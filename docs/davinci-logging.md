# Reaching the kernel log on davinci (Mi 9T)

The kernel keeps a persistent 4 MiB console ring in the **last 4100 KiB of the
`userdata` partition** (patch `0047-sweet-persistent-console-log.patch`). Our
root image is only the first 16 GiB of a ~48 GiB partition, so the ring sits in
untouched space after it and survives every reflash of the image.

Two ways to read it:

## A. Recovery + adb (works even if boot dies before USB)

1. Get an OrangeFox (or any recovery with `adb root`) image for **davinci**. It
   is not in git; drop it at `recovery/recovery.img`.
2. `fastboot boot recovery/recovery.img` — temporary, nothing is flashed.
3. Wait for the recovery, then on Windows:

   ```
   tools\sweet-log-pull.cmd logs\boot.txt
   ```

   (On Linux, `tools/sweet-log-pull.sh logs/boot.txt`.)

4. `adb reboot bootloader` to go back to fastboot.

The raw 4100 KiB area is kept as `logs/boot.txt.bin`; `tools/sweet-log.py`
decodes it against the `SWEETLOG` header.

## B. Live log over USB Ethernet (no recovery image needed)

Boot an image whose cmdline contains `sweetusb=2`. The kernel then streams the
console as UDP to `192.168.7.1:5140` every 100 ms (patch
`0077-sweet-usb-live-log.patch`), starting with the last 64 KiB. The phone
presents itself as a CDC-ECM adapter (host MAC `02:00:5e:77:ee:01`) and takes
`192.168.7.2/24`.

Ready-made image: `shim/out/shim-boot-davinci-usb.img` (identical to
`shim-boot-davinci.img` except `sweetusb=2` is appended to the cmdline;
SHA256 `c47835aac215c243152894b1908d559c7bfc6e2176c98193476785e32ee95728`).

On Linux: `tools/sweet-usbnet.sh logs/live.txt`.
On Windows: set the phone's USB-Ethernet adapter to `192.168.7.1/24`, then run
`tools\sweet-live-log.cmd logs\live.txt` (uses `ncat -l -u -k 5140`). Check the
link with `ping 192.168.7.2`.

This only helps if the hang happens **after** USB comes up; a hang before that
needs method A.

## Reading the log

`tools/sweet-crash.py` symbolicates the `CRASH` backtraces against the shared
cache in the root image. Useful greps:

```
grep -E 'SWEET (FB|UFS|TOUCH|USB)' logs/boot.txt
grep -E 'launchd|exec |CRASH|panic' logs/boot.txt | tail -50
```
