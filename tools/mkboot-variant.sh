#!/usr/bin/env bash
# Build a named davinci (or sweet) boot-image variant in one step, without
# leaving the canonical shim-boot-<device>.img pointing at the variant.
#
#   tools/mkboot-variant.sh <variant> <kernel> <adt> "<cmdline>"
#
# e.g. tools/mkboot-variant.sh davinci-touch6 xnu/out/kernel.development.sweet \
#          shim/out/davinci.adt \
#          "debug=0xc serial=3 cpus=6 keepsyms=1 ... sweetsample=SpringBoard,backboardd"
#
# Writes shim/out/shim-boot-<variant>.img (+ .sha256) and shim/out/payload-<variant>.bin.
# shim/build.sh always emits out/shim-boot-<device>.img and does `cd shim`, so the
# script builds, captures the result, and moves it to the variant name; the
# canonical image is left untouched (it is saved and restored around the build).
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/.." && pwd)
cd "$root"

variant=${1:?usage: mkboot-variant.sh <variant> <kernel> <adt> "<cmdline>"}
kernel=${2:?kernel path}
adt=${3:?adt path}
cmdline=${4:?cmdline}

out=shim/out
payload="$out/payload-$variant.bin"
canonical="$out/shim-boot-davinci.img"
# Pick the board from the ADT path so sweet builds also work.
case "$adt" in
	*davinci*) device=davinci ;;
	*sweet*)   device=sweet ;;
	*) echo "cannot infer device from ADT '$adt'; name the file *davinci* or *sweet*" >&2; exit 1 ;;
esac

for f in "$kernel" "$adt" "$root/dtb/boot_unpacked/dtb"; do
	[ -f "$f" ] || { echo "missing $f" >&2; exit 1; }
done

mkdir -p "$out"
# Keep the current canonical image (hardlinked: cheap) so it survives the build.
saved=
if [ -f "$canonical" ]; then
	saved="$canonical.saved-$$"
	cp -p "$canonical" "$saved"
fi
restore() {
	[ -n "$saved" ] && mv -f "$saved" "$canonical" && echo "canonical restored: $canonical"
}
trap restore EXIT

echo "== payload =="
python3 tools/mkpayload.py "$kernel" "$adt" "$payload" --cmdline "$cmdline"

echo "== shim (DEVICE=$device) =="
# shim/build.sh does `cd shim`, so both the payload and PYTHONPATH must be absolute.
DEVICE="$device" PYTHONPATH="$root/build/mkbootimg-stub" bash shim/build.sh "$root/$payload"

built="$out/shim-boot-$device.img"
dest="$out/shim-boot-$variant.img"
mv -f "$built" "$dest"
sha256sum "$dest" | awk '{print $1"  "$2}' > "$dest.sha256"
sha256sum "$payload" | awk '{print $1"  "$2}' > "$payload.sha256"
echo "built: $dest"
ls -l "$dest" "$dest.sha256"
echo "cmdline: $cmdline"
