@echo off
setlocal enabledelayedexpansion
rem ============================================================================
rem  Nord 6 port: flash stock ColorOS 17.0.0.100 FIRMWARE to the current slot.
rem  Fixes the "Hey Google" ADSP crash (wired Android Auto reconnect loop).
rem  - NO data wipe: no -w, no erase, no format, no "flashing unlock_critical".
rem  - Root stays: boot / init_boot / vendor_boot are never written.
rem  - modem is flashed from the BOOTLOADER (fastbootd cannot open it),
rem    the other 24 from FASTBOOTD (the bootloader refuses critical partitions).
rem  Start with the phone booted in Android (USB debugging on) or in the bootloader.
rem    flash_firmware.bat flashes images\ (the folder make_firmware_fix.py writes)
rem ============================================================================
cd /d "%~dp0"
set "PT=%~dp0"
set "ADB=adb"
set "FB=fastboot"
if exist "%PT%adb.exe" set "ADB=%PT%adb.exe"
if exist "%PT%fastboot.exe" set "FB=%PT%fastboot.exe"
where "%FB%" >nul 2>&1 || if not exist "%FB%" ( echo fastboot.exe not found: put it in this folder or on PATH. & goto :fail )
where "%ADB%" >nul 2>&1 || if not exist "%ADB%" ( echo adb.exe not found: put it in this folder or on PATH. & goto :fail )
set "SRC=images"
set PARTS=xbl xbl_config xbl_ramdump abl tz hyp keymaster devcfg qupfw uefi uefisecapp imagefv shrm cpucp cpucp_dtb aop aop_config bluetooth featenabler pvmfw soccp_debug soccp_dcd engineering_cdt oplusstanvbk
for %%p in (modem %PARTS%) do if not exist "%SRC%\%%p.img" ( echo MISSING %SRC%\%%p.img & goto :fail )
echo Source: %SRC%
echo.

rem ---- 1. get to the bootloader -------------------------------------------
"%FB%" devices 2>nul | findstr /r "fastboot$" >nul
if errorlevel 1 (
  echo Rebooting the phone to the bootloader...
  "%ADB%" reboot bootloader || ( echo No phone found over adb or fastboot. & goto :fail )
)
call :waitfb no || goto :fail
call :slot || goto :fail
echo Current slot: !SLOT!

rem ---- 2. modem from the bootloader ----------------------------------------
echo [bootloader] modem_!SLOT!
"%FB%" flash modem_!SLOT! "%SRC%\modem.img" || ( echo FAILED on modem. Nothing else was written. & goto :fail )

rem ---- 3. the rest from fastbootd ------------------------------------------
echo Switching to fastbootd...
"%FB%" reboot fastboot
call :waitfb yes || goto :fail
for %%p in (%PARTS%) do (
  echo [fastbootd] %%p_!SLOT!
  "%FB%" flash %%p_!SLOT! "%SRC%\%%p.img" || ( echo FAILED on %%p. Do NOT reboot - run this script again or ask for help. & goto :fail )
)
echo.
echo All 25 firmware images flashed to slot !SLOT!. Rebooting to Android...
"%FB%" reboot
echo Done. After boot: Hey Google ^> Voice Match ^> Retrain voice model.
pause
exit /b 0

:waitfb
rem %1 = no (bootloader) or yes (fastbootd)
for /l %%i in (1,1,60) do (
  for /f "tokens=2 delims=: " %%u in ('"%FB%" getvar is-userspace 2^>^&1 ^| findstr /b "is-userspace"') do (
    if /i "%%u"=="%~1" exit /b 0
  )
  timeout /t 2 /nobreak >nul
)
echo Phone did not show up in fastboot (is-userspace=%~1). Check the USB driver (nord6_fastboot_driver).
exit /b 1

:slot
set "SLOT="
for /f "tokens=2 delims=: " %%s in ('"%FB%" getvar current-slot 2^>^&1 ^| findstr /b "current-slot"') do set "SLOT=%%s"
if not defined SLOT ( echo Could not read the current slot. & exit /b 1 )
exit /b 0

:fail
echo.
echo Stopped. Your data was not touched.
pause
exit /b 1
