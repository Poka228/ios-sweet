#!/usr/bin/env python3
"""Unpack an Android boot image header v0-v2 into kernel/ramdisk/second/dtb + header.txt.

With --scan-dtb, also extract the DTBs appended to the kernel in Image.gz-dtb
style (some MIUI boot images are header v1 with no DTB field; the base SoC DTB
then follows the gzip stream). The gzip payload is skipped so compressed bytes
cannot be mistaken for an FDT, then every validated FDT is written as
dtb-NN.dtb. Those are base SoC DTBs, not the board tree: on davinci the board
nodes live in the dtbo partition and are merged by ABL at boot.
"""
import struct, sys, os, zlib

args = [a for a in sys.argv[1:] if not a.startswith('--')]
src, out = args[0], args[1]
scan_dtb = '--scan-dtb' in sys.argv
os.makedirs(out, exist_ok=True)
b = open(src, 'rb').read()
assert b[:8] == b'ANDROID!'
(ks, ka, rs, ra, ss, sa, ta, ps, ver, osv) = struct.unpack_from('<10I', b, 8)
cmd = b[64:64+512].split(b'\0')[0] + b[608:608+1024].split(b'\0')[0]
info = dict(kernel_size=ks, kernel_addr=hex(ka), ramdisk_size=rs, ramdisk_addr=hex(ra),
            second_size=ss, tags_addr=hex(ta), page_size=ps, header_version=ver,
            os_version=hex(osv), name=b[48:64].split(b'\0')[0].decode(), cmdline=cmd.decode())
rnd = lambda n: (n + ps - 1) // ps * ps
off = ps
parts = [('kernel', ks), ('ramdisk', rs), ('second', ss)]
if ver >= 1:
    rds, rdo, hs = struct.unpack_from('<IQI', b, 1632)
    parts.append(('recovery_dtbo', rds)); info['header_size'] = hs
if ver >= 2:
    ds, da = struct.unpack_from('<IQ', b, 1648)
    parts.append(('dtb', ds)); info['dtb_addr'] = hex(da)
for name, sz in parts:
    if sz:
        open(f'{out}/{name}', 'wb').write(b[off:off+sz])
    info[name + '_offset'] = off
    off += rnd(sz)

if scan_dtb:
    kernel = b[ps:ps+ks]
    start = None
    if kernel[:2] == b'\x1f\x8b':
        try:
            d = zlib.decompressobj(16 + zlib.MAX_WBITS)
            d.decompress(kernel)
            if d.eof:
                start = ps + len(kernel) - len(d.unused_data)
        except zlib.error:
            pass
    elif kernel[0x38:0x3c] == b'ARM\x64':  # uncompressed arm64 Image
        start = ps + rnd(ks)
    found = 0
    if start is not None:
        i = start
        while i + 40 <= len(b):
            if b[i:i+4] == b'\xd0\x0d\xfe\xed':
                total, ostruct, ostr, orsv, dver = struct.unpack_from('>5I', b, i+4)
                if (dver in (16, 17) and 0x100 < total <= 4 << 20 and
                        ostruct < total and ostr < total and orsv < total and
                        i + total <= len(b)):
                    found += 1
                    open(f'{out}/dtb-{found:02d}.dtb', 'wb').write(b[i:i+total])
                    i += total
                    continue
            i += 4
    info['appended_dtbs'] = found

with open(f'{out}/header.txt', 'w') as f:
    for k, v in info.items():
        f.write(f'{k}: {v}\n')
print(open(f'{out}/header.txt').read())
