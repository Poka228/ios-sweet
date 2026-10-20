# Xiaomi Mi 9T / Redmi K20 (`davinci`) — hardware reference for bare-metal bring-up

Target: Xiaomi Mi 9T (global) / Redmi K20 (China), codename **davinci**, SoC
**SM7150-AA** (Snapdragon 730). This document collects the addresses, memory
layout, panel/touch/PMIC wiring, and davinci-vs-sweet differences needed to port
the existing sweet-based XNU bring-up.

Confidence markers used below:

- **[DT]** — stated in the downstream or mainline device tree.
- **[FDT]** — read from a dumped, bootloader-patched FDT (`fdt-davinci`). This is
  ground truth for anything ABL fills in at boot (`/memory`, `bootargs`).
- **[INF]** — inference from two or more sources; reasonable but not proven.
- **[?]** — unconfirmed; treat as a hypothesis and verify on hardware.

Primary downstream source (pinned):
[LineageOS/android_kernel_xiaomi_sm6150 @ `e03e5ba22586be70673afb5d3c3f70510524e658`](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/tree/e03e5ba22586be70673afb5d3c3f70510524e658).
Cross-check: [MiCode/davinci-p-oss](https://github.com/MiCode/davinci-p-oss).

Mainline source (pinned):
[sm7150-mainline/linux @ `fd78d17954a86ea6ceb0c535e618ea129e09f8dd`](https://github.com/sm7150-mainline/linux/tree/fd78d17954a86ea6ceb0c535e618ea129e09f8dd).
Dumped FDTs: [sm7150-mainline/downstream-fdt](https://github.com/sm7150-mainline/downstream-fdt)
(`fdt-davinci`, `fdt-sweet`).

> Note on the name: davinci is the **sdmmagpie / SM7150** platform. It is *not*
> `trinket` (SM6150 / SD675). The shared Xiaomi files use `sdmmagpie` in their
> names and are also used by other SM7150 devices.

---

## 1. SoC and CPU topology

| Item | Value | Source |
|---|---|---|
| Marketing SoC | Snapdragon 730 (SM7150-AA) | downstream `qcom,sdmmagpie` |
| DT machine compatible | `qcom,sdmmagpie-qrd`, `qcom,sdmmagpie`, `qcom,qrd` | [overlay L24-28](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/davinci-sdmmagpie-overlay.dts#L24-L28) |
| `qcom,msm-id` | `<365 0x0>` | same |
| `qcom,board-id` (downstream) | `<39 0>` | same |
| `qcom,board-id` (mainline) | `<40 0>` | [sm7150-xiaomi-davinci.dtsi L30](https://github.com/sm7150-mainline/linux/blob/fd78d17954a86ea6ceb0c535e618ea129e09f8dd/arch/arm64/boot/dts/qcom/sm7150-xiaomi-davinci.dtsi#L30) |
| Mainline compatible | `xiaomi,davinci-samsung` / `xiaomi,davinci-visionox`, `xiaomi,davinci`, `qcom,sm7150` | [samsung.dts](https://github.com/sm7150-mainline/linux/blob/fd78d17954a86ea6ceb0c535e618ea129e09f8dd/arch/arm64/boot/dts/qcom/sm7150-xiaomi-davinci-samsung.dts#L18), [visionox.dts](https://github.com/sm7150-mainline/linux/blob/fd78d17954a86ea6ceb0c535e618ea129e09f8dd/arch/arm64/boot/dts/qcom/sm7150-xiaomi-davinci-visionox.dts#L18) |

CPU nodes in [`sdmmagpie.dtsi`](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie.dtsi#L58):

| CPUs | Node | MPIDR Aff1 | Core |
|---|---|---|---|
| CPU0–CPU5 | `cpu@0`, `cpu@100` … `cpu@500` | 0x0–0x5 | Cortex-A55 |
| CPU6–CPU7 | `cpu@600`, `cpu@700` | 0x6, 0x7 | Cortex-A76 |

Reported clocks on Mi 9T: A55 up to 1.8 GHz, A76 up to 2.2 GHz. The existing
port already emits 1.8/2.2 GHz for the davinci profile, so this matches.

**Porting note:** Aff1 is the sequential core number (0–7), exactly as on sweet.
There is no affinity remap needed.

---

## 2. Memory layout

### 2.1 `/memory` — filled by ABL, not present in any dts

Dumped davinci FDT:

```dts
/memory
    ddr_device_type = 0x00000007 (7)
    device_type = 'memory'
    reg = <0x00000000 0x80000000 0x00000000 0x80000000    /* 2 GiB @ 0x8000_0000 */
           0x00000001 0x00000000 0x00000000 0xfcc00000>;  /* ~3.95 GiB @ 0x1_0000_0000 */
```

Source: [`fdt-davinci`](https://github.com/sm7150-mainline/downstream-fdt/blob/master/fdt-davinci),
`/memory` (also visible in the local decompile `/tmp/opencode/davinci_fdt.txt`
around line 18380).

Decoded:

| Bank | Start | Size | End (exclusive) |
|---|---|---|---|
| 0 | `0x0000_0000_8000_0000` | `0x8000_0000` (2 GiB) | `0x0000_0000_FFFF_FFFF`+1 |
| 1 | `0x0000_0001_0000_0000` | `0xFCC0_0000` (4,238,475,264 B) | `0x0000_0001_FCC0_0000` |

Total `0x1_7CC0_0000` = 6,388,891,648 B ≈ **5.95 GiB** usable description. This
is the 6 GB variant (the dumped unit). The gap between the top of RAM
(`0x1_FCC0_0000`) and `0x2_0000_0000` is `0x0340_0000` = 52 MiB; it is not
described in `/memory` and has no `reserved-memory` entry. **[FDT]**

Sweet, for comparison (same dump set):

```dts
/memory
    reg = <0x0 0x80000000 0x1 0x0
           0x1 0x80000000 0x0 0xFBB00000>;   /* 4 GiB low + ~3.93 GiB @ 0x1_8000_0000 */
```

So sweet's dump is an 8 GB unit with a **different bank split** (4 GiB low,
upper bank at 0x1_8000_0000). Do **not** reuse the sweet upper-DDR base on
davinci.

**8 GB davinci is unconfirmed.** GSMArena lists a 6/256 and an 8/256 MiB 9T;
LineageOS/e/OS report 6 GB. If a davinci 8 GB unit follows the sweet pattern,
the upper bank would start at `0x1_8000_0000` with size `0xFBB0_0000`, but no
davinci dump confirms it. **[?]**

### 2.2 `reserved-memory` (identical on davinci and sweet)

Base values live in [`sdmmagpie.dtsi` L487+](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie.dtsi#L487);
both Xiaomi devices apply the same overrides in
[`xiaomi-sdmmagpie-common.dtsi`](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/xiaomi/xiaomi-sdmmagpie-common.dtsi#L266)
and [`davinci-sdmmagpie.dtsi`](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/xiaomi/davinci/davinci-sdmmagpie.dtsi#L226).
All of the following are confirmed in `fdt-davinci`.

| Region | Start | Size | Notes |
|---|---|---|---|
| `hyp_region` | `0x8570_0000` | `0x0060_0000` | hypervisor |
| `xbl_aop_mem` | `0x85e0_0000` | `0x001f_f000` | XBL/AOP |
| `sec_apps_region` | `0x85ff_f000` | `0x0000_1000` | |
| `smem` | `0x8600_0000` | `0x0020_0000` | shared memory |
| `removed_region` (TZ) | `0x8620_0000` | `0x0490_0000` | 73 MiB; enlarged from `0x02d0_0000` |
| `camera_region` | `0x8ab0_0000` | `0x0050_0000` | |
| `modem_region` | `0x8b00_0000` | `0x0840_0000` | 132 MiB |
| `pil_video_region` (venus) | `0x9340_0000` | `0x0050_0000` | |
| `cdsp_regions` | `0x9390_0000` | `0x01e0_0000` | |
| `pil_adsp_region` | `0x9570_0000` | `0x0260_0000` | base default `0x1e0_0000` |
| `wlan_msa_region` | `0x97d0_0000` | `0x0018_0000` | base default `0x9750_0000` |
| `npu_region` | `0x97e8_0000` | `0x0008_0000` | base default `0x9768_0000` |
| `pil_ipa_fw_mem` | `0x97f0_0000` | `0x0001_0000` | |
| `pil_ipa_gsi_mem` | `0x97f1_0000` | `0x0000_5000` | |
| `pil_gpu_mem` | `0x97f1_5000` | `0x0000_2000` | |
| `qseecom_region` | `0x9e40_0000` | `0x0140_0000` | |
| `cdsp_sec_regions` | `0x9f80_0000` | `0x01e0_0000` | |
| `cont_splash_region` | `0x9c00_0000` | `0x0170_0000` | 23 MiB, see §8.4 |
| `dfps_data_region` | `0x9d70_0000` | `0x0010_0000` | |
| `ramdump_fb_region` | `0xaf00_0000` | `0x0100_0000` | Xiaomi addition |
| `xbl_dump_mem` | `0x85d0_0000` | `0x0010_0000` | Xiaomi addition |

Dynamic pools (`alloc-ranges = <0 0 ...>`): `adsp_mem` 12 MiB, `cdsp_mem`
4 MiB, `qseecom_ta_mem` 16 MiB, `sp_mem` 8 MiB, `secure_display_region` 140 MiB,
and `linux,cma` 32 MiB (`0x200_0000`).

`cont_splash_region` is **not** `no-map` and is used as the boot framebuffer;
everything else listed with `no-map` must be excluded from any XNU physical
memory map. The existing `tools/mkadt.py` davinci profile already uses
`0x9c000000` / `0x1700000`.

---

## 3. Boot chain, boot image, and FDT evidence

### 3.1 `/chosen/bootargs` from the dumped davinci unit

```text
rcu_nocbs=0-7 noirqdebug console=ttyMSM0,115200n8 earlycon=msm_geni_serial,0x880000
androidboot.hardware=qcom androidboot.console=ttyMSM0 androidboot.usbcontroller=a600000.dwc3
service_locator.enable=1 lpm_levels.sleep_disabled=1 loop.max_part=7 buildvariant=user
androidboot.verifiedbootstate=orange androidboot.keymaster=1
root=PARTUUID=6b18816d-9435-5a4f-2253-b1527a78dfe1
androidboot.bootdevice=1d84000.ufshc androidboot.fstab_suffix=default
androidboot.serialno=be631643 androidboot.ramdump=disable androidboot.secureboot=1
androidboot.cpuid=0x89004b2c androidboot.hwversion=5.19.0 androidboot.hwc=GLOBAL
androidboot.hwlevel=MP androidboot.baseband=msm
msm_drm.dsi_display0=dsi_ss_fhd_ea_f10_cmd_display: skip_initramfs rootwait ro init=/init
androidboot.dtbo_idx=1 androidboot.dtb_idx=0 androidboot.dp=0x0
```

Key facts:

- Serial console is the **GENI QUP UART at `0x880000`**, IRQ-driven at runtime
  (`ttyMSM0`), earlycon `msm_geni_serial,0x880000`.
- UFS boot device is `1d84000.ufshc` (see §10).
- USB controller is `a600000.dwc3` (see §11).
- **Panel selection is a bootarg, not a DT flag**:
  `msm_drm.dsi_display0=dsi_ss_fhd_ea_f10_cmd_display`. The dumped unit is a
  Samsung EA panel.
- `androidboot.dtbo_idx=1`, `androidboot.dtb_idx=0`: the bootloader overlays a
  DTBO; the base DTB is index 0.
- `androidboot.hwversion=5.19.0`, `hwc=GLOBAL`, `hwlevel=MP`.

### 3.2 Boot image layout (LineageOS 23.2 device trees)

From
[`android_device_xiaomi_davinci/BoardConfig.mk`](https://github.com/LineageOS/android_device_xiaomi_davinci/blob/lineage-23.2/BoardConfig.mk)
and
[`android_device_xiaomi_sm6150-common/BoardConfigCommon.mk`](https://github.com/LineageOS/android_device_xiaomi_sm6150-common/blob/lineage-23.2/BoardConfigCommon.mk):

| Item | Value |
|---|---|
| `BOARD_BOOTIMAGE_PARTITION_SIZE` | `134217728` (128 MiB) |
| `BOARD_DTBOIMG_PARTITION_SIZE` | `33554432` (32 MiB) |
| `BOARD_RECOVERYIMAGE_PARTITION_SIZE` | `67108864` (64 MiB) |
| `BOARD_INCLUDE_DTB_IN_BOOTIMG` | `true` |
| `BOARD_KERNEL_SEPARATED_DTBO` | `true` |
| `BOARD_BOOTIMG_HEADER_VERSION` | `2` |
| Kernel base / page size | `0x0` / 4096 |
| Kernel image | `Image.gz` |

The DTBO is a separate partition and is applied by ABL on top of the base
DTB. The dumped `fdt-davinci` is the **post-overlay** view.

A raw dump of the MIUI 12 `boot` partition (128 MiB, AVB footer) shows how
the base arrives: header v1, `ramdisk_size=0`, no DTB field. After the gzip
kernel (`Linux 4.14.180-perf-gf5e9e9c`, MIUI builder) there is a 3.29 MiB
appended DTB collection in `Image.gz-dtb` style. It contains 15 DTBs for
many Qualcomm SoCs, including the generic `qcom,sdmmagpie` base
(`dtb01`, 397,929 bytes) but **no davinci board DTB** (no `xiaomi,davinci`,
no Goodix node). The board/panel nodes therefore come from the `dtbo`
partition.

The stock `dtbo` dump (746,917 bytes, Android dt_table v0) contains three
full overlays with `qcom,board-id` **39, 40 and 41** (downstream 39 = the
dumped unit). The base DTB has `__symbols__` and the overlays carry
`__fixups__`, so ABL can apply them normally. `dtb/boot_unpacked/dtb` in
this repo is the extracted `qcom,sdmmagpie` base; ABL merges the phone's
dtbo onto it exactly as for a stock boot.

---

## 4. Base addresses (verified in both dts and dumped FDT)

All values below are physical addresses; sizes in parentheses.

| Block | Address | Size | Source |
|---|---|---|---|
| GIC distributor (GICD) | `0x17a0_0000` | `0x1_0000` | [`sdmmagpie.dtsi` L759](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie.dtsi#L759) |
| GIC redistributors (GICR) | `0x17a6_0000` | `0x10_0000` | same, stride `0x2_0000`, 8 frames |
| GCC | `0x0010_0000` | `0x1f_0000` | [`sdmmagpie.dtsi` L897](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie.dtsi#L897) |
| TLMM (pinctrl) | `0x0340_0000` | `0xdc_2000` | [`sdmmagpie-pinctrl.dtsi` L14](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie-pinctrl.dtsi#L14) |
| TLMM SPI config | `0x17c0_00f0` | `0x60` | same, second reg |
| UFS host controller | `0x01d8_4000` | `0x3000` | [`sdmmagpie.dtsi` L2281](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie.dtsi#L2281) |
| UFS ICE | `0x01d9_0000` | `0x8000` | same |
| UFS PHY | `0x01d8_7000` | `0x0ddc` | `ufsphy_mem` node |
| SPMI core | `0x0c44_0000` | `0x1100` | [`sdmmagpie.dtsi` L2488](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie.dtsi#L2488) |
| SPMI channels | `0x0c60_0000` | `0x200_0000` | same |
| SPMI observer | `0x0e60_0000` | `0x10_0000` | same |
| SPMI intr | `0x0e70_0000` | `0xa_0000` | same |
| SPMI cnfg | `0x0c40_a000` | `0x2_6000` | same |
| Apps RSC mailbox | `0x1822_0000` | `0x100` | [`sdmmagpie.dtsi` L1477](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie.dtsi#L1477) |
| Apps RSC TCS | `0x1822_0d00` | `0x3000` | same |
| AOP QMP mailbox | `0x0c30_0000` | `0x1000` | [`sdmmagpie.dtsi` L1902](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie.dtsi#L1902) |
| AOP QMP IRQ register | `0x17c0_000c` | 4 B | same, `irq-reg-base` |
| IMEM | `0x146a_a000` | `0x1000` | [`sdmmagpie.dtsi` L1016](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie.dtsi#L1016) |
| IMEM `restart_reason` | `0x146a_a65c` | 4 B | `restart_reason@65c` inside IMEM |
| PSHOLD | `0x0c26_4000` | 4 B | [`sdmmagpie.dtsi` L1059](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie.dtsi#L1059) |
| TCSR boot-misc | `0x01fd_3000` | 4 B | same |
| USB3 wrapper (`ssusb`) | `0x0a60_0000` | `0x10_0000` | [`sdmmagpie-usb.dtsi` L17](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie-usb.dtsi#L17) |
| DWC3 core | `0x0a60_0000` | `0xcd00` | same L87 |
| QUSB2 PHY | `0x088e_2000` | `0x400` | same L136 |
| QUSB2 efuse | `0x0078_0200` | 4 B | same |
| QUSB2 refgen | `0x088e_7014` | 4 B | same |
| QMP USB/DP PHY | `0x088e_8000` | `0x3000` | same L216 |
| PDC | `0x0b22_0000` | `0x400` | [`sdmmagpie.dtsi` L771](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie.dtsi#L771) |
| Timer frame | `0x17c2_0000` | `0x1000` | [`sdmmagpie.dtsi` L815](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie.dtsi#L815) |
| MDSS MDP | `0x0ae0_0000` | `0x8_4208` | [`sdmmagpie-sde.dtsi` L16](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie-sde.dtsi#L16) |
| MDSS VBIF | `0x0aeb_0000` | `0x2008` | same |
| MDSS regdma | `0x0aea_c000` | `0x214` | same |
| DSI0 controller | `0x0ae9_4000` | `0x400` | same L404 |
| DISP_CC base | `0x0af0_8000` | 4 B | same |
| DSI0 PHY | `0x0ae9_4400` | `0x7c0` | same L502 |
| DSI0 dyn-refresh | `0x0ae9_4200` | `0x100` | same |
| DSI1 controller | `0x0ae9_6000` | `0x400` | secondary display; unused |
| DSI1 PHY | `0x0ae9_6400` | | secondary display; unused |

### 4.1 Interrupts

| Source | Interrupt | Notes |
|---|---|---|
| GIC | PPI 9 (maintenance), PPI 1/2/3/0 (arch timer) | `arm,armv8-timer`, 19.2 MHz |
| UFS HC | `GIC_SPI 265` | |
| SPMI | `GIC_SPI 481` | `qcom,ee = <0>`, channel 0 |
| Apps RSC | `GIC_SPI 5` | mailbox |
| AOP QMP | `GIC_SPI 389`, edge rising | |
| DWC3 | `GIC_SPI 133` | |
| TLMM | `GIC_SPI 208` | pinctrl summary IRQ |
| Timer frames | SPI 8/6 (frame 0), 9/10/11… disabled | |
| Display (DSI0) | MDP parent, hwirq 4 | `interrupts = <4 0>` on `mdss_mdp` |

### 4.2 Timer / clock

- Arch timer and timer frame run at **19.2 MHz** (`clock-frequency = <19200000>`).
- Frame 0 uses `0x17c2_1000` + `0x17c2_2000`; frames 1–3 are present but
  `status = "disabled"` (no wakeup timer). This is the same layout as sweet.
- RPMH/RSC is reached through `apps_rsc` (`0x1822_0000` + TCS at `0x1822_0d00`);
  `cmd-db` is at `0xc3f_000c` (inside the RPMh message RAM region).
- There is **no AOSS register node** in the DT. AOSS power/crash registers are
  accessed through the AOP QMP mailbox (`qmp_aop`, `0x0c30_0000`) and the
  `0x17c0_000c` IRQ register. Do not invent an AOSS base from other SoCs.

---

## 5. PMIC, PON, and keys

Downstream PMIC nodes (SPMI bus, USID in the unit address):

| Node | SPMI address | Role |
|---|---|---|
| `qcom,pm6150@0` | 0 | PM6150 primary: PON, charger, QG, RTC, regulators |
| `qcom,pm6150l@4` | 4 | PM6150L primary: GPIOs, LDOs, lab/ibb |
| `qcom,pm6150l@5` | 5 | PM6150L secondary: flash LED, PWM/LPG |

PON block is at **`0x800` on PM6150 (USID 0)**:
[`xiaomi/pm6150.dtsi` L1-31](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/xiaomi/pm6150.dtsi#L1-L31).

```dts
&spmi_bus {
    qcom,pm6150@0 {
        qcom,power-on@800 {
            interrupts = <0x0 0x8 0x0 IRQ_TYPE_NONE>,
                         <0x0 0x8 0x1 IRQ_TYPE_NONE>,
                         <0x0 0x8 0x4 IRQ_TYPE_NONE>,
                         <0x0 0x8 0x5 IRQ_TYPE_NONE>;
            interrupt-names = "kpdpwr", "resin",
                              "resin-bark", "kpdpwr-resin-bark";
            qcom,pon-dbc-delay = <62500>;
            qcom,pon_1 { /* KPDPWR */ ... };
            qcom,pon_3 { /* KPDPWR_RESIN */ ... };
        };
    };
};
```

Key mapping used by the downstream PMIC PON driver:

| PON | Pins | Linux key | Bring-up use |
|---|---|---|---|
| `pon_1` | KPDPWR | `KEY_POWER` | power / wake |
| `pon_2` | RESIN | `KEY_VOLUMEDOWN` | volume down |
| `pon_3` | KPDPWR + RESIN | reset (S2) | forced reset / EDL combo |
| — | PM6150L GPIO2, active low | `KEY_VOLUMEUP` | volume up |

Volume-up is a plain PM6150L GPIO key, not a PON:

```dts
&pm6150l_gpios {
    key_vol_up {
        key_vol_up_default: key_vol_up_default {
            pins = "gpio2";
            function = "normal";
            input-enable;
            bias-pull-up;
            power-source = <0>;
        };
    };
};

&soc {
    gpio_keys {
        compatible = "gpio-keys";
        vol_up {
            label = "volume_up";
            gpios = <&pm6150l_gpios 2 GPIO_ACTIVE_LOW>;
            linux,code = <KEY_VOLUMEUP>;
            debounce-interval = <15>;
            gpio-key,wakeup;
        };
    };
};
```

Source:
[`xiaomi-sdmmagpie-common.dtsi` L226-255](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/xiaomi/xiaomi-sdmmagpie-common.dtsi#L226-L255).
Mainline agrees (`gpio-keys` on `&pm6150l_gpios 2 GPIO_ACTIVE_LOW`,
[`sm7150-xiaomi-common.dtsi` L73-84](https://github.com/sm7150-mainline/linux/blob/fd78d17954a86ea6ceb0c535e618ea129e09f8dd/arch/arm64/boot/dts/qcom/sm7150-xiaomi-common.dtsi#L73-L84),
and `&pm6150_resin { linux,code = <KEY_VOLUMEDOWN>; }` L587).

**Porting note:** the existing `sweet_keys.c` already drives PON through SPMI.
The PON offset (`0x800`), USID (0), and key mapping are identical on sweet and
davinci. Volume-up on sweet is also PM6150L GPIO2 active-low, so no driver
change is needed.

---

## 6. Display

### 6.1 Panels present in the downstream DT

Two panels are compiled in and both are in the DSI display list:

| DT label | Panel name string | File |
|---|---|---|
| `dsi_ss_fhd_ea_f10_cmd` | `"ss ea fhd cmd dsi panel"`, model `"SS FHD EA CMD PANEL"` | [`dsi-panel-ss-fhd-ea-f10-cmd.dtsi` L20-21](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/xiaomi/davinci/dsi-panel-ss-fhd-ea-f10-cmd.dtsi#L20-L21) |
| `dsi_ss_fhd_eb_f10_cmd` | `"ss eb fhd cmd dsi panel"` | [`dsi-panel-ss-fhd-eb-f10-cmd.dtsi` L20-21](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/xiaomi/davinci/dsi-panel-ss-fhd-eb-f10-cmd.dtsi#L20-L21) |

Both are 1080×2340 AMOLED command-mode panels with identical timing
parameters:

```dts
qcom,mdss-dsi-panel-width = <1080>;
qcom,mdss-dsi-panel-height = <2340>;
qcom,mdss-dsi-h-front-porch = <64>;
qcom,mdss-dsi-h-back-porch = <64>;
qcom,mdss-dsi-h-pulse-width = <20>;
qcom,mdss-dsi-v-back-porch = <64>;
qcom,mdss-dsi-v-front-porch = <64>;
qcom,mdss-dsi-v-pulse-width = <20>;
qcom,mdss-dsi-panel-framerate = <60>;
qcom,mdss-dsi-panel-clockrate = <1100000000>;
qcom,mdss-dsi-panel-type = "dsi_cmd_mode";
qcom,mdss-dsi-bpp = <24>;
qcom,mdss-dsi-traffic-mode = "burst_mode";
```

- 4 DSI data lanes (`lane-0-state` … `lane-3-state`), no DSC.
- PHY timings `[00 24 0A 0A 26 25 09 0A 06 02 04 00]`, topology `<1 0 1>`.
- Physical panel size 68 mm × 147 mm.
- EA backlight range 4…2047; EB 256…4095; both use `bl_ctrl_dcs`
  (DCS brightness, no PWM/backlight GPIO).
- Backlight/panel supplies use `dsi_panel_pwr_supply_labibb_amoled`:
  `vddio` 1.8–1.904 V, `vdda-3p3` 3.0 V. The actual AMOLED rails are
  PM6150L lab/ibb.
- Reset: **PM6150L GPIO9**, active-low (`qcom,platform-reset-gpio`).
- TE: **TLMM GPIO10** (`qcom,platform-te-gpio`).
- EA additionally uses `qcom,mdss-dsi-bl-dcs-type-ss-ea`,
  `qcom,samsung-prepare-hbm`, HDR primaries, and an ESD IRQ on **TLMM GPIO32**
  (falling, `0x2002`).
- Both panels are in `qcom,dsi-display-list` in
  [`xiaomi/sdmmagpie-sde-display.dtsi` L169-177](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/xiaomi/sdmmagpie-sde-display.dtsi#L169-L177).

`qcom,dsi-display-active` is set on `&dsi_sim_vid_display` in the shipped DT
([`davinci-sdmmagpie.dtsi` L260-262](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/xiaomi/davinci/davinci-sdmmagpie.dtsi#L260-L262)).
That is a leftover default for the simulator panel, **not** the real panel
selection. The bootloader selects the real panel via
`msm_drm.dsi_display0=` (see §3.1).

### 6.2 Which panel is which

The dumped unit has:

```text
msm_drm.dsi_display0=dsi_ss_fhd_ea_f10_cmd_display
```

The mainline device trees split davinci into two variants:

- `sm7150-xiaomi-davinci-samsung.dts` → `samsung,ams639rq08`
- `sm7150-xiaomi-davinci-visionox.dts` → `visionox,g1639fp106`

**[INF]** Downstream **EA = Samsung**, **EB = Visionox**. This is inferred from
the naming and from the fact that only the EA panel carries Samsung-specific
HBM commands (`qcom,samsung-prepare-hbm`, `bl-dcs-type-ss-ea`); it is *not*
stated anywhere. Both downstream names start with "ss", so the "ss" prefix is
not evidence by itself. **[?]**

Mainline gates the panel purely on the `compatible` string, while downstream
uses the bootarg. The Visionox variant additionally sets
`touchscreen-inverted-x` and `touchscreen-inverted-y`.

### 6.3 Display controller addresses

See §4: MDP `0xae00000`, DSI0 ctrl `0xae94000`, DSI0 PHY `0xae94400`,
DISP_CC `0xaf08000`. DSI1 is present at `0xae96000` but unused on davinci.
Both panels are single-port, single-DSI (topology 1/0/1).

### 6.4 Splash / framebuffer

- Reserved region: `0x9c00_0000`, size **`0x0170_0000` = 24,117,248 B (23 MiB)**
  ([`sdmmagpie.dtsi` L635-638](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie.dtsi#L635-L638)).
- Actual framebuffer used by the port: `1080 * 2340 * 4 = 10,108,800 B`
  (9.64 MiB), pixel format `a8r8g8b8`, stride `1080*4`, height 2340.
- Mainline override:
  [`sm7150-xiaomi-davinci.dtsi` L23-29 and L222-224](https://github.com/sm7150-mainline/linux/blob/fd78d17954a86ea6ceb0c535e618ea129e09f8dd/arch/arm64/boot/dts/qcom/sm7150-xiaomi-davinci.dtsi#L23-L29)
  sets both `&cont_splash_mem` and `&framebuffer` to `1080*2340*4`.
  Mainline's common davinci/sweet default is `1080*2400*4`; the device file
  overrides the height to 2340.
- Do **not** size the XNU framebuffer descriptor from `0x1700000`; that is the
  reserved aperture, not the used image. Keep using 1080×2340×4.
- The reserved region ends at `0x9d700000`, exactly where `dfps_data_region`
  starts. No overlap.

---

## 7. Touchscreen

Goodix, not FocalTech. Downstream compatible `goodix,gt9889` (the driver is the
GT9886 family); mainline uses `goodix,gt9886`.

Downstream node:
[`davinci-sdmmagpie.dtsi` L172-216](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/xiaomi/davinci/davinci-sdmmagpie.dtsi#L172-L216).

```dts
&qupv3_se7_i2c {
    status = "ok";
    goodix@5d {
        compatible = "goodix,gt9889";
        reg = <0x5d>;
        interrupt-parent = <&tlmm>;
        interrupts = <9 0x2800>;              /* GPIO9, flags 0x2800 */
        vtouch-supply = <&pm6150l_l6>;        /* L6C, 3.1 V */
        vtouch-load = <600000>;
        goodix,reset-gpio = <&tlmm 8 0x0>;
        goodix,irq-gpio = <&tlmm 9 0x2800>;
        goodix,avdd-gpio = <&tlmm 5 0x0>;     /* 1.8 V enable */
        goodix,irq-flags = <2>;               /* falling */
        goodix,panel-max-x = <1079>;
        goodix,panel-max-y = <2339>;
        goodix,panel-max-w = <127>;
        goodix,panel-max-p = <127>;
        goodix,cfg-name = "goodix_gt9886_cfg_f10.bin";
        sensor0 { goodix,fw-name = "goodix_gt9886_fw_f10.bin"; goodix,x2x; goodix,y2y; };
        sensor1 { goodix,fw-name = "goodix_gt9886_fw_f10.bin"; };
    };
};
```

| Signal | Pin / resource |
|---|---|
| I2C bus | QUPv3 SE7, `i2c@0xa84000`, 100 kHz |
| I2C address | `0x5d` (7-bit) |
| IRQ | TLMM **GPIO9** (downstream `irq-flags=2` falling; mainline `IRQ_TYPE_LEVEL_LOW`) |
| Reset | TLMM **GPIO8**, active-low |
| AVDD enable | TLMM **GPIO5** (1.8 V rail switch) |
| Analog supply | **PM6150L L6** (`pm6150l_l6`, LDO6 / `ldoc6`), 3.0–3.1 V |
| Coordinates | X 0–1079, Y 0–2339 (1080×2340) |
| Pressure | 0–127 |
| Firmware/config | `goodix_gt9886_fw_f10.bin`, `goodix_gt9886_cfg_f10.bin` |
| Pull-ups | GPIO8 and GPIO9 |

Mainline equivalent:
[`sm7150-xiaomi-davinci.dtsi` L272-285](https://github.com/sm7150-mainline/linux/blob/fd78d17954a86ea6ceb0c535e618ea129e09f8dd/arch/arm64/boot/dts/qcom/sm7150-xiaomi-davinci.dtsi#L272-L285):

```dts
&i2c7 {
    touchscreen: goodix@5d {
        compatible = "goodix,gt9886";
        reg = <0x5d>;
        interrupts-extended = <&tlmm 9 IRQ_TYPE_LEVEL_LOW>;
        reset-gpios = <&tlmm 8 GPIO_ACTIVE_LOW>;
        avdd-supply = <&vreg_l6c_3p0>;
        touchscreen-size-x = <1080>;
        touchscreen-size-y = <2340>;
    };
};
```

`vreg_l6c_3p0` is deliberately tightened to **3.0–3.1 V** in
[`sm7150-xiaomi-common.dtsi` L427-435](https://github.com/sm7150-mainline/linux/blob/fd78d17954a86ea6ceb0c535e618ea129e09f8dd/arch/arm64/boot/dts/qcom/sm7150-xiaomi-common.dtsi#L427-L435)
with a comment that this is required for reliable touch init. Downstream sets
the rail's min to 1.648 V, max 3.1 V (shared with other loads), init 1.648 V
in LPM; the touch driver/init programs 3.1 V before use. See
[`sdmmagpie-regulator.dtsi` L646-653](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie-regulator.dtsi#L646-L653).

**Not** LDO11, **not** FocalTech. If existing sweet code uses LDO11 or a
FocalTech address, it will not work on davinci.

---

## 8. UFS

Downstream node:
[`sdmmagpie.dtsi` L2281+](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/sdmmagpie.dtsi#L2281).

```dts
ufshc_mem: ufshc@1d84000 {
    compatible = "qcom,ufshc";
    reg = <0x1d84000 0x3000>, <0x1d90000 0x8000>;  /* HC + ICE */
    reg-names = "ufs_mem", "ufs_ice";
    interrupts = <0 265 0>;
    phys = <&ufsphy_mem>;
    phy-names = "ufsphy";
    lanes-per-direction = <1>;
    dev-ref-clk-freq = <0>;   /* comment: 19.2 MHz */
    spm-level = <5>;          /* Xiaomi overrides to 3 */
    ...
};
```

- **One lane per direction** (2 total), UFS 2.x geometry.
- Controller at `0x1d84000` (size `0x3000`), ICE at `0x1d90000` (size `0x8000`).
- PHY at `0x1d87000`, compatible `qcom,ufs-phy-qmp-v3`.
- IRQ SPI 265.
- `spm-level = <3>` via
  [`xiaomi/sdmmagpie.dtsi` L27](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/xiaomi/sdmmagpie.dtsi#L27).
- Supplies ([`xiaomi-sdmmagpie-common.dtsi` L98-124](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/xiaomi/xiaomi-sdmmagpie-common.dtsi#L98-L124)):

| Rail | Regulator | Voltage |
|---|---|---|
| `vcc` | PM6150 L19 | 2.95–2.96 V |
| `vccq2` | PM6150 L12 | 1.75–1.95 V |
| `vdda-phy` | PM6150 L4 | 0.88 V |
| `vdda-pll` / `vddp-ref-clk` | PM6150L L3 | 1.2 V |
| `vdd-hba` | `ufs_phy_gdsc` | fixed |

- Mainline compatible list: `qcom,sm7150-ufshc`, `qcom,ufshc`,
  `jedec,ufs-2.0`, still 1 lane/direction.
- Device class is UFS 2.0/2.1. **The actual negotiated gear (PWM/G1…G3,
  HS-G1…G3) is chosen at runtime and is not in any DT. [?]** Read it from the
  UFS host controller after link-up rather than hardcoding.

The existing `drv/sweet_ufs.c` uses `0x1d84000`, `1d84000.ufshc`, SPI 265, and
1 lane — all identical on davinci.

---

## 9. USB

- Wrapper `ssusb@a600000`, size `0x10_0000`, compatible `qcom,dwc-usb3-msm`.
- DWC3 core `dwc3@a600000`, reg size `0xcd00`, IRQ SPI 133.
- **QUSB2 PHY is at `0x088e_2000`**, size `0x400`, plus efuse `0x0078_0200`
  and refgen `0x088e_7014`. `0xa600000` is the USB3/DWC3 controller, not the
  PHY. (This is a common mix-up when porting from other Qualcomm trees.)
- QMP USB/DP combo PHY `0x088e_8000`, size `0x3000`.
- davinci disables the QMP-DP PHY and forces high-speed:

```dts
&usb0 {
    dwc3@a600000 {
        usb-phy = <&qusb_phy0>, <&usb_nop_phy>;
        maximum-speed = "high-speed";
    };
};

&usb_qmp_dp_phy {
    status = "disabled";
};
```

Source:
[`davinci-sdmmagpie.dtsi` L151-163](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/xiaomi/davinci/davinci-sdmmagpie.dtsi#L151-L163).
The bootloader passes `androidboot.usbcontroller=a600000.dwc3`.

**Porting note:** do not enable SuperSpeed on davinci; the board only wires the
USB 2.0 PHY and uses a no-op PHY for the second lane. Model the controller as
high-speed only.

---

## 10. davinci vs sweet

| Feature | sweet (Redmi Note 10 Pro / Pro Max) | davinci (Mi 9T / K20) |
|---|---|---|
| SoC | SM7150 family (SD732G), msm-id 365 | SM7150-AA (SD730), msm-id 365 (same ID) |
| Downstream board-id | 46 | **39** |
| Mainline board-id | 46 | **40** |
| RAM in dump | 8 GB: 4 GiB @ 0x8000_0000 + 0xFBB0_0000 @ 0x1_8000_0000 | 6 GB: 2 GiB @ 0x8000_0000 + 0xFCC0_0000 @ 0x1_0000_0000 |
| Front camera | fixed (punch-hole) | **pop-up**, TI DRV8846 motor |
| Hall sensor | — | **AKM09970** (pop-up position) |
| Charger pump | — | **SMB1390** @ I2C 0x10 |
| Speaker amp | — | **TFA9874** @ I2C4 0x34 |
| Battery | **5020 mAh** (K6) | **4000 mAh** F10 (Coslight / Sunwoda) |
| Panel | **1080×2400** AMOLED, video mode, DSC, 120 Hz | **1080×2340** AMOLED, cmd mode, no DSC, 60 Hz (EA/EB) |
| Touch | **FocalTech FTS_K6** @ I2C 0x38, L11 | **Goodix GT9886/GT9889** @ I2C 0x5d, L6 |
| Splash region | `0x9c000000` / `0x1700000` | same |
| Reserved memory | identical | identical |
| UFS / GIC / SPMI / RPMh / IMEM / PSHOLD / USB | identical | identical |

The display and touch differences are the two that most affect the existing port:

- **Panel height is 2340 on davinci but 2400 on sweet.** The sweet panel is a
  120 Hz video-mode DSC panel (`dsi_k6_38_0c_0a_fhd_dsc_video_display`); the
  davinci panels are 60 Hz command-mode, no DSC. Do not reuse sweet's
  `1080×2400` framebuffer dimensions or its video-mode timing.
- **Touch is a different vendor and bus.** Sweet uses FocalTech `fts_K6` at
  I2C `0x38` with `pm6150l_l11`; davinci uses Goodix at `0x5d` with
  `pm6150l_l6`. The downstream driver binary names (`goodix_gt9886_*`) and the
  mainline `goodix,gt9886` binding both point at Goodix on davinci.

### 10.1 Pop-up camera motor

[`davinci-sdmmagpie.dtsi` L503-529](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/xiaomi/davinci/davinci-sdmmagpie.dtsi#L503-L529):

```dts
&pm6150l_pwm { status = "ok"; };

&soc {
    ti,drv8846@0 {
        compatible = "ti,drv8846";
        pwms = <&pm6150l_pwm 1 1000000>;      /* PWM ch1, 1 ms period */
        motor,gpio-mode0 = <&tlmm 91 0x00>;
        motor,gpio-mode1 = <&tlmm 66 0x00>;
        motor,gpio-sleep = <&tlmm 88 0x00>;
        motor,gpio-dir = <&tlmm 55 0x00>;
        motor,gpio-pwren = <&tlmm 90 0x00>;
        motor,rampup-pwm-period-ns = <625000>;
        motor,rampup-duration-ms = <50>;
        motor,high-pwm-period-ns = <52083>;    /* ~19.2 kHz */
        motor,high-duration-ms = <720>;
        motor,rampdown-pwm-period-ns = <625000>;
        motor,rampdown-duration-ms = <50>;
        motor,step-mode = <2>;
        pinctrl-0 = <&pwm_out_gpio10_default &motor_gpio_default &motor_gpio_fault>;
        status = "ok";
    };
};
```

The front camera is hidden until the motor is raised; XNU needs this only if
the front camera is to be used, but the Hall sensor must not be mistaken for a
cover/accessory input.

### 10.2 Hall sensor (pop-up position)

[`davinci-sdmmagpie.dtsi` L114-135](https://github.com/LineageOS/android_kernel_xiaomi_sm6150/blob/e03e5ba22586be70673afb5d3c3f70510524e658/arch/arm64/boot/dts/qcom/xiaomi/davinci/davinci-sdmmagpie.dtsi#L114-L135):

```dts
&qupv3_se9_i2c {
    status = "ok";
    akm09970@c {
        compatible = "akm,akm09970";
        reg = <0xC>;
        interrupts = <120 0>;                  /* note: DT says 120, */
        akm,gpio-reset = <&tlmm 64 0x00>;      /*       while the IRQ  */
        akm,gpio-irq = <&tlmm 93 0x00>;        /*       property says 93 */
        akm,measure-freq-hz = <100>;
        vdd-supply = <&pm6150l_l8>;
        status = "ok";
    };
};
```

The `interrupts = <120 0>` vs `akm,gpio-irq = <93>` mismatch is present in the
downstream source; the driver uses the GPIO property, so **GPIO93** is the
functional IRQ. **[DT, with a source inconsistency]**

### 10.3 Charger pump and amp

- `smb1390@0x10` on QUPv3 **SE9** (`i2c@0xa8c000`; the `smb1390.dtsi` include is
  inside `&qupv3_se9_i2c` alongside the Hall sensor), compatible
  `qcom,smb1390-charger-psy`, IRQ via `smb_stat_default`, die temp on
  `pm6150l_vadc ADC_AMUX_THM2`. Mainline calls this bus `i2c9`.
- `tfa9874@0x34` on mainline `i2c4` = **`i2c@0x890000`** (downstream SE4),
  reset TLMM 12, IRQ TLMM 56. Mainline models it as the primary speaker DAI.
- Battery data: F10 4000 mAh, two packs (`f10_coslt`, Sunwoda).

### 10.4 USB difference

davinci forces high-speed and disables QMP-DP (§9). Check sweet's DT before
carrying over a SuperSpeed configuration.

### 10.5 Splash size

Same reserved region (`0x9c000000`, `0x1700000`), but **not the same framebuffer
size**: davinci uses 1080×2340×4 = 9.64 MiB, sweet uses 1080×2400×4 = 9.89 MiB
inside that reservation. The davinci ADT/fbcon must use height 2340; mainline's
common default of 2400 is overridden to 2340 for davinci.

---

## 11. Existing unusual-boot / mainline work

- **sm7150-mainline** maintains full davinci DTs in
  [`sm7150-mainline/linux`](https://github.com/sm7150-mainline/linux), with
  Samsung and Visionox variants, plus a `firmware-xiaomi-davinci` package and
  the `downstream-fdt` dumps used as ground truth here.
- **postmarketOS** has a generic `qcom-sm7150` port that covers davinci
  (mainline kernel + initramfs). The wiki is bot-protected, but the device
  package and DTs are public in the pmaports repo.
- **No U-Boot board** for sm7150/davinci and **no UEFI / Windows-on-ARM**
  davinci port was found. The existing approach (custom ADT + shim + XNU) is
  not duplicating known work.
- No public "unusual boot" exploit path is needed: the bootloader is unlocked
  and the port boots via the standard Android boot image / DTBO flow.

---

## 12. Corrections and follow-ups for the existing port

These are discrepancies found while compiling this reference. They matter
because the port has so far only been built, not run on a Mi 9T.

1. **TLMM base in `sweet_touch.c`** (carried in
   `xnu/patches/0060-sweet-keys-touch-drivers.patch`). The original driver
   defined `TOUCH_NORTH_PA 0x03900000u /* DT TLMM + NORTH (0x500000) */` and
   computes GPIO config as `n * 0x1000` from that base. Both davinci and
   sweet DTs put TLMM at **`0x0340_0000`** with size `0xdc2000`, and the live
   FDT agrees. **Fixed in patch 0082**: the touch ADT node gained
   `tlmm-base`, set to `0x0340_0000` for davinci; sweet keeps `0x0390_0000`
   so the one board known to work on hardware is unchanged.
2. **davinci touch GPIOs differ from the old handoff claim.** The earlier
   NOTES.md text said "TLMM 6/7/8/9 identical on davinci" (now corrected).
   Actual davinci: **AVDD enable GPIO5**, **reset GPIO8**, **IRQ GPIO9**.
   GPIO6/7 are the QUP11 I2C SDA/SCL function, i.e. the touch bus itself;
   GPIO10 is the panel TE line, not a touch pin.
3. **Touch supply is PM6150L L6 (`ldoc6`), 3.0–3.1 V**, not LDO11. The current
   driver's comment says "an already powered L11C rail"; sweet uses L11C, but
   davinci's touch node uses `pm6150l_l6`. Repoint the rail before touching
   hardware.
4. **Panel selection must be passed explicitly.** The real panel is chosen by
   the `msm_drm.dsi_display0=` bootarg (EA or EB), and `dsi-display-active` on
   `dsi_sim_vid_display` is a decoy. The port should carry the panel choice
   from the bootargs/FDT rather than relying on the DT active flag.
5. **Upper DDR base for 6 GB is `0x1_0000_0000` + `0xFCC0_0000`**, not sweet's
   `0x1_8000_0000` + `0xFBB0_0000`. `tools/mkadt.py` already has this right for
   the davinci profile; do not regress it when unifying profiles.
6. **Splash uses 1080×2340**, even though the region is 23 MiB. Keep the
   framebuffer descriptor at `1080*2340*4`.
7. **QUSB2 PHY base is `0x088e2000`.** If any bring-up code pokes
   `0xa600000+offset` expecting the PHY, it is writing into the DWC3 core.
8. **Do not hardcode UFS gear.** Only lane count (1/direction), ref clock
   (19.2 MHz), and SPM level (3) are known from DT.
9. **AOSS has no register block in DT.** Use the AOP QMP mailbox at
   `0x0c300000`; do not add an invented AOSS base.
10. **PMIC USIDs**: PM6150 = 0 (PON at `0x800`), PM6150L = 4 and 5. The second
    PM6150L node (5) is the flash/PWM block; PON is only on PM6150.

---

## 13. Explicitly unconfirmed

| Item | Status / best estimate |
|---|---|
| UFS negotiated gear | Runtime; device is UFS 2.0/2.1, 1 lane/dir. Read from HC after link-up. |
| EA = Samsung, EB = Visionox | Strong inference, not documented. Dumped unit is EA. Both downstream names start with "ss". |
| 8 GB davinci RAM split | No dump. If sweet-like: 4 GiB @ `0x8000_0000` + `0xFBB0_0000` @ `0x1_8000_0000`. |
| Top 52 MiB gap (`0x1_FCC0_0000`–`0x2_0000_0000`) | Absent from `/memory` and reserved-memory. Likely firmware/ABL reserved or unusable; do not map. |
| Exact PM6150L L6 voltage at boot | DT range 1.648–3.1 V, init 1.648 V LPM; touch needs 3.1 V. Use 3.0–3.1 V. |
| AKM IRQ number | DT `interrupts` says 120, GPIO property says 93. GPIO93 is what the driver uses. |
| Panel `dsi-display-active` semantics | The flag on `dsi_sim_vid_display` is a leftover; real selection is the bootarg. |
| `androidboot.dtbo_idx` panel mapping | Dumped EA unit uses `dtbo_idx=1`, `dtb_idx=0`. Likely selects the panel/hwvariant DTBO; the EB index is unconfirmed. |
| Board-id 39 vs 40 | Both are real: downstream overlay 39, mainline 40. Match the bootloader's expected value per kernel tree. |

---

## 14. Source index

Downstream (all at commit `e03e5ba22586be70673afb5d3c3f70510524e658`):

- `arch/arm64/boot/dts/qcom/sdmmagpie.dtsi` — SoC bases: GIC, timer, GCC, IMEM,
  PSHOLD, SPMI, QMP, UFS, PDC, reserved-memory defaults.
- `arch/arm64/boot/dts/qcom/sdmmagpie-pinctrl.dtsi` — TLMM.
- `arch/arm64/boot/dts/qcom/sdmmagpie-sde.dtsi` — MDSS/DSI.
- `arch/arm64/boot/dts/qcom/sdmmagpie-usb.dtsi` — USB/DWC3/QUSB2/QMP.
- `arch/arm64/boot/dts/qcom/xiaomi/sdmmagpie.dtsi` — UFS `spm-level`, boot
  devices, fstab.
- `arch/arm64/boot/dts/qcom/xiaomi/xiaomi-sdmmagpie-common.dtsi` — UFS
  supplies, volume-up key, Xiaomi reserved-memory additions, LDO tightening.
- `arch/arm64/boot/dts/qcom/xiaomi/sdmmagpie-sde-display.dtsi` — panel list,
  panel supply entries, PHY timings.
- `arch/arm64/boot/dts/qcom/xiaomi/davinci/davinci-sdmmagpie.dtsi` — davinci
  overrides: touch, panel GPIOs, TZ size, motor, Hall, charger, USB.
- `arch/arm64/boot/dts/qcom/xiaomi/davinci/dsi-panel-ss-fhd-ea-f10-cmd.dtsi`
- `arch/arm64/boot/dts/qcom/xiaomi/davinci/dsi-panel-ss-fhd-eb-f10-cmd.dtsi`
- `arch/arm64/boot/dts/qcom/davinci-sdmmagpie-overlay.dts` — msm-id/board-id.
- `arch/arm64/boot/dts/qcom/xiaomi/pm6150.dtsi` — PON overrides.

Mainline (commit `fd78d17954a86ea6ceb0c535e618ea129e09f8dd`):

- `arch/arm64/boot/dts/qcom/sm7150-xiaomi-davinci.dtsi`
- `arch/arm64/boot/dts/qcom/sm7150-xiaomi-davinci-samsung.dts`
- `arch/arm64/boot/dts/qcom/sm7150-xiaomi-davinci-visionox.dts`
- `arch/arm64/boot/dts/qcom/sm7150-xiaomi-common.dtsi`

Dumps:

- <https://github.com/sm7150-mainline/downstream-fdt/blob/master/fdt-davinci>
- <https://github.com/sm7150-mainline/downstream-fdt/blob/master/fdt-sweet>

LineageOS device trees:

- <https://github.com/LineageOS/android_device_xiaomi_davinci/tree/lineage-23.2>
- <https://github.com/LineageOS/android_device_xiaomi_sm6150-common/tree/lineage-23.2>

Local working copies used while checking this document:

- `/tmp/opencode/kernel_sm6150` (downstream kernel)
- `/tmp/opencode/davinci_fdt.txt` (decompiled dumped FDT)
- `/tmp/opencode/pmos_linux` (mainline v7.2)
- `/tmp/opencode/fdt.py` (FDT parser used because `dtc` is unavailable)
