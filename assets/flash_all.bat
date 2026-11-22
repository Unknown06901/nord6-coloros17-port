@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "HERE=%~dp0"
title OnePlus Nord 6 - ColorOS 17 Port Flasher

REM Every run logs each fastboot/adb command and its output to logs\<date_time>\flash_log.txt.
REM When something fails, phone info is added and the folder is zipped so the user can send it.
REM Log paths are relative (this folder is the current directory), so a folder name with
REM spaces or brackets can't break the commands that use them.
set TS=
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss" 2^>nul') do set "TS=%%t"
if not defined TS set "TS=run_%RANDOM%"
set "LOGDIR=logs\%TS%"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "LOG=%LOGDIR%\flash_log.txt"
set "RUNOUT=%LOGDIR%\last_command.tmp"
call :log_header

echo ========================================================
echo   OnePlus Nord 6 ColorOS 17 Port - Fastboot/TWRP FastbootD
echo ========================================================
echo   The port is flashed from the FastbootD of the TWRP recovery bundled in this folder
echo   ^(twrp_nord6.img^). It is installed first and stays as your recovery.
echo.
echo   1. Clean flash - first install (from stock OxygenOS 16 / ColorOS 17 or any other ROM).
echo      Flashes everything and WIPES ALL DATA.
echo.
echo   2. Dirty flash - update a phone that already runs this port.
echo      Flashes only the .img files in this folder and KEEPS your data,
echo      so a fix package can contain just the patched images.
echo      Do NOT use this coming from stock firmware or another ROM: it will not boot without a wipe.
echo.
echo   Both flash the stock ColorOS 17.0.0.100 firmware from the firmware folder too ^(no data loss^),
echo   needed for Android Auto and "Hey Google". Delete the firmware folder to skip it.
echo.
echo   3. Collect logs - the phone does not boot, or something is wrong after flashing.
echo      Saves phone info and logs to a zip file you can send to the developer.
echo.
choice /c 123 /n /m "Select 1, 2 or 3: "
if errorlevel 3 goto :collect
if errorlevel 2 (set MODE=dirty) else (set MODE=clean)
echo.
call :say Selected: %MODE% flash
echo.
set ROOT=none
if "%MODE%"=="clean" (
    echo   1. Root with KernelSU Next - the latest release is downloaded and the port's
    echo      init_boot is patched with it on this PC before flashing, needs internet.
    echo   2. No root.
    echo.
    choice /c 12 /n /m "Select 1 or 2: "
    if errorlevel 2 (set ROOT=none) else (set ROOT=ksu)
) else (
    echo   1. Keep root - init_boot is NOT flashed, your Magisk/KernelSU patched init_boot stays.
    echo   2. Root with KernelSU Next - latest release, the port's init_boot is patched with it
    echo      ^(also updates an older KernelSU Next^), needs internet.
    echo   3. No root - flashes the port's stock init_boot.img, this removes root.
    echo   Note: root that lives in boot.img, such as KernelSU GKI mode, is replaced
    echo   whenever this folder contains boot.img.
    echo.
    choice /c 123 /n /m "Select 1, 2 or 3: "
    if errorlevel 3 (set ROOT=remove) else if errorlevel 2 (set ROOT=ksu) else (set ROOT=keep)
)
call :say Selected: root %ROOT%
echo.
set GAPPS=standard
if exist "my_product_lite.img" (
    echo   Google apps:
    echo   1. Standard - all Google apps of the port, already without the usual bloat.
    echo   2. Minimal Google - only the Google app, Play Store, Google Play services and Android Auto,
    echo      plus what they and the phone need: Gboard, Google Messages, Speech Services, WebView.
    echo      Gmail, Chrome, Maps, Calendar, Gemini, Files, Wallet, GPay, Lens, Digital Wellbeing,
    echo      Google Contacts, TalkBack, ARCore and the other Google apps are not installed.
    echo      Any of them can be installed from Play Store later.
    echo.
    choice /c 12 /n /m "Select 1 or 2: "
    if errorlevel 2 (set GAPPS=minimal) else (set GAPPS=standard)
    call :say Selected: Google apps !GAPPS!
    echo.
)
if not "%ROOT%"=="keep" if not "%ROOT%"=="none" if not exist "init_boot.img" (
    call :say ERROR: this choice needs init_boot.img in this folder, it is missing.
    goto :abort
)
if not exist "twrp_nord6.img" (
    call :say ERROR: twrp_nord6.img is missing from this folder. It is needed to flash the port.
    goto :abort
)
set KSU_IMG=
if "%ROOT%"=="ksu" call :ksu_prepare || goto :abort
set BOOTIMGS=boot init_boot vendor_boot dtbo
REM firmware\: stock ColorOS 17.0.0.100 firmware. The OxygenOS 16 ADSP firmware crashes on the port's "Hey Google"
REM voice model (each crash drops charging and USB: wired Android Auto reconnect loop). modem is written from the
REM bootloader (FastbootD can't open it, the recovery has it mounted); the bootloader refuses the other, critical,
REM partitions without "flashing unlock_critical" (wipes), so they go from FastbootD. Both go to the current slot.
set FW=0
if exist "firmware\modem.img" set FW=1
set FWPARTS=xbl xbl_config xbl_ramdump abl tz hyp keymaster devcfg qupfw uefi uefisecapp imagefv shrm cpucp cpucp_dtb aop aop_config bluetooth featenabler pvmfw soccp_debug soccp_dcd engineering_cdt oplusstanvbk
if "%FW%"=="1" for %%p in (%FWPARTS%) do if not exist "firmware\%%p.img" (
    call :say ERROR: firmware\%%p.img is missing. Copy the whole firmware folder, or delete it to skip the firmware.
    goto :abort
)
if "%ROOT%"=="keep" set BOOTIMGS=boot vendor_boot dtbo

echo Make sure your phone is connected in FASTBOOT (Bootloader) mode
echo and fastboot.exe is inside this folder or on PATH.
pause

set LOGICAL=vendor odm vendor_dlkm system_dlkm system system_ext product my_product my_stock my_heytap my_region my_bigball my_manifest my_engineering my_company my_preload my_carrier
set HAS_LOGICAL=0
for %%p in (%LOGICAL%) do if exist "%%p.img" set HAS_LOGICAL=1
if "%GAPPS%"=="minimal" set HAS_LOGICAL=1
set FLASH_FAILED=0
if "%MODE%"=="clean" if not exist "system.img" (
    call :say ERROR: a clean flash needs the full image set, system.img is missing from this folder.
    goto :abort
)

echo.
call :say [1/5] Bootloader: disabling AVB verification and installing TWRP recovery...
call :wait_fastboot || (
    call :say ERROR: no phone in fastboot mode found. Check the USB cable and the fastboot driver.
    goto :abort
)
REM TWRP must be written from the bootloader. A phone that is already in some FastbootD (stock or
REM another recovery) is sent back to the bootloader first.
call :runq fastboot getvar is-userspace
findstr /c:"is-userspace: yes" "%RUNOUT%" >nul && (
    call :say The phone is in FastbootD, rebooting it to the bootloader first...
    call :run fastboot reboot bootloader
    timeout /t 8 /nobreak >nul
    call :wait_fastboot || (
        call :say ERROR: the phone did not come back in bootloader mode.
        goto :abort
    )
    call :runq fastboot getvar is-userspace
    findstr /c:"is-userspace: yes" "%RUNOUT%" >nul && (
        call :say ERROR: the phone is still in FastbootD. Hold Volume Down + Power to open the bootloader, then run this again.
        goto :abort
    )
)
REM vbmeta first: coming from stock firmware, AVB verification is still on and could refuse the
REM non-stock recovery.
for %%p in (vbmeta vbmeta_system vbmeta_vendor) do (
    if exist "%%p.img" call :run fastboot --disable-verity --disable-verification flash %%p %%p.img || set FLASH_FAILED=1
)
if "!FLASH_FAILED!"=="1" goto :failed
call :say Flashing TWRP to the recovery partition of the current slot...
call :run fastboot flash recovery twrp_nord6.img || goto :failed
if "%FW%"=="1" (
    call :say Flashing the ColorOS 17 firmware modem from the bootloader...
    call :run fastboot flash modem firmware\modem.img || goto :failed
)

echo.
call :say [2/5] Rebooting into TWRP FastbootD...
call :run fastboot reboot fastboot
echo Wait for the TWRP FastbootD screen on the phone ^(up to 2 minutes^)...
timeout /t 10 /nobreak >nul
call :wait_fastbootd || (
    call :say ERROR: the phone did not reach TWRP FastbootD. Nothing except vbmeta and recovery was changed.
    goto :failed
)
call :say TWRP FastbootD is ready.

echo.
call :say [3/5] TWRP FastbootD: flashing boot partitions...
if "%ROOT%"=="keep" call :say Skipping init_boot to keep root.
for %%p in (%BOOTIMGS%) do (
    set "IMG=%%p.img"
    if "%%p"=="init_boot" if defined KSU_IMG (
        set "IMG=!KSU_IMG!"
        call :say Flashing KernelSU Next patched init_boot.
    )
    if exist "!IMG!" call :run fastboot flash %%p "!IMG!" || set FLASH_FAILED=1
)
if "!FLASH_FAILED!"=="1" goto :failed
if "%FW%"=="1" (
    call :say TWRP FastbootD: flashing the rest of the ColorOS 17 firmware...
    for %%p in (%FWPARTS%) do call :run fastboot flash %%p firmware\%%p.img || set FLASH_FAILED=1
)
if "!FLASH_FAILED!"=="1" goto :failed

if "%HAS_LOGICAL%"=="0" (
    echo.
    call :say No logical partition images in this folder, skipping the super partition.
    goto :finish
)

echo.
call :say [4/5] TWRP FastbootD: freeing super partition space and flashing Logical Partitions...
echo Checking that the phone is in FastbootD...
call :runq fastboot getvar is-userspace
findstr /c:"is-userspace: yes" "%RUNOUT%" >nul || (
    call :say ERROR: the phone is not in FastbootD. The screen must show the FastbootD menu, not the bootloader.
    goto :failed
)

REM The phone can be on slot a or b (an OTA switches slots). Boot images went to the current slot
REM in step 1, so the logical partitions must go there too, never a hardcoded _a.
set SLOT=
call :runq fastboot getvar current-slot
for /f "usebackq tokens=1,2 delims=: " %%a in ("%RUNOUT%") do if "%%a"=="current-slot" set "SLOT=%%b"
if defined SLOT set "SLOT=!SLOT:_=!"
set OTHER=
if "!SLOT!"=="a" set OTHER=b
if "!SLOT!"=="b" set OTHER=a
if not defined OTHER (
    call :say ERROR: could not read the current slot from FastbootD, got "!SLOT!". Nothing in super was changed.
    goto :failed
)
call :say Current slot: !SLOT!

REM A pending/merging OTA keeps snapshot COW partitions in super; an old "adb remount" leaves "scratch".
REM Both eat the free space and cause "Not enough space to resize partition".
call :run fastboot snapshot-update cancel
call :runq fastboot delete-logical-partition scratch
for %%p in (%LOGICAL%) do (
    call :runq fastboot delete-logical-partition %%p_!OTHER!
    call :runq fastboot delete-logical-partition %%p_a-cow
    call :runq fastboot delete-logical-partition %%p_b-cow
)

REM Drop the current-slot partitions that are about to be reflashed, so their old sizes can't block the resize.
REM Partitions without an image here are left untouched (dirty flash with a partial fix package).
for %%p in (%LOGICAL%) do (
    call :pimg %%p
    if exist "!PIMG!" call :runq fastboot delete-logical-partition %%p_!SLOT!
)

REM Minimal Google: my_product comes from my_product_lite.img (see :pimg).
for %%p in (%LOGICAL%) do (
    call :pimg %%p
    if exist "!PIMG!" (
        call :say Flashing !PIMG! to %%p_!SLOT!, please wait ...
        call :runq fastboot create-logical-partition %%p_!SLOT! 0
        call :run fastboot flash %%p_!SLOT! "!PIMG!" || set FLASH_FAILED=1
    )
)
if "!FLASH_FAILED!"=="1" goto :failed

:finish
echo.
call :say [5/5] Flashing Complete. TWRP stays installed as the recovery.
if "%MODE%"=="dirty" goto :dirty

echo IMPORTANT: A clean flash of the port requires a Data Wipe (fastboot -w).
echo Press any key to wipe data and reboot, or close this window to skip wiping.
pause
call :run fastboot -w || (
    call :say ERROR: wiping data failed, the phone will not boot like this.
    goto :failed
)
call :run fastboot reboot
call :boot_help
if "%ROOT%"=="ksu" call :ksu_manager
call :google_cleanup
call :say Done.
if exist "%RUNOUT%" del /q "%RUNOUT%"
pause
exit /b 0

:dirty
call :say Dirty flash: your data is kept, rebooting now.
call :run fastboot reboot
call :boot_help
echo.
if "%ROOT%"=="ksu" call :ksu_manager
call :google_cleanup
if "%ROOT%"=="remove" (
    echo Root was removed, so the optional root cache clean-up is skipped.
    goto :done
)
echo Optional, needs root and USB debugging: clear the cached carrier settings, the package
echo cache, the Settings search index and the system sounds index, so changed carrier configs,
echo apps, settings and ringtones are picked up (one extra reboot).
choice /c YN /m "Do this once the phone has booted"
if errorlevel 2 goto :done
call :wait_android
REM Sounds set to None (ringtone/notification/alarm = null): a phone that booted once without the sound files
REM keeps them empty. MediaProvider sets the stock default only while the *_set flag is missing and it indexes
REM the file for the first time (internal.db is rebuilt below). None can also be the user's choice, so ask.
REM settings runs as the shell user: under su it fails silently.
set "TONES=%LOGDIR%\empty_tones.tmp"
adb shell "for k in ringtone notification_sound alarm_alert; do case $(settings get system $k) in ''|null) echo $k;; esac; done" > "%TONES%" 2>nul
for %%A in ("%TONES%") do if %%~zA equ 0 goto :tones_done
echo These sounds are set to None: 
type "%TONES%"
choice /c YN /m "Set them back to the stock default tone (N keeps None)"
if errorlevel 2 goto :tones_done
adb shell "for k in ringtone notification_sound alarm_alert; do case $(settings get system $k) in ''|null) settings delete system ${k}_set;; esac; done"
:tones_done
if exist "%TONES%" del /q "%TONES%"
adb shell "su -c 'am force-stop com.android.settings.intelligence; am force-stop com.google.android.providers.media.module; rm -f /data/user/0/com.google.android.providers.media.module/databases/internal.db*; rm -f /data/user_de/0/com.android.phone/files/carrierconfig-*.xml; rm -rf /data/system/package_cache/*; cd /data/data/com.android.settings.intelligence && rm -f databases/search_index.db* shared_prefs/indexing_manager.xml shared_prefs/full_indexed_pkgs.xml'"
if errorlevel 1 (
    echo Root command failed - grant adb shell root access in your root manager and run it again:
    echo adb shell "su -c 'am force-stop com.android.settings.intelligence; am force-stop com.google.android.providers.media.module; rm -f /data/user/0/com.google.android.providers.media.module/databases/internal.db*; rm -f /data/user_de/0/com.android.phone/files/carrierconfig-*.xml; rm -rf /data/system/package_cache/*; cd /data/data/com.android.settings.intelligence && rm -f databases/search_index.db* shared_prefs/indexing_manager.xml shared_prefs/full_indexed_pkgs.xml'"
    pause
    exit /b 1
)
adb reboot
echo Caches cleared, phone is rebooting.

:done
call :say Done.
if exist "%RUNOUT%" del /q "%RUNOUT%"
pause
exit /b 0

:failed
echo.
call :say ERROR: flashing stopped because of the error above. Do NOT reboot the phone yet, send the log file first.
goto :fail_collect

:abort
call :say Nothing was flashed.

:fail_collect
echo Collecting phone info for the developer...
call :collect_fastboot
call :pack
pause
exit /b 1

REM ---------------------------------------------------------------- collect logs (menu option 3)

:collect
call :say Selected: collect logs
echo.
echo Connect the phone with USB. Any of these works:
echo   - fastboot or FastbootD mode. If the phone keeps restarting, hold Volume Down + Power
echo     until the fastboot screen opens. This gives partition and slot info only.
echo   - Android booted with USB debugging on. Gives full logs.
echo   - a recovery with adb, such as TWRP. Gives the kernel log of the last failed boot.
echo Looking for the phone for up to 2 minutes, close this window to cancel...
adb start-server >nul 2>&1
set /a WAITN=0
:collect_wait
set /a WAITN+=1
if !WAITN! gtr 40 goto :collect_nodevice
call :detect
if not defined DEVMODE (
    timeout /t 3 /nobreak >nul
    goto :collect_wait
)
if "!DEVMODE!"=="unauthorized" (
    echo Unlock the phone and allow USB debugging on the prompt...
    timeout /t 3 /nobreak >nul
    goto :collect_wait
)
call :say Phone found, mode: !DEVMODE!
if "!DEVMODE!"=="fastboot" (
    call :collect_fastboot
    goto :collect_done
)
if "!DEVMODE!"=="device" (
    call :collect_android
    goto :collect_done
)
if "!DEVMODE!"=="recovery" (
    call :collect_recovery
    goto :collect_done
)
call :say The phone is in adb mode "!DEVMODE!", logs can't be read in this mode. Reboot it to fastboot and try again.
goto :collect_done

:collect_nodevice
call :say No phone found. Check the USB cable and drivers: "fastboot devices" or "adb devices" must list it.
:collect_done
call :pack
pause
exit /b 0

:detect
REM DEVMODE = fastboot, or the adb state (device, recovery, unauthorized, sideload, ...), or empty.
REM Uses the "devices" commands only: fastboot getvar would wait forever without a phone.
set DEVMODE=
for /f "tokens=1" %%d in ('fastboot devices 2^>nul') do set DEVMODE=fastboot
if defined DEVMODE exit /b 0
for /f "skip=1 tokens=2" %%s in ('adb devices 2^>nul') do if not defined DEVMODE set "DEVMODE=%%s"
exit /b 0

:collect_fastboot
call :detect
if not "!DEVMODE!"=="fastboot" (
    call :say No phone in fastboot mode, fastboot info skipped.
    exit /b 0
)
set "CAPF=fastboot_getvar_all.txt"
call :cap fastboot getvar all
exit /b 0

:collect_android
echo Reading logs from Android...
set "CAPF=getprop.txt"
call :cap adb shell getprop
set "CAPF=logcat_all.txt"
call :cap adb logcat -d -b all
set "CAPF=logcat_previous_boot.txt"
call :cap adb logcat -d -L
set "CAPF=dmesg.txt"
call :cap adb shell dmesg
echo If your root manager asks whether to allow Shell, allow it.
call :runq adb shell "su -c id"
findstr /c:"uid=0" "%RUNOUT%" >nul && (
    set "CAPF=dmesg_root.txt"
    call :cap adb shell "su -c dmesg"
    set "CAPF=pstore_console.txt"
    call :cap adb shell "su -c 'cat /sys/fs/pstore/console-ramoops*'"
    set "CAPF=tombstones.txt"
    call :cap adb shell "su -c 'for f in /data/tombstones/tombstone_[0-9][0-9]; do echo ==== $f; cat $f; done'"
    set "CAPF=anr.txt"
    call :cap adb shell "su -c 'for f in /data/anr/*; do echo ==== $f; cat $f; done'"
    set "CAPF=dropbox_list.txt"
    call :cap adb shell "su -c 'ls -l /data/system/dropbox'"
)
choice /c YN /m "Also make a full bug report (2-5 minutes, 10-30 MB more)"
if errorlevel 2 exit /b 0
>>"%LOG%" echo ^>^> adb bugreport
adb bugreport "%LOGDIR%\bugreport.zip"
exit /b 0

:collect_recovery
echo Reading logs from recovery...
set "CAPF=pstore_console.txt"
call :cap adb shell "cat /sys/fs/pstore/console-ramoops*"
set "CAPF=pstore_pmsg.bin"
call :cap adb exec-out "cat /sys/fs/pstore/pmsg-ramoops-0"
set "CAPF=recovery_dmesg.txt"
call :cap adb shell dmesg
set "CAPF=recovery_log.txt"
call :cap adb shell "cat /tmp/recovery.log"
set "CAPF=recovery_getprop.txt"
call :cap adb shell getprop
exit /b 0

REM ---------------------------------------------------------------- subroutines

:pimg
REM PIMG = the image file for logical partition %1 (my_product_lite.img for my_product with Minimal Google).
set "PIMG=%~1.img"
if "%~1"=="my_product" if "%GAPPS%"=="minimal" set "PIMG=my_product_lite.img"
exit /b 0

:google_cleanup
REM Minimal Google, after boot: the image leaves out the Google apps, but an app that Play Store updated
REM keeps its update in /data as a normal app on a dirty flash, and ARCore is in my_stock. Uninstall
REM those for user 0 (no root needed). Packages that are not on the phone are skipped.
if not "%GAPPS%"=="minimal" exit /b 0
if not exist "google_minimal_packages.txt" exit /b 0
echo.
echo Minimal Google clean-up, needs USB debugging: removes Google apps that stay behind after
echo the flash - on a dirty flash, apps updated from Play Store keep their update as a normal
echo app - and ARCore. The list is google_minimal_packages.txt in this folder.
echo If the data was wiped, finish the phone setup and turn on USB debugging first.
choice /c YN /m "Do this once the phone has booted"
if errorlevel 2 (
    echo Skipped. Uninstall leftover Google apps on the phone yourself if you see any.
    exit /b 0
)
call :wait_android
set /a GRM=0
for /f "usebackq tokens=1" %%k in ("google_minimal_packages.txt") do (
    call :runq adb shell pm path %%k
    findstr /c:"package:" "%RUNOUT%" >nul && (
        call :runq adb shell pm uninstall --user 0 %%k
        findstr /c:"Success" "%RUNOUT%" >nul && (
            call :say Removed %%k
            set /a GRM+=1
        ) || call :say Could not remove %%k
    )
)
call :say Minimal Google clean-up: !GRM! apps removed.
exit /b 0

:wait_fastboot
REM Waits up to 2 minutes until "fastboot devices" lists the phone (fastboot getvar would hang without one).
set /a WFN=0
:wait_fastboot_loop
call :detect
if "!DEVMODE!"=="fastboot" exit /b 0
set /a WFN+=1
if !WFN! gtr 40 exit /b 1
timeout /t 3 /nobreak >nul
goto :wait_fastboot_loop

:wait_fastbootd
REM Waits up to 2 minutes until the phone answers in userspace fastboot (FastbootD).
set /a WDN=0
:wait_fastbootd_loop
call :detect
if "!DEVMODE!"=="fastboot" (
    call :runq fastboot getvar is-userspace
    findstr /c:"is-userspace: yes" "%RUNOUT%" >nul && exit /b 0
)
set /a WDN+=1
if !WDN! gtr 40 exit /b 1
timeout /t 3 /nobreak >nul
goto :wait_fastbootd_loop

:say
REM Print a line and add it to the log.
echo(%*
>>"%LOG%" echo(%*
exit /b 0

:run
REM Run a command, show its output and add the command and its output to the log. Keeps the exit code.
REM The output appears when the command has finished.
>>"%LOG%" echo(^>^> %*
%* > "%RUNOUT%" 2>&1
set RC=!errorlevel!
type "%RUNOUT%"
type "%RUNOUT%" >> "%LOG%"
>>"%LOG%" echo(   [exit code !RC!]
exit /b %RC%

:runq
REM Like :run, but the output only goes to the log.
>>"%LOG%" echo(^>^> %*
%* > "%RUNOUT%" 2>&1
set RC=!errorlevel!
type "%RUNOUT%" >> "%LOG%"
>>"%LOG%" echo(   [exit code !RC!]
exit /b %RC%

:cap
REM Like :runq, but the output goes to its own file CAPF in the log folder.
>>"%LOG%" echo(^>^> %* ^> !CAPF!
%* > "%LOGDIR%\!CAPF!" 2>&1
>>"%LOG%" echo(   [exit code !errorlevel!]
exit /b 0

:log_header
>>"%LOG%" echo Nord 6 ColorOS 17 port flasher log - %DATE% %TIME%
>>"%LOG%" echo Folder: %HERE%
>>"%LOG%" ver
>>"%LOG%" echo Images in this folder:
>>"%LOG%" dir /-c *.img 2>&1
call :runq where fastboot adb
call :runq fastboot --version
exit /b 0

:pack
REM Zip the log folder and show it in Explorer.
if exist "%RUNOUT%" del /q "%RUNOUT%"
set "ZIP=logs\nord6_logs_%TS%.zip"
powershell -NoProfile -Command "Compress-Archive -Path '%LOGDIR%\*' -DestinationPath '%ZIP%' -Force" >nul 2>&1
echo.
if exist "%ZIP%" (
    echo Logs saved. Send this file to the developer:
    echo   !HERE!!ZIP!
    start "" explorer /select,"!HERE!!ZIP!"
) else (
    echo Logs saved. Zip this folder and send it to the developer:
    echo   !HERE!!LOGDIR!
)
exit /b 0

:boot_help
echo.
echo The first boot can take a few minutes. If it has not finished booting after 10 minutes
echo (it keeps restarting or stays on the logo), hold Volume Down + Power until the fastboot
echo screen opens, run flash_all.bat again and choose 3 to collect logs for the developer.
echo This flash was logged to !HERE!!LOG!
exit /b 0

:ksu_prepare
REM Download the latest KernelSU Next and patch init_boot.img on this PC (no phone needed),
REM the same way "ksud boot-patch" does. The result is flashed in step 1.
if exist "init_boot_ksu.img" del /f /q "init_boot_ksu.img"
echo Downloading KernelSU Next, please wait...
call :run powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%ksu_root.ps1" -Action download || (
    call :say ERROR: could not download KernelSU Next.
    exit /b 1
)
echo Patching init_boot.img, please wait...
call :run powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%ksu_root.ps1" -Action patch || (
    call :say ERROR: patching init_boot failed.
    exit /b 1
)
set KSU_IMG=init_boot_ksu.img
echo.
exit /b 0

:ksu_manager
echo.
echo Root is in place. KernelSU Next needs its manager app to grant root to apps.
echo The app is ksu\KernelSU_Next.apk in this folder: copy it to the phone and install it,
echo or let this script install it over USB debugging once the phone has booted.
choice /c YN /m "Install the manager over adb now"
if errorlevel 2 (
    echo Install ksu\KernelSU_Next.apk on the phone yourself later.
    exit /b 0
)
echo If the data was wiped, finish the setup and turn on USB debugging again.
call :wait_android
call :run powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%ksu_root.ps1" -Action install || (
    echo Install failed - install ksu\KernelSU_Next.apk on the phone yourself.
)
exit /b 0

:wait_android
echo Waiting for the phone (unlock it and allow USB debugging if asked; close this window to cancel)...
adb wait-for-device
:wait_boot
adb shell getprop sys.boot_completed 2>nul | findstr "1" >nul || (timeout /t 5 /nobreak >nul & goto :wait_boot)
exit /b 0
