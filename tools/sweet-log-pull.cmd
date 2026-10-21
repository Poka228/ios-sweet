@echo off
REM Pull the SWEET persistent console log (kernel patch 0047) from a phone
REM booted into recovery with adb root.  Windows counterpart of
REM tools/sweet-log-pull.sh.
REM
REM   tools\sweet-log-pull.cmd [OUT.txt]
REM
REM Reads only: the last 1025 blocks (4 KiB) of the userdata partition.
REM
REM All arithmetic is done in Python: cmd.exe set /a is 32-bit (the ~51 GiB
REM partition size overflows it) and the recovery shell's $(( )) is 32-bit
REM too, so neither can compute the block offset.
setlocal

set OUT=%~1
if "%OUT%"=="" set OUT=logs\boot.txt

where adb >nul 2>nul || (echo Error: adb not found in PATH & exit /b 1)
where python >nul 2>nul || (echo Error: python not found in PATH & exit /b 1)

if not exist logs mkdir logs

python "%~dp0sweet-log-pull.py" "%OUT%"
if errorlevel 1 exit /b 1
endlocal
