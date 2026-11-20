# Instructions for AI agents

This file is for any AI coding agent working on this kit (Gemini CLI, Google Antigravity, Claude Code,
ChatGPT / Codex, Cursor, GitHub Copilot and others). Keep everything in this one file; the other instruction
files only point here (when you add a pointer for a new tool, keep it a pointer and add it to this table and to
the README's agent section):

| Agent | Reads |
|---|---|
| Codex (ChatGPT's coding agent, CLI and cloud), Jules, OpenCode, Zed, Factory and most others | `AGENTS.md` |
| Claude Code | `CLAUDE.md` -> `AGENTS.md` |
| Gemini CLI | `GEMINI.md` -> `AGENTS.md` |
| Qwen Code | `QWEN.md` -> `AGENTS.md` |
| Google Antigravity | `.agent/rules/port-kit.md` (always on) -> `AGENTS.md` |
| GitHub Copilot | `.github/copilot-instructions.md` -> `AGENTS.md` |
| Cursor | `AGENTS.md`, plus `.cursor/rules/port-kit.mdc` (always apply) -> `AGENTS.md` |
| Windsurf | `.windsurf/rules/port-kit.md` (always on) -> `AGENTS.md` |
| Cline / Roo Code | `.clinerules/port-kit.md` -> `AGENTS.md` |
| Amazon Q Developer | `.amazonq/rules/port-kit.md` -> `AGENTS.md` |
| JetBrains Junie | `.junie/guidelines.md` -> `AGENTS.md` |
| Kiro | `.kiro/steering/port-kit.md` (always included) -> `AGENTS.md` |
| Aider | `.aider.conf.yml` loads `AGENTS.md` and `README.md` read-only into every chat |
| A chat without file access (ChatGPT, Gemini or Claude on the web) | Upload `AGENTS.md` and `README.md` (or the kit zip) and say "follow AGENTS.md" |

Agent memory (Claude memory, Gemini memories, ChatGPT memory) is not shared between services. Anything another
agent needs to know goes in this file, never only in an agent's private memory. `README.md` describes every
change the build makes; read it before changing a step.

## The user's setup

- Kit folder: `~/port/port_kit` on WSL2 (Ubuntu) under Windows. Inputs and outputs sit next to it: `~/port/base/images`
  (Nord 6 ColorOS 17.0.0.100), `~/port/donor_c80/images` (OnePlus 15 ColorOS 17 C.80), `~/port/out_*` (build outputs), and a
  build log `~/port/_<name>_build.log` per build.
- The kit is a git repo, pushed to the private GitHub repo `Unknown06901/nord6-coloros17-port` (`main`). Commit
  kit changes with a clear message; push when the user asks. Build inputs and outputs are never committed.
- adb is the Windows binary, called from WSL:
  `/mnt/c/Users/Shaml/Desktop/platform-tools-latest-windows/platform-tools/adb.exe`. It takes Windows paths for
  push/pull (for example `C:\Users\Shaml\Downloads\...`), so stage files under `/mnt/c/Users/Shaml/Downloads/`.
- Two phones can be connected; pass `-s`. The Nord 6 (this port) is serial `3C166L00D3K00000`. The other one
  (`5212c457`, Redmi Note 5 Pro on VoltageOS) has nothing to do with this kit.
- The Nord 6 runs KernelSU Next (no metamodule) and Meow Zygisk (see "Testing on the phone").
- The user flashes, reboots and unlocks the phone themselves, and replies "Rebooted" when it is back.
- **Melody earbud popup work stays out of the kit.** The case-open popup, its blur and the realme Buds Air6 Pro image
  packs live only in the KernelSU module `port_melody_blur` on the user's phone. Don't add them here. The kit's only
  Melody step is the realme whitelist patch (`patch_melody`).
  The module's `post-fs-data.sh` rebuilds `/product/overlay` from the my_* overlay dirs. With a mount path that
  doesn't exist the merge loses every my_* overlay and zygote aborts with `Not allowlisted (70): /my_product/cust/...`
  (bootloop that looks like a port bug). Since 2026-11-18 it uses `/my_*` (ColorOS 17 base) and falls back to
  `/mnt/vendor/my_*`; a copy of its scripts is in `~/port/melody_realme_module/port_melody_blur_scripts/`.

## What this kit is

It builds a ColorOS 17 port ROM for the **OnePlus Nord 6** from two official firmware packages:

| | Device | Model / project | SoC | Verified build |
|---|---|---|---|---|
| Base | OnePlus Nord 6 (ColorOS 17) | CPH2793, OP6135L1, project 24885 | SM8735 | `CPH2793export_11_17.0.0.100(EX01)` |
| Donor | OnePlus 15 (ColorOS 17, Android 17) | CPH2745, OP611FL1, project 24863 | SM8850 | `CPH2745_11.C.75_1750_202610181120` (17.0.0.102 EX01); C.80 (17.0.1.201 EX01) builds cleanly, see note below |

The Nord 6 panel is a **165 Hz LTPS video-mode panel** (`AA610_P_3_A0034_dsc_video_mode_panel`), not LTPO. It
can't refresh at 1 Hz, so donor features that need LTPO must stay off. Panoramic and all-day AOD work through
the driver's full-screen AOD mode, enabled by the port's dtbo edit (see Decisions).

`build_port.py` takes the base's boot chain, kernel, vendor and odm, and the donor's system partitions. It then
applies every fix that was made and tested on a real phone. Each code patch finds its target by class,
method and instruction pattern, never by file offset, and stops the build if the pattern isn't found exactly
once.

## Ground rules

1. **Never flash, wipe, format, or reboot the phone to the bootloader, recovery or fastboot unless the user
   asks for that exact action.** Reading (adb shell, logcat, dumpsys, pulling files) is fine. Changes that a
   reboot undoes, such as a bind mount or a setting, are fine for testing, but say what you changed and
   revert it when you're done.
2. **Never save the phone's PIN or password** to a file, memory or log. Ask the user for it each session.
3. **Every fix must end up in the kit.** A change tested only on the phone is lost on the next build. Turn it
   into a build step (see "Adding or changing a fix"), add it to the `README.md` table, and note it in the
   output's `BUILD_REPORT.txt` if you patched an existing output by hand.
4. **Keep patches pattern-based.** Use the helpers in `lib/dexpatch.py`, which raise `PatchError` instead of
   writing a broken file. No hard-coded offsets, no absolute paths, no paths outside the kit except the
   `--base/--donor/--out/--work` arguments.
5. **Respect the hardware.** Only port features the Nord 6 hardware supports: SM8735, LTPS panel, no
   wireless charging, no eSIM. When in doubt, compare with the base (stock Nord 6) files; the base is the
   reference for what the device supports.
6. **Don't redo the dead ends** listed at the end of this file without new evidence.

## Requirements

- Linux or WSL2, about 80 GB free for `--work` when both inputs are OTA zips (40 GB with image folders).
- `python3` 3.8+ (standard library only) and `java` 11+ (`sudo apt install openjdk-21-jre-headless`).
- Everything else ships in `tools/`: erofs-utils 1.8.10 (`extract.erofs`, `mkfs.erofs`, `fsck.erofs`),
  `payload-dumper-go`, smali/baksmali 2.5.2, smali/baksmali 3.0.10 in `tools/smali3` (framework.jar only).
- Flashing is done by the user on Windows with `flash_all.bat` (fastboot from Android platform-tools) or
  from TWRP with the recovery zip.

## Commands

```bash
# 1. check tools, java, inputs and disk space (builds nothing)
python3 build_port.py --check --base Nord6_ColorOS17_OTA.zip --donor OnePlus15_ColorOS17_OTA.zip --out out_port

# 2. build (about 10 minutes plus unpacking); output = images + flash_all.bat + BUILD_REPORT.txt
python3 build_port.py --base Nord6_ColorOS17_OTA.zip --donor OnePlus15_ColorOS17_OTA.zip --out out_port

# 3. optional: TWRP-flashable zip of the output
python3 make_recovery_zip.py out_port Nord6_ColorOS17_Port.zip --firmware-ref BASE_IMAGES_DIR

# 4. firmware fix folder for phones still on OxygenOS 16 firmware (Android Auto / Hey Google fix)
python3 make_firmware_fix.py BASE_IMAGES_DIR_OR_OTA out_fw_fix
```

`--base` and `--donor` take an images folder, a `payload.bin`, a full OTA zip or a fastboot zip.
Other options: `--keep-going` (report failing patches instead of stopping), `--keep-work`,
`--banner-text`, `--level`. After a build, read `BUILD_REPORT.txt`: it must have no `FAILED` or `WARNING`
lines you can't explain.

## Layout

| Path | What it is |
|---|---|
| `build_port.py` | The whole build: partition plan, per-partition steps (`do_vendor`, `do_odm`, `do_system`, `do_system_ext`, `do_my_product`, `do_my_stock`, `do_my_manifest`), `DEBLOAT` list, image packing |
| `lib/patches.py` | Code patches for Settings, SystemUI and `oplus-services.jar` (each function's docstring says what and why) |
| `lib/dexpatch.py` | Same-size dex patching inside apk/jar, `resources.arsc` string edits, binary-XML attribute insert |
| `lib/misc.py`, `assets/misc/` | Settings > Miscellaneous page (appended dex + top-level row), Developer options animation-scale box (`AnimScale`) and its back ends: services.jar, framework.jar (smali 3, `PortSpoof`), SettingsProvider.apk (`PortDevHide`), app-readable props, Photos sysconfig |
| `lib/subsysradio.py` | Renumbers the donor's subsys_radio HAL calls to the Nord 6 HAL version |
| `make_recovery_zip.py`, `assets/recovery/` | TWRP zip builder and its installer script |
| `make_firmware_fix.py`, `assets/firmware/` | Firmware fix folder: the base build's firmware images + `flash_firmware.bat` (modem from the bootloader, the rest from fastbootd, no wipe, root kept) |
| `assets/fastboot_driver/` | Windows WinUSB driver for USB `18D1:D00D` (Nord 6 bootloader and fastbootd); `install_driver.ps1` needs an Administrator PowerShell |
| `assets/flash_all.bat`, `assets/ksu_root.ps1` | Windows flasher (clean/dirty flash, log collection) and the KernelSU Next init_boot patcher |
| `assets/twrp_nord6.img.gz` | Nord 6 TWRP, gzipped (the build writes `twrp_nord6.img` to the output); `flash_all.bat` flashes the port from its FastbootD |
| `assets/odm/` | Display colour calibration for the Nord 6 panel |
| `assets/launcher/` | Prebuilt launcher (Zuyqa 17.3.9 + Google search button) and the script that made it |
| `tools/` | Bundled binaries (see Requirements) |

## How the build works

1. Unpack both inputs to image folders; check the identity (`my_manifest/build.prop`) and warn if the base or
   donor differs from the verified builds.
2. Copy unchanged images: boot chain and `*_dlkm` from base, `product` and the small `my_*` images from donor,
   and `vbmeta*` from base with flags 3 (verification off).
3. Extract the partitions to rebuild (vendor and odm from base; system, system_ext, my_product, my_stock and
   my_manifest from donor), apply each `do_*` step, and repack with `mkfs.erofs` (lz4hc, 16 KiB clusters,
   same UUID, file times = build time). `Part.write_config()` regenerates `fs_config` and `file_contexts` from
   the extracted metadata, so added files must go through `Part.add_from()` to get correct owners and labels.
4. Write `BUILD_REPORT.txt`; every `LOG()` line ends up there.

## Adding or changing a fix

- **Remove an app or file:** add its path to `DEBLOAT[partition]` in `build_port.py` with a comment saying why.
  Remove its permission/sysconfig xmls too if it has them.
- **Take a file from base:** use `Part.add_from()` inside the right `do_*` step and `LOG()` the reason.
- **Edit an xml or prop:** use `xml_edit()` / `edit_props()`. Match single lines with regexes like
  `_app_features()` does, so the rest of the file stays byte-identical.
- **Patch app or framework code:**
  1. Disassemble the target to understand it:
     `java -jar tools/baksmali-2.5.2.jar d classes.dex -o out_smali` (unzip the dex from the apk or jar first).
  2. If the change keeps the instruction size (flip a register, a branch target or a constant), write a
     function `fn(dex)` in `lib/patches.py` that finds the site with `dex.insns(class, method)` and
     `find_one(...)`, then edits `dex.d` in place. Call it from `patch_settings` / `patch_systemui` /
     `patch_services_jar` through `patch_dex_in_zip(apk, class, fn, label)`. See `systemui_seamless_aod` for
     a small example.
  3. If it needs new instructions, write a smali patcher and use `smali_patch_jar()` (see
     `services_vrr_smali`), which reassembles that one dex.
  4. Write a docstring that explains what the patch changes and why the stock code misbehaves on the Nord 6.
- **Check before a full build:** `python3 -m py_compile build_port.py lib/*.py`. Then test the single patch
  on the apk/jar pulled from the phone (`adb pull /system_ext/priv-app/SystemUI/SystemUI.apk`), for example
  `python3 -c "import sys; sys.path.insert(0,'lib'); import patches; patches.patch_systemui('SystemUI.apk', print)"`.

## Testing on the phone

The phone runs this port, rooted with KernelSU Next (`su` works in `adb shell`). Useful patterns:

- **Meow Zygisk unmounts every /data-sourced mount inside app processes** (it manages `kernel_umount`), so a
  bind mount from `/data/local/tmp` is seen by system_server but not by apps. Copy the test file to tmpfs first
  (`mkdir /dev/port_t; cp ... /dev/port_t/`) and bind-mount from there. Some banking/UPI apps (PhonePe) detect
  such mounts and close; reboot without the mounts before the user uses them.
- **Patched framework.jar, services.jar or a provider apk** needs the mount before zygote starts: a test KernelSU
  module whose `post-fs-data.sh` copies the files to /dev and bind-mounts them (module `system/` folders are not
  mounted without a metamodule). Disable it by renaming `post-fs-data.sh` to `.off`; it takes effect on reboot.
- **Try a patched system apk without flashing** (the original comes back on reboot):
  ```bash
  adb push SystemUI.patched.apk /data/local/tmp/
  adb shell su -M -c "mount -o bind /data/local/tmp/SystemUI.patched.apk /system_ext/priv-app/SystemUI/SystemUI.apk"
  adb shell su -c "kill \$(pidof com.android.systemui)"
  ```
  Undo with `su -M -c "umount -l <same path>"` and restart the app. `-M` makes the mount visible to every
  app's mount namespace. Restarting SystemUI locks the screen; the user unlocks it.
- **Logs:** `adb logcat -b main,system` with tags `SystemUi--Aod`, `SystemUi--Keyguard`, `AODDisplayUtil`;
  `dumpsys display | grep mState` shows ON / DOZE / OFF.
- **Settings written by an experiment can outlive it.** SystemUI writes some secure settings once and skips
  them later (for example `oplus_keyguard_panoramic_aod_support`). After reverting, set them back by hand and
  check with `settings get secure <name>`.
- Keep the screen on during tests with `settings put system screen_off_timeout 300000`, and tell the user to
  restore their own value afterwards.

## Decisions and dead ends (verified on the device)

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
  secure screenshots, plus a root backend). The code is in `../unknwn_addons_backup.zip` (with HOW-TO-RESTORE.txt).
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

## Definition of done

- `python3 -m py_compile build_port.py make_recovery_zip.py lib/*.py` passes.
- `python3 build_port.py --check ...` says "ready to build".
- A full build finishes with no `FAILED` lines, and `BUILD_REPORT.txt` lists your new step.
- `README.md` describes the change in the partition table or the debloat/patch notes.
- The phone boots, and the feature was checked on the device by the user, or you said clearly that it
  wasn't.
