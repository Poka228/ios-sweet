#pragma once
/*
 * Per-device physical constants for the boot shim.
 *
 * build.sh selects the device with DEVICE=<profile> (default: sweet) and
 * passes -DDEVICE_<PROFILE>. Only values that differ between boards of the
 * same SoC family belong here; everything SoC-level (GIC, UFS, GENI, SPMI,
 * RPMh, IMEM, PSHOLD, 19.2 MHz timer) is identical on SM7150 boards and
 * stays in the .c/.h files that use it.
 *
 * The framebuffer is the ABL continuation-splash region: a linear
 * a8r8g8b8 buffer at the panel's native resolution (see the stock device
 * tree's /reserved-memory "cont_splash_region" or "splash" node). Verify
 * the values for a new board with tools/fdt-device.py on its stock
 * boot.img before booting.
 */

#if defined(DEVICE_DAVINCI)
/* Xiaomi Mi 9T (davinci, SM7150-AA), 1080x2340 AMOLED. */
#define DEVICE_NAME	"davinci"
#define FB_BASE		0x9c000000UL	/* reserved-memory cont_splash_region */
#define FB_W		1080
#define FB_H		2340
#else
/* Xiaomi Redmi Note 10 Pro (sweet, SM7150-AB), 1080x2400 AMOLED. */
#define DEVICE_NAME	"sweet"
#define FB_BASE		0x9c000000UL	/* reserved-memory cont_splash_region */
#define FB_W		1080
#define FB_H		2400
#endif

#define FB_STRIDE	(FB_W * 4)	/* a8r8g8b8, matches mainline simplefb */
#define FB_PHYS		FB_BASE
