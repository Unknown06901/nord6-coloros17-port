# Decisions and dead ends (verified on the device)

Part of the agent instructions for this kit: read `AGENTS.md` first, then this file before changing any build step,
patch or test. Don't redo a dead end listed here without new evidence. It is a separate file so that `AGENTS.md`
stays under Google Antigravity's 24,000-byte limit per rule file (longer files are cut off). Add new verified
decisions here; if this file nears 24 KB, split it by topic and list the new files in `AGENTS.md`.


- **Donor C.80 (17.0.1.201, 2026-11-11 audit):** every code patch still finds its target (the donor code is
  unchanged at those sites), subsys_radio went V1 -> V2 and is still remapped to base V9 automatically. Already
  gone in C.80, so those steps are no-ops: the game HDR page (`sys_gamespace_gamesettings.xml` is empty) and
  the peak-brightness / sell-mode nit / renderengine maxLuminance props. New in C.80 and removed for base parity:
  `ro.oplus.radio.global_regionlock.dynamic` (my_stock) and `persist.sys.bt.leacoexist` (my_product). New and
  kept: phoenixd + oplus_kmsg_wb_helper (the base kernel has Phoenix 2.0), gpp client libs (base vendor has the
  hexlp HAL), subsys-imsvoip-plugin (software only, no HAL calls).
- **Upstream to the ColorOS 17 base (17.0.0.100, 2026-11-18).** From version 17 OPPO, OnePlus and realme all ship ColorOS (no OxygenOS 17); call the base ColorOS 17 in docs and posts. The official Android 17 base made four steps
  obsolete, and they were removed: the `lseek` seccomp additions (the base policies have it), the donor
  `libradioapis.so` in odm (base odm is ColorOS 17 telephony now), the oplus-services engineer `checkService`
  patch (the base vendor declares `IEngineer/default` in `vendor.oplus.hardware.engineer.aidl.apex`, and stock
  ColorOS 17 uses the same `waitForService`), `port_product_overlay.rc` (the base fstab mounts my_* at
  `/my_*`, as the donor's libfs_mgr expects), and two steps that had nothing left to do: the vendor_property_contexts
  duplicate drop (0 duplicates) and the base ringtones copy (ColorOS 17 my_stock has the same sounds as the donor). Still needed on 17.0.0.100: fstab avb strip, perf [13,32]
  (still `Supported="no"` for tuna), Widevine prov40 off (base still `true`), dtbo AOD config (base panel nodes
  still lack it), subsys_radio renumbering (interface hashes still differ), all my_product/my_stock parity
  steps and every donor-side app patch. Sounds moved in ColorOS 17: ringtones/notifications are in
  `my_product/res/audio` (not my_stock), and the donor has only per-motor `haptic_ringtone/output<F>HZ` sets, so
  `sound_parity` takes the base folders (missing tones after the first 17.0.0.100 flash). 17.0.0.100 has the same GKI kernel build as 16.0.5.1300, an Android 15 vendor at the same patch level
  (2026-10-01) and KeyMint v3, so a dirty flash from the 16.0.5.1300-based port keeps data (no patch-level rollback).
  **But the phone needs the 17.0.0.100 firmware** (see Hotword): 26 of 29 firmware images differ (dsp, spuservice,
  oplus_sec are equal), and the OxygenOS 16 ADSP crashes on the 17 voice model. All firmware is ARB 0 on both.
  Old-base history follows.
- **C.80 first flash bootlooped (2026-11-11), fixed by `port_product_overlay.rc` (removed with the ColorOS 17 base):** zygote aborted forking
  system_server with `Not allowlisted (70): /my_product/cust/IN/overlay/...apk`, and once past that the punch
  hole sat on the left. Cause (from the saved boot logs in `/mnt/vendor/oplusreserve/media/log/boot_log/`,
  `kernel_boot.log`, grep `libfs_mgr`): C.80 libfs_mgr mounts `/product/overlay` with lowerdirs `/my_product/overlay`
  etc., which don't exist yet on the Nord 6 (base fstab mounts my_* at `/mnt/vendor/my_*`), so the mount fails.
  C.75 used `/mnt/vendor/...` and worked. Check that kernel log line on every new donor.
- **oplus-services.jar:** builds before C.80 shipped a system.img with an older auto-port jar; from C.80 on the
  port uses the kit's own donor jar + patches. Device check of that jar is pending (first C.80 flash).
- **Hotword / Android Auto (2026-11-20, tested on device):** the "Hey Google" enrollment apks come from base.
  17.0.0.100 base ships v36 apks (53140 B DSP model, version 868740715; byte-identical to the donor's). That model
  crashes the **OxygenOS 16 ADSP firmware** (`err_qdi.c:1215:EX:audio_process` every 2-5 s once Hey Google is armed;
  each ADSP restart drops charging and USB, so wired Android Auto keeps reconnecting). With the stock 17.0.0.100
  firmware on the phone the same model runs clean (desk test + Desktop Head Unit session with Hey Google and AA
  audio concurrent: 0 crashes). So: stock 17 firmware + base apks. The OxygenOS 16 v35 apks (53092 B, version
  642444186) also work, but only matter on OxygenOS 16 firmware. Flashing the firmware without a wipe: the bootloader
  refuses critical partitions (xbl, abl, tz...) unless `flashing unlock_critical` (wipes), so flash those 25 from
  fastbootd; fastbootd can't open `modem` (recovery has it mounted), so flash `modem` from the bootloader. Verify by
  reading the partitions back; `splash` always differs in its first 5 bytes (the phone stamps a `DDPH` header).
  `make_firmware_fix.py` builds that package from the base images (25 images by default: dsp, spuservice,
  oplus_sec and splash are the same as OxygenOS 16.0.5.1300; `--skip-same-as DIR` drops more). The images are
  never committed (modem.img is 199 MB, over GitHub's 100 MB limit; base inputs stay out of git anyway).
  `flash_firmware.bat` was written from the steps run by hand on 2026-11-20; the script itself has not yet run
  end to end on a phone.
  Since 2026-11-22 the port build also writes `firmware/` (same 25 images, `build_port.add_firmware`) and
  `flash_all.bat` flashes it in both modes: `modem` from the bootloader right after TWRP, the other 24 from TWRP
  FastbootD after the boot images. Not yet run end to end on a phone either.
- **Windows fastboot driver:** the Nord 6 bootloader (REV_0100) and fastbootd (REV_0606) both enumerate as USB
  `18D1:D00D`, which Google's `android_winusb.inf` doesn't list, so Device Manager shows "CPH2793" with an error
  and a manually picked driver is lost on every mode switch. `assets/fastboot_driver` adds a WinUSB inf with the
  Android interface GUID `{F72FE0D4-CBCB-407d-8814-9ED673D0DD6B}` and a self-signed catalog; installed on the
  user's PC on 2026-11-20 (published as `oem48.inf`). An agent may be blocked from running the elevated install
  (it adds a certificate to the trusted root store); the user runs it.
  Check on the phone: `dumpsys soundtrigger_middleware` (model ACTIVE + dataSize) and `/dev/kmsg` for
  `remoteproc-adsp: fatal`. Note: `dmesg` as root is killed by seccomp on this ROM (SIGSYS tombstones); read
  `/dev/kmsg` or `/sys/fs/pstore/console-ramoops-0` (previous boot) instead.
- **Radio:** the donor uses subsys_radio HAL V1 numbering and the Nord 6 HAL is V9. `lib/subsysradio.py`
  renumbers the calls; never drop that step. Radio/RF features, SAR and carrier configs all come from base.
- **Traceur and CrossDeviceServiceBroker are removed.** ColorOS kept a perfetto "health" trace running all
  the time through Traceur (heat and idle drain). `midasd`, `ostatsd` and `ostats_pullerd` are disabled
  through build.prop.
- **UniRender is off** (it caused banded screenshots). **WCG 2.0 is off.** The display configs come from base,
  plus the 165 Hz option.
- **AOD:**
  - **Full-screen AOD comes from the panel device tree (2026-11-17, tested on device).** The Nord 6 display
    driver (`msm_drm.ko`, OFP code = `oplus_onscreenfingerprint.c` in OnePlusOSS
    `android_kernel_modules_and_devicetree_oneplus_sm8735`, branch `oneplus/sm8735_b_16.0.0_nord_6`) has a
    full-screen AOD mode: no `lp1-command`, and the "aod layer exist, filter backlight" rule is skipped, so the
    doze brightness reaches the panel. It needs panel DT property `oplus,ofp-longrui-aod-config` (bit 0x4 full
    screen, 0x8 full screen all day). Base leaves it out (reads 0x0). `build_port.patch_dtbo` adds `<0xC>` to the
    AA610 A0034 panel nodes in every dtbo overlay (`lib/dtbo.py`, pure-Python FDT editor). Other panels in the same
    dtbo (e.g. AC274 A0026) are left alone. vbmeta flags 3 means the stale dtbo AVB hash doesn't matter.
  - SystemUI reads the same value as panel feature 217 (0x2 seamless, 0x4 panoramic, 0x8 all day, 0x1 inverse of
    gotoDozeWithOff) and sends the mode back itself (`setDisplayStateByCurrentAodStyleType`: 4 = panoramic, via the
    displaypanelfeature HAL -> `PANEL_IOCTL_SET_LONGRUI_AOD`). So panoramic and all-day need no SystemUI flag patch.
  - Seamless (bit 0x2, kernel "a mirror to the end") is not claimed in DT: the kernel would then run its own
    AOD-off handling, which this panel may not support. `systemui_seamless_aod` forces the SystemUI flag in both
    paths of `initSmoothTransitionState` instead. It has to cover the normal path because 217 is no longer 0.
  - Display modes: the AOD app hides its energy saving / scheduled / always-on picker on video-mode panels
    (`aod_show_display_mode`, one static flag = `disable_aod_all_day_mode || video_mode_aod_support`).
    `systemui_videomode_aod_hide` drops the video-mode clause from both `onEnergySavingNotifyHide` methods, so
    "always on" and scheduled can stay on. Energy saving still hides about 5 s after the last lift/notification
    and comes back on lift (tilt/pick-up sensor, shaking does nothing).
  - The old symptoms were all the backlight filter: without full-screen mode the panel kept only the brightness
    it had while on (so the first AOD after locking was visible), went black about 5 s in, and a re-show after
    the panel had been off started at backlight 0 (black on lift). Don't go back to forcing panel bits in
    SystemUI or clearing SurfaceFlinger's panoramic flag (`service call SurfaceFlinger 23332`): neither changes the
    kernel path.
  - The app feature `com.oplus.systemui.panoramic_aod_all_day.enable` is not needed (base doesn't have it, all-day
    works without it).
- **Earbuds (Melody, `com.oplus.melody`):**
  - Melody's built-in model whitelist (`res/raw/melody_app_whitelist.json`, AES-GCM, key = SHA-256 of the
    signing certificate) has OPPO, OnePlus and realme models. While loading, it drops realme models unless
    `Build.BRAND` is realme. `melody_realme_whitelist` removes that check. Class names are obfuscated
    differently in every Melody build, so the patch finds its site by instruction shape across all dex files.
  - Result, verified with realme Buds Air6 Pro: the earbuds are recognised and get their Melody page.
    The product images, EQ layout and popup images come from Melody's server, which returns 404 for realme
    models (`control_<pid>_<color>`, `fetch14_...`). So the images stay generic, there's no EQ and no
    case-open popup. realme's own app (realme Link) still handles EQ.
  - Patching the apk in place keeps the signing block, so the whitelist key still matches. Re-signing the
    apk would break decryption.
  - The Play Store updates Melody into `/data/app`, which would hide the patched system copy, so the build
    raises its versionCode.
- **Google Fast Pair battery card popping up every ~10 s:** this is Play Services, not the port. Some
  earbuds (realme Buds Air6 Pro) keep alternating their Fast Pair advertisement while the case is open, and
  Play Services dismisses and re-posts the card each time. It can't be fixed in the ROM. The user-side fix is
  to turn off Banner for Google Play services > "Devices with your account".
- **UNKNWN AddOns was built and then removed on 2026-11-09 at the user's request** (a Settings > UNKNWN AddOns page
  for CPU/GPU profiles, Overkill thermal table, forced refresh rate, big cores, animation speed, custom font and
  secure screenshots, plus a root backend). Its backup zip was deleted on 2026-11-22; it is gone.
  Don't add it back unless the user asks. What it taught, still true for this ROM:
  - `settings` (`cmd`) hands its stdin/stdout/stderr to system_server; pointed at a root-owned file the call fails
    silently ("Failed transaction"). Pipe it in background scripts.
  - The SM8735 prime core's 3.2 GHz step is only in `scaling_boost_frequencies`. ColorOS writes the little
    cluster's `scaling_max_freq` itself. The per-core `cpu-*` sensors pass 100 °C within seconds of full load
    (normal); `cpuss-*` are the steadier cluster sensors.
  - toybox `chcon` has no `--reference`; use `chcon $(stat -c %C <file>)`.
  - `OplusSubSettings`/`SubSettings` accept any fragment, so a new Settings page needs no manifest change; a new
    dex can be appended to Settings.apk ahead of its signing block.
- **Animation-scale box (2026-11-17):** 0x ("Animation off") hangs SystemUI on this port, so the Developer options
  lists drop every entry below 0.5 and gain "Custom…" (value `custom`) with a 0.5–10 number box. `AnimScale` lives in
  the Miscellaneous dex, so `patch_anim_scale` must run after `misc.patch_settings`; it rewrites only the bodies of
  `updateState` and `onPreferenceChange` in the three `development/*ScalePreferenceController` classes (classes.dex,
  baksmali 2.5.2 is fine there). `onChange` always returns false and `refresh` sets the shown value. Only the
  Settings UI is gated: accessibility "Remove animations" and `settings put global` can still write 0.
  Verified on the phone: 1.5x applied to all three Global keys (a higher scale is slower, as on any Android).
- **Miscellaneous page (2026-11-15, Lunaris AOSP as reference):** each switch was checked on the phone with a test
  module (secure-app screenshot in PhonePe, recording kept through lock, SearchSelector 7955 -> 7171 downgrade,
  Photos "This CPH2793 can back up unlimited photos and videos at no charge").
  - Netflix 15001 (-93) is Widevine Provisioning 4.0 failing in the TEE (`GetProvisioning40RequestInternal status
    323`), not device certification. `enable_prov40=false` in odm fixes it, with or without TrickyStore. No spoof.
  - Granting the recorder the `PROJECT_MEDIA` app-op does not keep a recording alive on lock; the recorder stops
    itself on SCREEN_OFF unless its own setting is 1.
  - Photos needs only the sysconfig features; a Pixel Build spoof (Lunaris PixelPropsUtils) isn't needed for it.
  - baksmali 2.5.2 cannot disassemble framework.jar (AIOOBE in HiddenApiRestriction on the newer hidden-API flags).
    `misc.patch_framework` uses smali 3.0.10 with `-a 29`: dex 039 with all hidden-API flags kept (`-a 28` drops
    them, `-a 35` writes a dex 041 container).
  - Android 17 ART refuses `Field.set` on static final fields (Build.MODEL etc.), even after setAccessible or clearing
    `Field.accessFlags`. PortSpoof writes with `Unsafe.putObject(Build.class, Field.offset, value)` (verified).
  - Hide developer options (SettingsProvider, system_server): every settings read reply goes through
    `packageValueForCallResult`, so that's the single hook. `getGlobalSetting` enforces read access with the caller's
    uid, so the injected code clears the calling identity before reading `port_hide_dev*`. ColorOS's own
    `oplus.SettingsFilter.valueFilter` already answers 0 to some apps (Airtel, Xstream) with the switch off; that
    isn't this patch. To test as an app uid without the app, take the provider binder as root
    (`getContentProviderExternal`), then `Os.setuid(uid)` and call `GET_global` (`su <uid> content call` is denied).
  - Choose apps page (2026-11-22): Back must go through `OnBackPressedDispatcher` (an `OnBackPressedCallback`);
    `OplusSubSettings.setSubSettingsCallback` / `Activity.onBackPressed` overrides are not called on Android 17.
    `COUISearchBar.setOnClickListener` attaches to its inner background view, a `COUISearchBar` created in code needs
    an explicit height (52dp, as on Settings home) or it measures 0, and menus inflated with the fragment's
    `MenuInflater` skip `app:actionViewClass`. `Preference.setIcon` inside `onBindViewHolder` throws (RecyclerView
    rebind during layout), so lazy icons go straight into the row's `android:id/icon` ImageView. Settings' own logs
    hit ColorOS's per-process log quota (`LOG_FLOWCTRL ... DROPPED`); use `dumpsys activity top` for view trees.
  - The Photos features are a switch because the app-side `ApplicationPackageManager.hasSystemFeature` filters them;
    the sysconfig itself is fixed at boot.
  - Testing on the phone: KernelSU Next 3.x mounts a module's `system/` only with a metamodule (none installed), so
    test modules bind-mount from `post-fs-data.sh`. The user's Meow Zygisk (ReZygisk, manages `kernel_umount`)
    unmounts /data-sourced mounts in every app process but keeps tmpfs ones, so copy test files to /dev first. A
    /data-sourced framework.jar mount crash-looped apps (zygote had the patched jar, apps saw stock: zip EOF).
- **Launcher:** the old dock bar / liquid glass patch is retired; the Zuyqa launcher in `assets/launcher`
  replaces OplusLauncher.
- **Things that are user settings, not build steps:** Private DNS mode, per-app battery restrictions,
  screen timeout.

