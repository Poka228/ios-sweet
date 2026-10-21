@echo off
REM Capture the live kernel console the phone streams over USB Ethernet
REM (kernel patches 0075-0077; boot image must have sweetusb=2).
REM The phone presents a CDC-ECM adapter (host MAC 02:00:5e:77:ee:01, which
REM Windows may show as an "RNDIS/CDC-ECM" or "USB Ethernet" adapter), takes
REM 192.168.7.2/24 and sends the console as UDP to 192.168.7.1:5140.
REM
REM   tools\sweet-live-log.cmd [OUT.txt]
REM
REM Requires: the phone booted with shim-boot-davinci-usb.img, and ncat.exe
REM (Nmap) or any UDP listener on port 5140.  Set the adapter's IPv4 address
REM to 192.168.7.1 / 255.255.255.0 first (see docs\davinci-logging.md).
setlocal

set OUT=%~1
if "%OUT%"=="" set OUT=logs\live.txt
if not exist logs mkdir logs

set NCAT=ncat
where ncat >nul 2>nul || set NCAT="C:\Program Files (x86)\Nmap\ncat.exe"

echo Listening on UDP 5140, appending to %OUT% ...
echo (Ctrl+C to stop.  ping 192.168.7.2 checks the link.)
echo.

%NCAT% -l -u -k 5140 >> "%OUT%"
endlocal
