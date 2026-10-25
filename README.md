# ios-sweet

**Apple's iOS 16 running on a Redmi Note 10 Pro — and now the Xiaomi Mi 9T.**

This project ports Apple's open-source XNU kernel (xnu-8796, the iOS 16 generation) to the Xiaomi Redmi Note 10 Pro (`sweet`, Qualcomm SM7150 / Snapdragon 732G). On top of it runs the **unmodified iOS 16.7.16 (20H392) userland of the iPhone X**: launchd, the system daemons, backboardd, SpringBoard and the stock apps.

The same kernel and boot image builder also support the **Xiaomi Mi 9T** (`davinci`, SM7150-AA / Snapdragon 730, 1080×2340 panel). Both boards share the SoC blocks, the UFS host, the PMIC wiring and the QUPv3 touch bus, so there is **one kernel binary**; the board differences are the panel height in the device tree (`tools/mkadt.py`, `FB_H`), the shim build (`DEVICE=`) and the davinci touch driver (patches 0082/0083). See [Xiaomi Mi 9T (davinci)](#xiaomi-mi-9t-davinci).

As of **2026-10-18** the sweet phone boots to the **iOS home screen**. You can unlock it, open Settings, pull down Control Center and the notification center, and use the touchscreen and the hardware buttons. Rendering runs entirely on the CPU; there is no GPU driver.

> Experimental bring-up, not a usable phone OS. Many things are missing or stubbed (see below), and Apple's security model is mostly switched off. It installs into the `userdata` partition and so **erases Android's user data**.

## What works

| Area | State |
| --- | --- |
| Boot | Stock Xiaomi bootloader → `fastboot boot` of our shim → XNU. Nothing is flashed to the boot partitions |
| CPU | 6 of the 8 cores (the six Cortex-A55s) via PSCI, 16K pages, GICv3 interrupts, timers |
| Memory | About 3.95 GiB of the upper DDR bank |
| Storage | Own UFS host driver; the iOS root is a journaled HFS+ volume in `userdata`, read/write |
| iOS userland | Real iPhone X 16.7.16 root filesystem and shared cache; launchd and the system daemons run |
| Display | Kernel IOSurface + IOMobileFramebuffer (`AppleCLCD`) services; CoreAnimation renders in software; frames are copied into the bootloader's framebuffer. Presented to iOS as an iPhone X panel (1125×2436) |
| GUI | backboardd, SpringBoard, lock screen, home screen, Control Center, notification center, Settings |
| Touch | Goodix GT9896 over I²C (GENI), rail enabled through RPMh, delivered as HID digitizer events |
| Buttons | Power, volume up/down (PMIC through SPMI) as HID consumer keys; lock/wake works |
| Battery | IOPMPowerSource service (static 100 %, charging icon; real fuel-gauge readout prepared) |
| Device identity | iPhone X (`iPhone10,3` / `D22AP`): no Home button, gesture UI |
| Activation | Native "Hactivation" path of mobileactivationd, chosen through device-tree security status. No Apple servers involved |

## What does not work (yet)

- **Navigation:** you cannot leave an app (the home gesture and AssistiveTouch Home do nothing yet).
- **No Wi-Fi, Bluetooth, cellular, audio, camera, sensors, GPS or SEP / Face ID.** Daemons for them start and fail or keep relaunching.
- **No GPU.** Everything is drawn by the CPU at roughly 20–30 fps. The two Cortex-A76 cores are not used yet.
- **Few apps.** The image has only what is on the system volume. There is no App Store, no Apple ID, and some Settings pages are empty.
- **Slow boot:** about 4 minutes on the Apple logo.
- **Security is off:** permissive code signing (AMFI) and sandbox policies, a stub AppleKeyStore, no data protection. Do not put anything personal on it.

## How it boots

```
ABL (stock Xiaomi bootloader, unlocked)
  -> fastboot boot shim-boot.img              (temporary; nothing is flashed to boot)
     -> shim: own MMU setup, reads the live FDT, loads the payload from the ramdisk
        -> XNU Mach-O + generated Apple Device Tree (ADT) + boot-args
           -> XNU -> UFS driver -> HFS+ root in the userdata partition
              -> dyld + shared cache -> launchd -> daemons -> backboardd + SpringBoard
```

There is no serial port (the debug UART is wired as SPI on this board). The kernel draws its console into the framebuffer that ABL leaves at `0x9c000000`, and keeps a persistent 4 MiB log ring at the end of `userdata`. You read that log from OrangeFox recovery with `tools/sweet-log-pull.sh`, so you don't have to film the screen.

## How to do it yourself

You need a Redmi Note 10 Pro (`sweet`, global or Indian variant, SM7150) with an **unlocked bootloader**, a Linux PC, and a GitHub account for the kernel build. This is the exact path used for the screenshots above; other variants or firmware may need changes. **Everything on `userdata` is lost.** Bootloaders, recovery, modem and persist partitions are never touched.

### 0. Back up the phone

Boot OrangeFox (or any recovery with adb root) temporarily and pull at least `persist`, `modemst1`, `modemst2`, `fsg`, `fsc` and `boot`, `dtbo`, `vbmeta`. They contain per-device calibration data. Keep them off git; `.gitignore` already excludes `backup/`, `dtb/` and `recovery/`.

The shim needs the stock DTB. Unpack your phone's stock `boot.img`:

```sh
python3 tools/unpack_bootv2.py backup/boot.img dtb/boot_unpacked   # -> dtb/boot_unpacked/dtb
```

### 1. Build the kernel

The kernel builds on GitHub's macOS runners with [blacktop/darwin-xnu-build](https://github.com/blacktop/darwin-xnu-build). The workflow fetches xnu-8796, applies `xnu/patches/` in order, and also stages the pinned open-source libpthread, HFS and BearSSL sources it needs. Fork the repo (public repos get free macOS minutes) and run:

```sh
gh workflow run xnu.yml -R YOU/ios-sweet
gh run download RUN_ID -R YOU/ios-sweet -n xnu-kernel -D xnu/out
```

To check a patch locally before spending a CI run, `tools/xnu-cc.py` replays the compile commands of a previous CI log for single files.

### 2. Build the iOS root image

Download the iPhone X (iPhone10,3) iOS 16.7.16 (20H392) IPSW from Apple. Then, on Linux, with `apfs-fuse`, `hfsprogs` and sudo:

```sh
# OS, SystemOS and AppOS disk images from the IPSW (see BuildManifest.plist for their names)
tools/mkiosroot.sh OS.dmg SystemOS.dmg AppOS.dmg ios16-root.img 16G
sudo fsck.hfsplus -fy ios16-root.img
sudo mount -t hfsplus -o loop,force ios16-root.img /mnt/iosroot
sudo python3 tools/sweet-root-tweaks.py /mnt/iosroot
sudo umount /mnt/iosroot
img2simg ios16-root.img ios16-root.simg
```

`mkiosroot.sh` copies the OS volume and both cryptexes into one case-sensitive journaled HFS+ volume. It adds the dyld cache links, the plain system keybag and the log directories the daemons expect. `sweet-root-tweaks.py` applies the bring-up changes: it skips Setup, seeds the activation state, removes the baseband daemon, disables the watchdogs that kill slow apps and the crash-looping media paths, and so on. The script's header explains each change.

The device tree builder copies `/product` from the real iPhone X device tree, which MobileGestalt needs. Extract it once, without downloading the whole IPSW:

```sh
python3 tools/remotezip.py IPSW_URL DeviceTree.d22ap.im4p research/ipsw-x/dt
ipsw img4 im4p extract research/ipsw-x/dt/Firmware/all_flash/DeviceTree.d22ap.im4p -o research/ipsw-x/d22ap.adt
```

### 3. Build the boot image

Needs `aarch64-linux-gnu-gcc` and `mkbootimg`.

```sh
python3 tools/mkadt.py shim/out/sweet.adt --highmem
python3 tools/mkpayload.py xnu/out/kernel.development.sweet shim/out/sweet.adt shim/out/payload.bin \
    --cmdline 'debug=0xc serial=3 cpus=6 keepsyms=1 -enable_kprintf_spam -noprogress rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin ufsrw=1 rootrw=1 launchd_unsecure_cache=1 wdt=-1 sweetfb_noconsole=1 sweetfb_hz=30'
shim/build.sh out/payload.bin          # add DEVICE=davinci on a Mi 9T -> shim-boot-<device>.img
```

What the less obvious boot-args do:

| Boot-arg | Effect |
| --- | --- |
| `rd=ufsroot0 ufsrw=1 rootrw=1` | Root on the `userdata` partition, writable |
| `cpus=6` | Start the six A55 cores; `cpus=1` is the safe fallback |
| `launchd_unsecure_cache=1` | launchd accepts its job cache without AMFI |
| `wdt=-1 wdt_test=no_user_checkin` | No hardware watchdog |
| `sweetfb_noconsole=1` | Stop drawing kernel text over the GUI. It still goes to the persistent log; panics are drawn |
| `sweetfb_hz=30` | Panel refresh rate of the CPU copy |
| `sweettouch=0`, `sweetkeys=0` | Disable the touch or button driver |

### 4. Flash the root and boot

```sh
fastboot -S 512M flash userdata ios16-root.simg   # ~7 minutes; do not unplug
# Xiaomi's fastboot often hangs after a large flash: re-enter fastboot with Power + Volume down
fastboot boot shim/out/shim-boot.img
```

The first boot takes about 4–5 minutes on the Apple logo, then the lock screen appears. Swipe up to unlock. To get back to fastboot, hold Power + Volume down.

### 5. Read the kernel log

```sh
fastboot boot recovery/recovery.img        # OrangeFox, temporary
tools/sweet-log-pull.sh logs/boot.txt      # 4 MiB console ring from the end of userdata
adb reboot bootloader
```

The log contains crash reports with backtraces (`CRASH name ...`), IOKit traces of backboardd and SpringBoard, and the drivers' `SWEET ...` lines. `tools/sweet-crash.py` symbolicates them against the shared cache.

### QEMU

`tools/qemu-sweet.py` boots the same kernel on QEMU `virt` with a test RAM-disk root. It is useful for kernel-only changes; see `NOTES.md`.

## Xiaomi Mi 9T (davinci)

The Mi 9T is the same SM7150 family as the Note 10 Pro, so the kernel is **not** rebuilt per board: the CI kernel (`machine_config=SWEET`) is used as is. Only the device tree and the boot shim carry board data.

| | sweet (Note 10 Pro) | davinci (Mi 9T) |
| --- | --- | --- |
| Panel | 1080×2400 AMOLED | 1080×2340 AMOLED (Samsung EA F10, DSI command mode) |
| Splash framebuffer | `0x9c000000`, 0x1700000 | identical |
| Touch | Goodix GT9896 (Yellowstone) or FocalTech 54:52, I²C `0x5d` on QUPv3 SE7 `0xa84000`, TLMM 6/7 SDA/SCL, 8 reset, 9 IRQ | Goodix GT9886 (Normandy), same bus and pins; GPIO90 is the pop-up camera motor and must never be driven |
| Touch power | PM6150L LDO11 (`ldoc11`, 3200 mV) + TLMM 90 gate | PM6150L LDO6 (`ldoc6`, 3000 mV), no enable pin |
| Keys | PM6150 PON + PM6150L GPIO2 | identical |
| UFS / GIC / RPMh / SPMI / IMEM / USB / timer | `0x1d84000` / `0x17a00000` / `0x18220000` / `0xc440000` / `0x146aa65c` / `0xa600000` / 19.2 MHz | identical |

The panel height is `FB_H` in `tools/mkadt.py` (2400 on sweet, 2340 on davinci) and in `shim/device.h`. Patch 0082 makes the kernel's touch driver davinci-only: it replaces the sweet GT9896/FocalTech probe with the GT9886 protocol and the L6C rail, so a kernel built from this series no longer brings up sweet's touchscreen.

Use the same steps as above with the device-specific commands below. Step 0 (unpacking your Mi 9T's stock `boot.img` into `dtb/boot_unpacked/`) gives the shim the **base** `qcom,sdmmagpie` DTB; the board/panel nodes live in the `dtbo` partition and ABL merges them onto that base during boot, exactly as for a stock boot. The MIUI 12 boot image is header v1 with no header DTB, so the base DTB is in the appended `Image.gz-dtb` collection; extract it with `python3 tools/unpack_bootv2.py dtb/davinci-boot.img dtb/boot_unpacked --scan-dtb` and copy `dtb-01.dtb` over `dtb/boot_unpacked/dtb`.

```sh
# Check the stock DTB against the profile first: memory banks, splash
# region, panel size, touch node, PMIC keys, SoC block addresses.
python3 tools/fdt-device.py dtb/boot_unpacked/dtb

python3 tools/mkadt.py shim/out/davinci.adt --highmem
python3 tools/mkpayload.py xnu/out/kernel.development.sweet shim/out/davinci.adt shim/out/payload.bin \
    --cmdline 'debug=0xc serial=3 cpus=6 keepsyms=1 -enable_kprintf_spam -noprogress rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin ufsrw=1 rootrw=1 launchd_unsecure_cache=1 wdt=-1 sweetfb_noconsole=1 sweetfb_hz=30'
DEVICE=davinci shim/build.sh out/payload.bin  # -> shim/out/shim-boot-davinci.img
fastboot boot shim/out/shim-boot-davinci.img       # temporary boot, nothing is flashed
```

The touch driver stops after the GT9886 PID probe unless you add `davinci_touch_probeonly=0` to the boot-args.

The iPhone X image is unchanged: it is presented as a 1125×2436 canvas and centre-cropped to the 1080×2340 panel (48 px off the top and bottom); touch coordinates are normalized with the panel size from the ADT. The splash buffer is at the same `0x9c000000` as sweet. The upper DDR bank is `0x100000000` + `0xfcc00000`, confirmed by a bootloader-patched live davinci FDT (ABL fills in `/memory`, so it is not in the static DTB); `tools/fdt-device.py` prints it together with the splash region, the panel, the touch node, the keys and the SoC blocks, so you can re-check it on your own phone.

## Repository layout

| Path | What |
| --- | --- |
| `shim/` | Bare-metal boot shim (C + asm) packed as an Android boot.img v2 |
| `xnu/patches/` | The XNU patch series (applied in order by CI), plus staging scripts for libpthread, HFS and BearSSL |
| `.github/workflows/xnu.yml` | Kernel CI build |
| `tools/mkadt.py` | Generates the Apple Device Tree from the board's MMIO layout (`FB_H` is the per-board value) and the iPhone X identity |
| `tools/fdt-device.py` | Prints memory/splash/panel/touch/PMIC facts from a stock `boot.img` DTB or a live FDT (verifies a device profile) |
| `tools/mkpayload.py` | Packs kernel + ADT + boot-args into the shim payload |
| `tools/mkiosroot.sh` | Builds the HFS+ iOS root from the IPSW images |
| `tools/sweet-root-tweaks.py` | Bring-up changes to the root (Setup skip, activation, daemons) |
| `tools/sweet-log-pull.sh`, `sweet-log.py` | Read the persistent kernel log from recovery |
| `tools/sweet-crash.py` | Symbolicate console crash reports |
| `tools/xnu-cc.py` | Local single-file compile check from a CI log |
| `tools/qemu-sweet.py` | QEMU test boots with framebuffer text decoding |
| `tools/adt.py`, `remotezip.py`, `unpack_bootv2.py`, `sparsediff.py` | Helpers |
| `NOTES.md` | Detailed engineering log: every boot, crash and decision, plus hardware facts |

Not in git: partition backups, live device trees, recovery images, Apple firmware and root images, and downloaded or generated build trees. They contain device serials and calibration data, or Apple's copyrighted files.

## Kernel patches

| # | What |
| --- | --- |
| 0001–0009 | Toolchain compatibility, SWEET machine config, non-PAC arm64, stubs for Apple-internal pieces |
| 0010–0018 | Early framebuffer console, physmap fix, PRNG without corecrypto, device-tree platform expert, timer PPI, boot CPU driver |
| 0019–0020 | Apple open-source libpthread kernel provider; BearSSL AES |
| 0021–0027 | RAM-disk root, mockfs, SHA-256, minimal AMFI, Apple open-source HFS+, MD5 |
| 0028–0034 | UFS host driver and root device, read/write root, DMA above 4 GiB |
| 0035–0045 | Entitlements, bindfs, AppleKeyStore stub, IOWatchdog, console crash reports |
| 0046 | IOSurface (IOCoreSurfaceRoot) and IOMobileFramebuffer (AppleCLCD) services |
| 0047–0055 | Diagnostics: persistent log, /dev/null tee, IOKit trace, heap strings and user stack sampler on crash; permissive Sandbox policy; HFS rename-swap; AppleKeyStore selectors |
| 0056–0057 | Throttled panel copy; no external identity resolver |
| 0058 | HID event services. Apple's IOHIDFamily-1915.140.3 user client and event queue, matching the iOS 16.7 userland |
| 0059 | iPhone X identity (`hw.product` / `hw.target` from the device tree) |
| 0060 | Power and volume keys over SPMI; touch over GENI I²C |
| 0061 | Present the display as 1125×2436 |
| 0062 | RPMh regulator vote for the touch rail; battery power source |
| 0063 | GENI FIFO packing fix and the Goodix GT9896 protocol |
| 0064 | Grant PRIV_WORK_INTERVAL (UIKit's CoreAnimation work interval) |
| 0065 | SMP: secondary A55 cores via PSCI CPU_ON |
| 0066–0067 | Fault-region crash info; console mute |
| 0068 | IOSurface lookup semantics for already-mapped surfaces |
| 0069 | Batched persistent-log flushes |
| 0070 | Hibernate PID handling |
| 0071 | Touch edge-tip events for the home/app-switcher gestures |
| 0072–0077 | USB device mode: probe, EP0, VBUS override, ECM, RX mbufs, live log |
| 0078 | SMP with all eight cores |
| 0079 | Display power |
| 0080 | Network trace |
| 0081 | USB link state |
| 0082 | davinci touch: Goodix GT9886 (Normandy) protocol, PM6150L L6C rail at 3000 mV, GPIO90 (pop-up camera motor) never touched |
| 0083 | davinci bottom-edge gestures (SweetHID digitizer mapping) |

## Key hardware facts

- RAM: payloads use the upper bank, `0x100000000` + `0xfcc00000` (about 3.95 GiB), above Qualcomm's protected carve-outs.
- GICv3 with security extensions: the timer goes through Group 1 IRQ (virtual timer INTID 19), not FIQ as on Apple silicon.
- PSCI through `smc`, 19.2 MHz timer, ARMv8.2 without pointer authentication. MPIDR uses Aff1 for the core number.
- Panel: sweet 1080×2400 DSC video mode, davinci 1080×2340 command mode; both use the continuous ABL splash buffer at `0x9c000000`, no refresh kick needed.
- Touch: Goodix GT9896 (sweet) / GT9889 (davinci) at I²C `0x5d` on QUP SE7 (`0xa84000`); sweet is powered by PM6150L LDO11, davinci by LDO6 plus a 1.8 V gate on TLMM 5, both through RPMh. The driver maps the TLMM base supplied by the ADT (davinci `0x03400000`).
- Buttons: power and volume down on the PM6150 PON block, volume up on PM6150L GPIO2 (SPMI SID 4) — identical on both boards.

More in [`NOTES.md`](NOTES.md).

## Credits

Built on Apple's open-source releases (xnu, IOHIDFamily, libpthread, hfs), [BearSSL](https://bearssl.org), [blacktop/darwin-xnu-build](https://github.com/blacktop/darwin-xnu-build), [ipsw](https://github.com/blacktop/ipsw), Qualcomm/Xiaomi's published Linux kernel sources for the hardware details, and [OrangeFox Recovery](https://orangefox.download). iOS itself is Apple's and is not distributed here.
