# Nord 6 ColorOS 17 port builder

AI agents (Gemini CLI, Antigravity, Claude Code, Codex, ...): read [AGENTS.md](AGENTS.md) first.

`build_port.py` rebuilds the flashable port from scratch:

- **Base**: stock Nord 6 ColorOS 17 images in `../base/images` (currently 17.0.0.100). From version 17 OPPO, OnePlus and realme all ship ColorOS; there is no OxygenOS 17.
- **Donor**: a ColorOS 17 build. It can be an images folder, a `payload.bin`, or a full OTA `.zip`.

The script applies every fix that was made and tested on the device. Each code patch finds
its target by class, method and instruction pattern, not by a fixed file offset, so it also
works on a newer donor build of the same code. If a pattern isn't found exactly once, the
build stops and doesn't write a broken file.

## Usage

The kit is self-contained: unzip it anywhere on Linux/WSL. It needs `python3` (standard
library only) and `java` (`sudo apt install openjdk-21-jre-headless`). The erofs tools,
payload-dumper-go, smali/baksmali 2.5.2 and smali 3.0.10 (`tools/smali3`, framework.jar only) are in `tools/`.

```bash
python3 build_port.py --check --base Nord6_Base.zip --donor ColorOS17_OTA.zip --out out_port   # preflight only
python3 build_port.py --base Nord6_Base.zip --donor ColorOS17_OTA.zip --out out_port
```

`--base` and `--donor` each accept:
- an images folder (`*.img`)
- a `payload.bin`
- a full OTA zip (with `payload.bin` inside)
- a fastboot zip (with `*.img` inside)

Other options:
- `--work DIR`: scratch space, default `./_work`. With two OTA zips it needs about 60–80 GB free. It is deleted afterwards unless you pass `--keep-work`.
- `--banner-text "..."`: text on the About-device pill. Pass `""` to keep the stock text.
- `--level N`: lz4hc level, default 12.
- `--keep-going`: report a failing patch instead of stopping the build.
- `--check`: only check Python, Java, the bundled tools, the inputs and free space, then exit (0 = ready).

The output is all images, `flash_all.bat`, `ksu_root.ps1` and `BUILD_REPORT.txt`. The report lists every step,
the donor fingerprint and the total size of the logical partitions. Flash from Windows with
`flash_all.bat`, which asks for the mode first:

- Clean flash: for a first install (from stock OxygenOS 16 / ColorOS 17 or any other ROM). Needs the full image set, flashes
  everything and wipes data at the end. It asks Root with KernelSU Next or No root.
- Dirty flash: for updating a phone that already runs this port. Flashes only the `.img` files in the
  folder and keeps data, so a fix package can contain just the changed images (for example only
  `system_ext.img` and `my_product.img`); boot images and FastbootD are skipped when absent. It then asks
  Keep root (init_boot is not flashed, so a Magisk/KernelSU patched init_boot stays), Root with KernelSU
  Next (also updates an older KernelSU Next) or No root (flashes the port's stock `init_boot.img`). Root that lives in `boot.img` (KernelSU GKI mode) is replaced whenever
  the folder has `boot.img`. Afterwards, if root was kept, it
  can clear the cached carrier config and package cache over adb (needs root and USB debugging), then
  reboot once more. CarrierConfig is always versionCode 1, so the phone never drops its carrier cache by
  itself. It also resets the Settings search index: SettingsIntelligence re-indexes an app only when the
  app's version changes, so after a fix that hides a setting (for example reverse wireless charging or eSIM)
  the old search result would otherwise stay forever. It also drops MediaProvider's system sounds index
  (`internal.db`; the photo/music index is separate) and, for a ringtone, notification or alarm sound that is
  empty, its `*_set` flag: MediaProvider picks the stock default (`ro.config.*`) only when it first indexes that
  file, so a phone that booted once without the sound files kept an empty tone. Because None can be a deliberate
  choice, the script lists the sounds set to None and asks before resetting them (N keeps None). `settings` runs as the adb shell user there (under `su` it fails silently), and Android
  17 refuses media URIs written with `settings put`, which is why the flag is reset instead. Images are stamped with the build time (`mkfs.erofs -T`), so PackageManager re-parses
  changed apks even without that step: the port's fingerprints never change between builds.
- Collect logs: for a phone that does not boot or misbehaves after flashing. It waits up to 2 minutes for
  the phone and saves what the current mode allows: fastboot/FastbootD gives `fastboot getvar all` (slot,
  partition sizes, retry/unbootable flags); booted Android with USB debugging gives getprop, logcat (also the
  previous boot's via `logcat -L`) and dmesg, and with root also pstore, tombstones, ANRs and the dropbox
  list, plus an optional `adb bugreport`; a recovery with adb (TWRP) gives the pstore kernel log of the last
  failed boot and the recovery log.

Every run logs each fastboot/adb command with its output and exit code to `logs\<date_time>\flash_log.txt`
(also the Windows version, fastboot path/version and the image list). When a step fails the script stops,
adds `fastboot getvar all`, zips the folder to `logs\nord6_logs_<date_time>.zip` and opens it in Explorer
so the user can send it. Logical partitions go to the phone's current slot (read in FastbootD; phones are
often on slot b after an OTA), and the script refuses to touch super if the phone is not in FastbootD.

Root with KernelSU Next happens on the PC before anything is flashed, so the phone never has to boot first.
`ksu_root.ps1` (PowerShell 5.1, no extra tools) downloads the latest GitHub release into `ksu\`: the
`aarch64_<KMI>_kernelsu.ko` for the kernel in `boot.img` (android15-6.6), the manager apk and `ksud`, from which
it takes `ksuinit` (the official release ships it only inside ksud, as a raw deflate stream). It then patches
`init_boot.img` into `init_boot_ksu.img` exactly like `ksud boot-patch` (init -> init.real, ksuinit as
/init, kernelsu.ko, `ksu_config` = `bundled=1`; magiskboot cpio layout, lz4 legacy, AVB footer kept;
verified: the ramdisk cpio is byte-identical to the one ksud produces), and step 1 flashes that. Without
internet it reuses an earlier download. After boot it offers to install the manager over adb; otherwise
install `ksu\KernelSU_Next.apk` by hand.

### Recovery zip (no PC needed)

```bash
python3 make_recovery_zip.py out_port Nord6_ColorOS17_Port.zip
```

This packs the images folder into a zip for the Nord 6 TWRP. Install it from internal storage or a USB-OTG
drive (exFAT/NTFS: the zip is about 7.7 GB, too big for FAT32), or with `adb sideload` from any PC or phone.
Each image is zstd -19 compressed and stored uncompressed in the zip, so recovery streams it straight
to the partition. `port/manifest.txt` has the size and sha256 of every raw image. The installer is
`assets/recovery/update-binary` (a shell script for TWRP's mksh). It does what `flash_all.bat` does in
fastbootd, with TWRP's own `lptools`, `lpdump`, `zstd`, `unzip` and `bootctl`:

1. Checks: the phone is a Nord 6 (project 24885), the tools exist, no OTA merge is running,
   the images fit in super, and the zip's CRCs are good (for a local file; a sideload streams once). Nothing
   is written before every check passes.
   It also compares the phone's firmware (modem, dsp, tz, xbl, abl and the other 24 firmware partitions of the
   base OTA, sha256 from `--firmware-ref`, default `../base/images`) with the base build, and says whether
   it matches. This is information only. The zip never writes firmware, so the phone keeps the firmware of
   whatever stock build it had (OxygenOS 16 or ColorOS 17). OxygenOS 16.0.5.1300 firmware is fine for the ColorOS 17.0.0.100 base: same GKI kernel build (6.6.118-android15-8, ab15863337), same Android 15 vendor freeze, KeyMint v3 and vendor patch level 2026-10-01 on both, so the firmware check reports "differs" but nothing depends on it.
2. Asks with the volume keys: Vol UP flashes the port's stock init_boot, Vol DOWN keeps the current init_boot
   and with it Magisk/KernelSU root. With no key in 30 s it flashes the stock one.
3. Unmaps whatever recovery mapped from super. If an OTA was pending it cancels it, the same as
   `fastboot snapshot-update cancel`: COW partitions and `/metadata/ota` state are removed and the
   merge status is reset. It then removes the other slot's partitions, scratch and this slot's partitions
   that the zip replaces. It resizes `system_<slot>` and recreates the rest at their new sizes
   (lptools adds new partitions to system's group), writes each image through zstd and reads it back to
   compare its sha256.
4. Writes vbmeta (flags 3), boot, init_boot, vendor_boot and dtbo to the current slot, then marks that slot
   active.
5. If TWRP decrypted /data, it clears the package cache, carrier config cache, Settings search index and system sounds index (the
   dirty-flash clean-up of `flash_all.bat`, no root needed here).
6. It compares the installed system's SDK level with the zip's. If they differ (stock OxygenOS 16 / ColorOS 17 -> port), it
   says Wipe > Format Data is required before rebooting. TWRP's Format Data also deletes the metadata
   encryption key, like `fastboot -w`.

A folder with only some images gives a fix package that replaces only those partitions; the other partitions of
the slot are kept. For a dry run that checks everything and writes nothing, run `adb shell touch
/tmp/port_dryrun` in TWRP first (delete it before the real install). The installer logs to
`/tmp/port_install.log`.

After a change to the installer only, `--reuse OLD.zip` copies every image whose sha256 is unchanged from the
earlier zip instead of compressing it again (minutes instead of ~15).

For **building**, the base should be the Nord 6 ColorOS 17 build this kit was verified on (ColorOS 17.0.0.100,
`CPH2793export_11_17.0.0.100(EX01)`, security patch 2026-10-01; OxygenOS 16 bases are no longer supported since 2026-11-18): the odm
colour calibration in `assets/` equals the 17.0.0.100 file plus the six `24811_*` render intents the donor's colour modes use. With another base the build warns; compare that file first. The donor is a
ColorOS 17 build for the OnePlus 15 (CPH2745, SM8850; verified with `CPH2745_11.C.75_1750_202610181120`; also builds cleanly from `CPH2745_11.C.80_1800_202610290517` / 17.0.1.201). The
Nord 6 is SM8735, so chip-specific donor files must not reach the Nord 6 DSP (see the hotword row below).

## What comes from where

| Partition | Source | Changes |
|---|---|---|
| boot, init_boot, vendor_boot, vendor_dlkm, system_dlkm | base | none |
| dtbo | base | Nord 6 panel nodes get `oplus,ofp-longrui-aod-config = <0xC>` (full-screen + all-day AOD in the display driver) |
| vbmeta, vbmeta_system, vbmeta_vendor | base | flags = 3 (verity and verification off) |
| product, my_bigball, my_carrier, my_engineering, my_heytap, my_region | donor | none |
| vendor | base | fstab avb flags removed; perf HAL: resource [13,32] (0x43480000, L3 min freq, marked unsupported) removed from the tuna (SM8735) boosts in `perfboostsconfig.xml`, which logged "Failed to reset [13,32]" on every scroll |
| odm | base | colour calibration json from `assets/` (includes the 24811_* render intents); `vendor.wv.oemcrypto.debug.enable_prov40=false`: Widevine L1 Provisioning 4.0 fails in this phone's TEE (status 323), so Netflix stopped with error 15001 (-93); Provisioning 3.0 (factory keybox) works |
| system | donor | oplus-services.jar: screen timeout dozes into AOD; in 165 Hz mode the touch-idle rate floors at 120 Hz; the touch panel's report-rate sync (node 242, `refresh_report_sync_support`) follows the display mode, 165/144 at those rates and the HAL default (120) below. Stock ColorOS only sets it inside games (COSA), so in 165 Hz mode touch sampling stayed at the 120 Hz level. Stale oat files removed; services.jar patches for the Miscellaneous page (below); `etc/sysconfig/port_photos_unlimited.xml` (Google Photos unlimited backup); debloat (below) |
| system_ext | donor | OTA app, SystemAppUpdateService and SAUHelper removed; base `display_brightness_config_common.xml`; midasd/ostatsd/ostats_pullerd off; Settings, SettingsProvider (hide developer options), SystemUI and OplusLauncher patches (below); radio subsystem jars renumbered to the Nord 6 HAL (below); stale oat removed |
| my_product | donor | base permission/feature/overlay files and panel configs; ringtones and notification sounds from base (`res/audio/ringtones`, `res/audio/notifications`; the donor's `res/audio/haptic_ringtone/output<F>HZ` sets are removed: they are picked by the OnePlus 15 motor props, which the port drops, so the sound pickers were empty); EuiccGoogle and dolby_vision.cfg removed; wireless charging features removed, battery health added; the all-day panoramic AOD app feature (`com.oplus.systemui.panoramic_aod_all_day.enable`) is left out like base, all-day works from the panel capability in dtbo; game HDR removed; WCG 2.0 off; UniRender off (fixes banded screenshots); refresh rate and VRR configs from base, plus the 165 Hz option; build.prop display props aligned with base; Google hotword enrollment apks (`priv-app/HotwordEnrollment*HEXAGON_WIDEBAND.apk`) from base: the donor's DSP voice model crashes the Nord 6 ADSP whenever "Hey Google" is armed, and each ADSP restart drops charging and USB (Android Auto keeps reconnecting in the car); radio/RF = Nord 6: `oplus.software.radio.*`/`wlan.*` feature declarations equal base (main file and each base `cust/*` region file; donor OnePlus 15 modem/RF features such as rf_power_boost, hyper_uplink_mode_enable, rf_icc_support, esim_* removed), cellular SAR / Wi-Fi SAR / Wi-Fi regulation / Wi-Fi product / RF event configs from base, base `carrierReady/oplus_carrier_config.xml` files and base-only carrier dirs, `CarrierConfigOverlay.product.<project>` from base (the donor one enabled VoData and other NR policies for Airtel/Jio), donor Wi-Fi chip (WCN7861), eSIM, 5GE and PDN props removed, Wi-Fi channel version and ATPC backup TX power from base; SoC/board parity (SM8850 donor -> SM8735 Nord 6): USB PHY tuning, touch report rate, haptic effect tables (base AW8697 motor; donor `ro.oplus.haptic.lra_*` removed), camera osense thread-boost ids, game manager / graphics enhancement (donor SM8850 CPU/GPU frequency table, super-resolution specs, MEMC and Adreno GPU profiles dropped), fusion-light profiles, SM8735 AI-search text-embedding models from base, donor AICore SM8850 feature and Wi-Fi EDCCA config removed, Bluetooth (SAR, RSSI offsets, feature masks) and audio/camera props from base (also `persist.sys.bt.*`: C.80's donor-only `persist.sys.bt.leacoexist` LE Audio dual mode is removed). Animation level stays at the donor's flagship value; debloat (below); Photos no longer drops to 90 Hz on a photo (its gallery entries in `refresh_rate_config.xml` lose `appreqfirst` and get `enableWinOverride="false"`) |
| my_stock | donor | donor-only `ro.oplus.radio.global_regionlock.dynamic` (new in C.80: cloud-synced SIM region-lock policy) removed, so region lock uses the local policy like base; Melody (earbuds app): realme earbuds kept in its model whitelist (the app dropped every realme model unless the phone's brand is realme, so realme buds were ignored; now they get their page in Bluetooth settings), versionCode raised to 1999999999 so a Play Store update can't replace the patched copy (a dirty flash drops an installed update); AOD app: display-mode picker (energy saving / scheduled / always on) shown, it was hidden for video-mode panels; debloat (below) |
| my_manifest | donor | device identity rewritten to CPH2793 / OP6135L1 / "OnePlus Nord 6"; ab_ota_partitions taken from base |

Debloat (`DEBLOAT` in build_port.py), background services and preloads that cost CPU, battery and data:
my_stock StdSP (app-install "safety scan" verifier; every install waited on it, also carried an ad SDK),
SecurityGuard, DCS (Oplus telemetry), RomUpdate, Cota, MCS (push/ads), KeKeMarket,
Browser, SoftsimRedteaRoaming, OPMemberShip, DeviceIntegrationService, LinktoWindows and the INOnePlusStore,
OPForum, Pictorial and Tips stubs; my_product Facebook services/installer/appmanager/app stub with their
permission and sysconfig files, Meet and FamilyLinkParentalControls, YouTube and Google Photos (not bloat, but as preinstalled system apps they break ReVanced/RVMM modules: the module installs its own stock version, which fails as a downgrade under a newer system copy; installed from Play Store or by the module they are normal, uninstallable user apps); system_ext SystemAppUpdateService and
SAUHelper; system Traceur and CrossDeviceServiceBroker (Link to Windows backend). Traceur goes because
OplusQualityProtect, Olc and oplus-services start "health" traces through it (`oplus.intent.action.TRACEUR_START_TRACING`):
on the donor build the session ran around the clock (19 data sources, 124 MB ring buffer, about an hour of
traced_probes CPU over three days) and dumped ~35 MB `health_trace-*.perfetto-trace` files into
`/data/local/traces` several times a day, so the phone ran warm and drained idle. Without Traceur the requests go
nowhere; Developer options loses "System Tracing" (perfetto from adb still works). OnePlus AI apps (AIUnit, aiassistant, AIMemory, AIWriter, AISeal, AONService, AICallAssistant,
Gleaner, Metis, SandboxRuntime) are kept. ColorOS re-installs system apps that were only uninstalled per user,
which is why they are removed from the images. Play Protect (Play Store) stays the package verifier.

Minimal Google (optional, picked in flash_all.bat): the build also writes `my_product_lite.img` (`GOOGLE_MINIMAL`
in build_port.py, on top of the debloat above; `--no-google-minimal` skips it). It keeps Google Play services, the
Google Services Framework, Play Store, the Google app with "Hey Google", Speech Services (voice and TTS for the
Assistant and Android Auto) and Android Auto, plus what the phone has no replacement for (Gboard is the only
keyboard, Google Messages the only SMS app, WebView with Trichrome) and setup/system pieces (SetupWizard, Partner
Setup, Restore, SearchSelector, PackageInstaller, ExtShared, ConfigUpdater, Developer Verifier, Emergency info).
Removed: Chrome, Gmail, Maps, Calendar, Gemini, Lens, Wallet, GPay, Files, Google Contacts, Google Dialer,
Digital Wellbeing, AICore, Android System Intelligence, Private Compute Services, Cross-Device Services,
Personal Safety, TalkBack, Switch Access, Android Device Policy, Location History, Odad, Feedback, Print
Recommendation, Play Auto Install config and the removable Drive, Find My Device, Fitbit, Home, Google One,
Videos and YT Music preinstalls. No OnePlus app depends on any of them (manifest scan). Chrome goes too, so
there is no browser until one is installed from Play Store. After boot the script can uninstall, over adb for
user 0, the packages in `google_minimal_packages.txt`: on a dirty flash a removed system app that Play Store had
updated keeps its update as a user app, and ARCore sits in my_stock. Going back to Standard brings the apps back
fresh, without their old data.

Settings: the About-device ColorOS banner shows without the OTA app; the pill text is `--banner-text`
(C.80 made the pill a plain text label; the kit turns it back into the translucent pill button);
the Quick glance card is gone; the Software update row stays hidden.
Developer options > Window / Transition / Animator duration scale: "Animation off" is removed and a "Custom…"
entry opens a number box that takes any value from 0.5x to 10x (anything else is refused with a toast). The scale is
a duration multiplier: 1.5x is slower, 0.5x is the fastest. The three stock controllers hand `updateState` and
`onPreferenceChange` to `AnimScale` (`assets/misc/smali`, in the Miscellaneous dex; `misc.patch_anim_scale`).
Settings > Miscellaneous (`lib/misc.py`, page code in `assets/misc/smali`, its own card above Aeroplane mode):
- Allow screenshots in secure apps: writes Secure `disable_secure_windows` (WindowManagerService only honours it on
  debuggable builds; services.jar drops that check) and `persist.sys.port.secure_video` (framework.jar:
  `SurfaceView.setSecure(true)` becomes false, so video and camera views are captured too). DRM video stays black.
- Keep recording when locked: writes System `recording_settings_enable_screen_off_pause`, which the ColorOS screen
  recorder reads before stopping a recording on screen off.
- Allow app downgrades: sets `persist.sys.port.allow_downgrade`; `PackageManagerServiceUtils.isDowngradePermitted`
  returns true while it is 1 (no `-d` or debuggable build needed).
- Hide developer options from apps + Choose apps: Global `port_hide_dev` (switch) and `port_hide_dev_pkgs`
  (comma-separated packages, picked on the Choose apps page, which lists user-installed apps). SettingsProvider.apk
  (system_ext): `packageValueForCallResult`, which builds every settings read reply, first calls an injected
  `portDevHidden(name)`. For `development_settings_enabled`, `adb_enabled` and `adb_wifi_enabled` it reads both
  settings with the caller identity cleared and, if the switch is on and the calling app uid (appId >= 10000) has a
  picked package, answers "0" (`PortDevHide`, `assets/misc/settingsprovider`). The real values and every other
  caller are untouched. The apk is rewritten with its signing block kept, and its stale oat is removed. ColorOS's
  own `SettingsFilter` already answers 0 to some apps (Airtel, for example) whatever this switch says.
- Snapchat as Pixel: `persist.sys.port.spoof_snapchat`; framework.jar `Instrumentation.newApplication` calls
  `PortSpoof` (new class, `assets/misc/framework`), which gives com.snapchat.android the Pixel XL Build values.
- Google Photos unlimited backup (on by default, `persist.sys.port.photos_unlimited=1` in system build.prop):
  `etc/sysconfig/port_photos_unlimited.xml` declares Photos' NEXUS/PIXEL/PIXEL_2016 preload features (all Photos
  checks; no Build spoof), and framework.jar `ApplicationPackageManager.hasSystemFeature` hides them while the
  switch is off.
The three `persist.sys.port.*` props read by app processes are labelled `exported_system_prop` in
`plat_property_contexts` (apps can't read `system_prop`). framework.jar is reassembled with smali 3 (`tools/smali3`);
the system boot image no longer matches it, so ART builds one in /data on the first boot (slower first boot).
Radio subsystem: the donor's `vendor-subsystem-service`, `oplus-subsystem-service` and `oplus-subsystem-service-ext` jars use the ColorOS 17 numbering (V1) of `vendor.oplus.hardware.subsys_interface.subsys_radio`, while the Nord 6 odm `subsys_daemon` implements V9. Almost every call reached a different HAL function (setCallback ran readNv, so all modem replies were dropped and com.oplus.subsys timed out; other calls hit modem setters). `lib/subsysradio.py` reads both code tables from the base and donor jars, checks signatures and parcelable layouts, and renumbers the proxy calls (calls the base HAL lacks fail cleanly as Unimplemented) and the response/indication callbacks.
SystemUI: Seamless AOD style is available; panoramic (full-wallpaper) AOD with all display modes (energy saving: hides after about 5 s and comes back on lift; scheduled; always on); screen timeout goes to AOD the same way the power button does;
the lock-screen carrier label is aligned.
OplusLauncher (`assets/launcher`): replaced by the user-supplied Zuyqa modded launcher 17.3.9 (its own
frosted dock, Custom features page, Recents options), with the Home screen search button's Breeno option
turned into Google (opens the Google app search, pill "Ask Google") and the mod credit headers removed.
Built into system_ext it needs no root or Magisk/KSU module. Details and rebuild steps in
`assets/launcher/README.txt`. (The earlier dock bar / liquid glass patch is retired.)

## If a newer donor breaks a step

`BUILD_REPORT.txt` and the console name the failing step, for example
`FAILED: SystemUI.apk patches: ... pattern matched 0 times`. Usually the donor changed that code.
Either drop that step with `--keep-going` (you lose only that fix), or update the matcher in
`lib/patches.py`. Each function's docstring says what it changes.

**Flashing over an existing port without a data wipe:** files in these images all have mtime 0, so
PackageManager keeps its cached parse of an apk whose manifest changed (it would still show the old
version). Clear the entry and reboot, e.g. for the hotword apks:
`adb shell su -c 'rm /data/system/package_cache/*/HotwordEnrollment*'` then `adb reboot`.
If "Hey Google" was trained on the old build, retrain the voice model once so the base model is stored.

After the first boot you can optionally run
`adb shell cmd package compile -m speed-profile -f com.android.systemui` (and the same for
`com.android.settings` and `com.android.launcher`), so the patched apps don't run from the APK/JIT until the next background dexopt.

## TWRP (bundled)

`assets/twrp_nord6.img.gz` (gzipped; the build writes `twrp_nord6.img` to the output) is our Nord 6 TWRP (v6, md5 65e97bdc6ac0745d7f5db568fb399a82; decrypts the port's
data, own FastbootD). The build copies it next to `flash_all.bat`, which now:
1. in the bootloader flashes vbmeta (verification off) and installs TWRP to the current slot's recovery
   (a phone that starts in some FastbootD is sent back to the bootloader first),
2. reboots into TWRP FastbootD (`fastboot reboot fastboot`) and waits for it,
3. flashes boot/init_boot/vendor_boot/dtbo and 4. the logical partitions from TWRP FastbootD.
Stock or other recoveries' FastbootD are no longer used for flashing. TWRP stays as the recovery.


## Working on the kit with an AI agent

All agent instructions are in `AGENTS.md`: ground rules, the user's setup, commands, layout and every decision
already tested on the phone. `CLAUDE.md` (Claude Code), `GEMINI.md` (Gemini CLI), `.agent/rules/port-kit.md`
(Google Antigravity) and `.github/copilot-instructions.md` (GitHub Copilot) only point to it; Codex (ChatGPT's coding
agent), Cursor and others read `AGENTS.md` directly. Open the `port_kit` folder as the workspace.

In a chat with no file access (ChatGPT, Gemini or Claude on the web), upload `AGENTS.md` and `README.md` (or the
kit zip) and start with: "Read AGENTS.md and README.md first and follow AGENTS.md. Every fix must become a build
step in the kit." Whatever an agent learns that the next one needs goes into `AGENTS.md`, not into that service's
memory.
