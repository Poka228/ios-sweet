#!/usr/bin/env python3
"""Pull the SWEET persistent console log from a phone in recovery (adb root).

  sweet-log-pull.py [OUT.txt]

Reads only the last 1025 blocks (4 KiB each) of the userdata partition, where
kernel patch 0047 keeps the 4 MiB console ring + its header, and decodes it
with sweet-log.py.  All arithmetic happens here because cmd.exe set /a and the
recovery shell's $(( )) are both 32-bit (the partition is ~51 GiB).
"""
import os
import struct
import subprocess
import sys

SELF = os.path.dirname(os.path.abspath(__file__))
BLOCK = 4096
BLOCKS = 1 + (4 << 20) // BLOCK          # header block + 4 MiB ring = 1025
DEV_PATHS = ('/dev/block/by-name/userdata',
             '/dev/block/bootdevice/by-name/userdata')


def adb(*args, binary=False):
    """Run adb, return stdout (bytes if binary).  Raises on non-zero exit."""
    r = subprocess.run(['adb', *args], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, check=False)
    if r.returncode != 0:
        raise SystemExit('adb %s failed: %s'
                         % (' '.join(args), r.stderr.decode('utf-8', 'replace').strip()))
    return r.stdout if binary else r.stdout.decode('utf-8', 'replace').strip()


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join('logs', 'boot.txt')
    binary = out + '.bin'
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)

    # Resolve the userdata block device (by-name is stable across kernels).
    script = ('for d in %s; do [ -e "$d" ] && readlink -f "$d" && break; done'
              % ' '.join(DEV_PATHS))
    dev = adb('shell', script)
    if not dev:
        raise SystemExit('userdata block device not found on the connected device')
    print('userdata block device:', dev)

    # 64-bit size and offset: do NOT use the phone's shell arithmetic.
    size = int(adb('shell', 'blockdev --getsize64 ' + dev).split()[0])
    print('partition size: %d bytes' % size)
    if size < BLOCKS * BLOCK:
        raise SystemExit('partition too small for the log ring')
    skip = size // BLOCK - BLOCKS
    print('reading blocks %d.. (%d KiB from byte %d)'
          % (skip, BLOCKS * BLOCK // 1024, skip * BLOCK))

    data = adb('exec-out', 'dd if=%s bs=%d skip=%d count=%d 2>/dev/null'
               % (dev, BLOCK, skip, BLOCKS), binary=True)
    if len(data) != BLOCKS * BLOCK:
        sys.stderr.write('warning: read %d bytes, expected %d\n'
                         % (len(data), BLOCKS * BLOCK))
    with open(binary, 'wb') as f:
        f.write(data)

    magic, version, ring, total, seq = struct.unpack_from('<8sIIQQ', data, 0)
    if magic != b'SWEETLOG':
        raise SystemExit('no SWEETLOG header (log never flushed, or wrong area); '
                         'raw area kept in ' + binary)
    print('# version %d, ring %d, total %d bytes, flush #%d%s'
          % (version, ring, total, seq,
             ' (wrapped: oldest bytes lost)' if total > ring else ''))

    body = data[BLOCK:BLOCK + ring]
    if total <= ring:
        text = body[:total]
    else:
        start = total % ring
        text = body[start:] + body[:start]
    with open(out, 'w', newline='') as f:
        f.write(text.decode('utf-8', 'replace').replace('\r', ''))
    print('log written to %s  (raw area kept in %s, %d lines)'
          % (out, binary, text.count(b'\n')))


if __name__ == '__main__':
    main()
