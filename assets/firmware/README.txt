Nord 6 ColorOS 17 port - firmware fix (Android Auto / "Hey Google")

PROBLEM
  Wired Android Auto keeps disconnecting/reconnecting and charging flaps. The port's "Hey Google"
  voice model (base ColorOS 17.0.0.100) crashes the audio DSP when the phone still has OxygenOS 16
  firmware. Every DSP crash drops charging and USB.

FIX
  Flash the base build's firmware. The DSP code is in modem.img; the other images keep the firmware
  one matched set, as an official update does. Port images (system, my_product, ...) are not touched.

HOW
  1. Phone booted in Android with USB debugging on (or already in the bootloader).
     adb.exe and fastboot.exe in this folder or on PATH.
  2. Run flash_firmware.bat. It does everything by itself:
       bootloader -> modem        (fastbootd can't open modem)
       fastbootd  -> the rest     (the bootloader refuses these without a wipe)
       reboot
  3. After boot: Google app > Settings > Google Assistant > Hey Google & Voice Match >
     Voice model > Retrain voice model.

SAFE
  No data wipe (no -w, erase, format or unlock_critical). boot / init_boot / vendor_boot are never
  written, so root stays. Only the current slot is written. Anti-rollback is 0 on OxygenOS 16 and
  ColorOS 17 firmware, so going back is possible.

WINDOWS DRIVER
  The Nord 6 bootloader and fastbootd both show up as USB 18D1:D00D, which Google's USB driver
  doesn't list (Device Manager shows "CPH2793" with an error after every mode switch).
  One-time fix: Administrator PowerShell in fastboot_driver\, then
    powershell -ExecutionPolicy Bypass -File install_driver.ps1
  It installs a WinUSB driver for 18D1:D00D with a self-signed certificate (added to the PC's
  trusted stores). After that both modes bind automatically.

FILES
  images\           firmware images (md5 in md5.txt)
  flash_firmware.bat
  fastboot_driver\  nord6_fastboot.inf + install_driver.ps1
