@echo off
REM Pull the SWEET persistent console log (kernel patch 0047) from a phone
REM booted into recovery with adb root.  Windows counterpart of
REM tools/sweet-log-pull.sh, for use from cmd.exe / PowerShell.
REM
REM   tools\sweet-log-pull.cmd [OUT.txt]
REM
REM Reads only: the last 1025 blocks (4 KiB) of the userdata partition.
setlocal enabledelayedexpansion

set OUT=%~1
if "%OUT%"=="" set OUT=logs\boot.txt

where adb >nul 2>nul || (echo Error: adb not found in PATH & exit /b 1)
where python >nul 2>nul || (echo Error: python not found in PATH & exit /b 1)

set HERE=%~dp0
set BIN=%OUT%.bin
if not exist logs mkdir logs

REM Resolve the userdata block device (by-name is stable across kernels).
for /f "usebackq delims=" %%d in (`adb shell "for d in /dev/block/by-name/userdata /dev/block/bootdevice/by-name/userdata; do [ -e $d ] && readlink -f $d && break; done"`) do set DEV=%%d
if "%DEV%"=="" (echo Error: userdata block device not found & exit /b 1)
echo userdata block device: %DEV%

for /f "usebackq delims=" %%s in (`adb shell blockdev --getsize64 %DEV%`) do set BYTES=%%s
echo partition size: %BYTES% bytes

set /a SKIP=%BYTES%/4096 - 1025
echo reading blocks %SKIP%.. (last 4100 KiB)

adb exec-out "dd if=%DEV% bs=4096 skip=%SKIP% count=1025 2>/dev/null" > "%BIN%"
if errorlevel 1 (echo Error: dd failed & exit /b 1)

python "%HERE%sweet-log.py" "%BIN%" "%OUT%"
if errorlevel 1 (echo Error: sweet-log.py failed & exit /b 1)

echo.
echo log written to %OUT%  (raw area kept in %BIN%)
endlocal
