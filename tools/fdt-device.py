#!/usr/bin/env python3
"""Print the device-tree facts the port needs, from a stock Android boot.img DTB.

Usage:
    tools/fdt-device.py DTB [--all]

Reads the Flattened Device Tree that tools/unpack_bootv2.py extracts
(dtb/boot_unpacked/dtb) and prints:

  * the /memory nodes (bank base/size) and every /reserved-memory child,
  * the continuation-splash region (the linear framebuffer the shim draws to),
  * display panels and their native resolution,
  * touch controllers (bus node, reg address, supplies),
  * PMIC key/GPIO nodes,
  * the SoC blocks the kernel/shim hardcode (GIC, UFS, GCC, SPMI, RPMh).

The port uses these numbers in tools/mkadt.py, shim/device.h and the kernel
patches; --all dumps every node for deeper digging. No dependency beyond the
Python standard library.
"""
import struct
import sys

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9


def be32(b, o):
    return struct.unpack_from('>I', b, o)[0]


class Node:
    def __init__(self, name, parent=None):
        self.name = name
        self.parent = parent
        self.props = {}
        self.children = []

    @property
    def path(self):
        if self.parent is None:
            return '/'
        prefix = self.parent.path
        return (prefix if prefix != '/' else '') + '/' + self.name

    def prop_str(self, key):
        v = self.props.get(key)
        if v is None:
            return None
        return v.rstrip(b'\0').decode('utf-8', 'replace')

    def prop_u32s(self, key):
        v = self.props.get(key)
        if v is None:
            return None
        return list(struct.unpack('>%dI' % (len(v) // 4), v[:len(v) // 4 * 4]))

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


def parse(blob):
    if be32(blob, 0) != FDT_MAGIC:
        raise SystemExit('not a flattened device tree')
    total, off_struct, off_strings = be32(blob, 4), be32(blob, 8), be32(blob, 12)
    if total > len(blob):
        raise SystemExit('truncated device tree')
    p, root, cur = off_struct, None, None
    while p < total:
        tok = be32(blob, p)
        p += 4
        if tok == FDT_BEGIN_NODE:
            end = blob.index(b'\0', p)
            name = blob[p:end].decode('utf-8', 'replace')
            n = Node(name, cur)
            if cur is None:
                root = n
            else:
                cur.children.append(n)
            cur = n
            p = (end + 4) & ~3
        elif tok == FDT_END_NODE:
            cur = cur.parent
        elif tok == FDT_PROP:
            ln, nameoff = be32(blob, p), be32(blob, p + 4)
            val = p + 8
            s = off_strings + nameoff
            key = blob[s:blob.index(b'\0', s)].decode()
            cur.props[key] = blob[val:val + ln]
            p = (val + ln + 3) & ~3
        elif tok == FDT_NOP:
            continue
        elif tok == FDT_END:
            break
        else:
            raise SystemExit('bad FDT token 0x%x at 0x%x' % (tok, p))
    return root


def cells(node, prop, default=2):
    v = node.prop_u32s(prop)
    return v[0] if v else default


def decode_regs(root, node):
    """reg entries as (address, size) using the parent's #address/#size-cells."""
    ac = cells(node.parent or root, '#address-cells')
    sc = cells(node.parent or root, '#size-cells')
    v = node.props.get('reg')
    if v is None:
        return []
    words = list(struct.unpack('>%dI' % (len(v) // 4), v[:len(v) // 4 * 4]))
    out, i = [], 0
    while i + ac + sc <= len(words):
        addr = 0
        for w in words[i:i + ac]:
            addr = (addr << 32) | w
        size = 0
        for w in words[i + ac:i + ac + sc]:
            size = (size << 32) | w
        out.append((addr, size))
        i += ac + sc
    return out


def hexrange(a, s):
    if s:
        return '0x%x-0x%x (%s, %d MiB)' % (a, a + s - 1, hex(s), s // (1 << 20))
    return '0x%x' % a


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__.strip())
        return
    blob = open(sys.argv[1], 'rb').read()
    root = parse(blob)
    show_all = '--all' in sys.argv
    print('root: %s' % root.prop_str('compatible'))
    for key in ('model', 'qcom,board-id', 'qcom,msm-id', 'qcom,pmic-id'):
        if root.prop_str(key):
            print('%-16s %s' % (key + ':', root.prop_str(key)))

    print('\n[memory] (usable banks; mkadt --highmem uses the upper one)')
    for n in root.children:
        if n.name.startswith('memory'):
            for a, s in decode_regs(root, n):
                print('  %-22s %s' % (n.path, hexrange(a, s)))

    print('\n[reserved-memory] (carve-outs; the splash one is the panel buffer)')
    splash_hint = []
    for n in root.walk():
        if n.parent and n.parent.name == 'reserved-memory':
            regs = decode_regs(root, n)
            for a, s in regs:
                print('  %-30s %s  compat=%s' % (n.name, hexrange(a, s), n.prop_str('compatible')))
            low = n.name.lower()
            if 'splash' in low or 'fb' == low or 'cont_splash' in low:
                splash_hint.append((n.name, regs))

    print('\n[display] (panels and their native size)')
    for n in root.walk():
        c = n.prop_str('compatible') or ''
        w, h = n.prop_u32s('qcom,mdss-dsi-panel-width'), n.prop_u32s('qcom,mdss-dsi-panel-height')
        if (w or h) or 'dsi' in c and 'panel' in c:
            print('  %-40s %sx%s  %s' % (n.path, w[0] if w else '?', h[0] if h else '?', c))

    print('\n[touch] (controller bus nodes; the kernel driver probes these)')
    for n in root.walk():
        c = n.prop_str('compatible') or ''
        low = c.lower()
        if any(k in low for k in ('goodix', 'focaltech', 'ft5', 'novatek', 'synaptics', 'touchscreen')):
            regs = decode_regs(root, n)
            addrs = ', '.join('0x%x' % a for a, _ in regs)
            print('  %-40s compat=%s reg=%s' % (n.path, c, addrs))
            for key in ('interrupt-parent', 'interrupts', 'reset-gpios', 'irq-gpios',
                        'goodix,irq-gpio', 'goodix,reset-gpio',
                        'focaltech,reset-gpio', 'focaltech,irq-gpio'):
                v = n.prop_u32s(key)
                if v:
                    print('      %-22s %s' % (key + ':', ', '.join('0x%x' % x for x in v)))
            # supplies point at regulator phandles; resolve names one level up
            for key in ('vdd-supply', 'avdd-supply', 'vddio-supply'):
                v = n.prop_u32s(key)
                if not v:
                    continue
                for m in root.walk():
                    if m.prop_u32s('phandle') == v or m.prop_u32s('linux,phandle') == v:
                        print('      %-22s %s (%s)' % (key + ':', m.path,
                                                       m.prop_str('regulator-name')))

    print('\n[keys] (PMIC PON and GPIO keys)')
    for n in root.walk():
        c = (n.prop_str('compatible') or '').lower()
        if 'pon' in n.name or 'pon' in c or 'gpio-keys' in c or 'keys' == n.name:
            print('  %-40s compat=%s' % (n.path, n.prop_str('compatible')))
            interesting = [n] + n.children if ('gpio-keys' in c) else [n]
            for m in interesting:
                if 'linux,code' in m.props:
                    print('      %-22s %s' % (m.name + ' linux,code:', m.prop_u32s('linux,code')))
                for key in ('gpios', 'interrupts', 'qcom,pon_1', 'qcom,pon_2', 'qcom,pon_3'):
                    if key in m.props:
                        print('      %-22s %s' % (m.name + ' ' + key, m.prop_u32s(key)))

    print('\n[SoC blocks the shim/kernel hardcode]')
    wanted = {
        'interrupt-controller': ('GIC', 'arm,gic-v3'),
        'ufshc': ('UFS', 'qcom,ufshc'),
        'gcc': ('GCC', 'qcom,gcc'),
        'spmi': ('SPMI', 'qcom,spmi'),
        'rsc': ('RPMh', 'qcom,rpmh'),
        'imem': ('IMEM', 'qcom,msm-imem'),
        'usb': ('USB', 'qcom,dwc3'),
    }
    for n in root.walk():
        c = n.prop_str('compatible') or ''
        for needle, (label, compat) in wanted.items():
            if needle in n.name or compat in c:
                regs = decode_regs(root, n)
                if regs:
                    print('  %-6s %-32s %s  %s' % (label, n.path,
                                                   ', '.join(hexrange(a, s) for a, s in regs), c))
                break

    if splash_hint:
        print('\n[splash] candidates for shim/device.h FB_BASE and tools/mkadt.py fbcon:')
        for name, regs in splash_hint:
            for a, s in regs:
                print('  %s: base=0x%x size=0x%x' % (name, a, s))

    if show_all:
        print('\n[all nodes]')
        for n in root.walk():
            print('  %s  [%s]' % (n.path, ', '.join(sorted(n.props))))

    print('\nNote: the shim also needs this DTB packed into the boot image '
          '(shim/build.sh DTB=...).')


if __name__ == '__main__':
    main()
