#!/usr/bin/env python3
"""Fast raw -> Android sparse image converter (big sequential reads).

  mksparse.py IN.img OUT.simg [--block 4096] [--read 8]

`img2simg` reads the image in 4 KiB pieces, which crawls on DrvFs/9p mounts
(~9 MB/s).  This one streams the input in large chunks (~250 MB/s here) and
emits RAW chunks for data, DONT_CARE for runs of zero blocks.
"""
import argparse
import os
import struct
import sys

MAGIC = 0xed26ff3a
RAW, DONT_CARE = 0xcac1, 0xcac3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--block', type=int, default=4096)
    ap.add_argument('--read', type=int, default=8, help='read size in MiB')
    a = ap.parse_args()

    bs = a.block
    size = os.path.getsize(a.src)
    if size % bs:
        sys.exit('image size is not a multiple of the block size')
    total_blks = size // bs
    step = max(1, (a.read << 20) // bs)

    nchunks = 0
    with open(a.src, 'rb', buffering=0) as fi, open(a.dst, 'wb', buffering=0) as fo:
        fo.write(b'\0' * 28)  # header patched at the end
        left = total_blks
        while left:
            want = min(step, left)
            buf = fi.read(want * bs)
            if len(buf) != want * bs:
                sys.exit('short read')
            left -= want
            buf = bytearray(buf)
            if 0 not in buf:  # fast path: no zero bytes at all in this buffer
                fo.write(struct.pack('<HHII', RAW, 0, want, 12 + want * bs))
                fo.write(buf)
                nchunks += 1
                continue
            i = 0
            while i < want:
                off = i * bs
                is_zero = not any(buf[off:off + bs])
                j = i + 1
                while j < want:
                    o = j * bs
                    z = not any(buf[o:o + bs])
                    if z != is_zero:
                        break
                    j += 1
                cnt = j - i
                if is_zero:
                    fo.write(struct.pack('<HHII', DONT_CARE, 0, cnt, 12))
                else:
                    fo.write(struct.pack('<HHII', RAW, 0, cnt, 12 + cnt * bs))
                    fo.write(buf[off:off + cnt * bs])
                nchunks += 1
                i = j
        fo.flush()
        os.fsync(fo.fileno())
        fo.seek(0)
        fo.write(struct.pack('<IHHHHIIII', MAGIC, 1, 0, 28, 12, bs,
                             total_blks, nchunks, 0))
        fo.flush()
        os.fsync(fo.fileno())
    print('%s -> %s: %d blocks, %d chunks, %d bytes' %
          (a.src, a.dst, total_blks, nchunks, os.path.getsize(a.dst)))


if __name__ == '__main__':
    main()
