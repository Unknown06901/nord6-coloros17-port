# Instructions for AI agents

This file is for any AI coding agent working on this kit (Gemini CLI, Google Antigravity, Claude Code,
ChatGPT / Codex, Cursor, GitHub Copilot and others). Keep everything in this file and `DECISIONS.md`
(device-verified decisions and dead ends); the other instruction files only point here (when you add a pointer for a
new tool, keep it a pointer and add it to this table and to the README's agent section):

| Agent | Reads |
|---|---|
| Codex (ChatGPT's coding agent, CLI and cloud), Jules, OpenCode, Zed, Factory and most others | `AGENTS.md` |
| Claude Code | `CLAUDE.md` -> `AGENTS.md` |
| Gemini CLI | `GEMINI.md` -> `AGENTS.md` |
| Qwen Code | `QWEN.md` -> `AGENTS.md` |
| Google Antigravity | `AGENTS.md` and `GEMINI.md` natively, plus `.agents/rules/port-kit.md` (always on) and `.agents/rules/decisions.md` (loaded when relevant) |
| GitHub Copilot | `.github/copilot-instructions.md` -> `AGENTS.md` |
| Cursor | `AGENTS.md`, plus `.cursor/rules/port-kit.mdc` (always apply) -> `AGENTS.md` |
| Windsurf | `.windsurf/rules/port-kit.md` (always on) -> `AGENTS.md` |
| Cline / Roo Code | `.clinerules/port-kit.md` -> `AGENTS.md` |
| Amazon Q Developer | `.amazonq/rules/port-kit.md` -> `AGENTS.md` |
| JetBrains Junie | `.junie/guidelines.md` -> `AGENTS.md` |
| Kiro | `.kiro/steering/port-kit.md` (always included) -> `AGENTS.md` |
| Aider | `.aider.conf.yml` loads `AGENTS.md`, `DECISIONS.md` and `README.md` read-only into every chat |
| A chat without file access (ChatGPT, Gemini or Claude on the web) | Upload `AGENTS.md`, `DECISIONS.md` and `README.md` (or the kit zip) and say "follow AGENTS.md" |

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
  `/mnt/vendor/my_*`. The only copy of its scripts is on the phone (`/data/adb/modules/port_melody_blur/`); the PC
  copy was deleted on 2026-11-22.

## What this kit is

It builds a ColorOS 17 port ROM for the **OnePlus Nord 6** from two official firmware packages:

| | Device | Model / project | SoC | Verified build |
|---|---|---|---|---|
| Base | OnePlus Nord 6 (ColorOS 17) | CPH2793, OP6135L1, project 24885 | SM8735 | `CPH2793export_11_17.0.0.100(EX01)` |
| Donor | OnePlus 15 (ColorOS 17, Android 17) | CPH2745, OP611FL1, project 24863 | SM8850 | `CPH2745_11.C.75_1750_202610181120` (17.0.0.102 EX01); C.80 (17.0.1.201 EX01) builds cleanly, see note below |

The Nord 6 panel is a **165 Hz LTPS video-mode panel** (`AA610_P_3_A0034_dsc_video_mode_panel`), not LTPO. It
can't refresh at 1 Hz, so donor features that need LTPO must stay off. Panoramic and all-day AOD work through
the driver's full-screen AOD mode, enabled by the port's dtbo edit (see `DECISIONS.md`).

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
6. **Don't redo the dead ends** listed in `DECISIONS.md` without new evidence.

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

## Decisions and dead ends

Everything already tested on the phone (what works, what was tried and failed, and why) is in **`DECISIONS.md`**.
Read it before changing any build step or patch. It is kept out of this file so `AGENTS.md` stays under
Antigravity's 24,000-byte rule-file limit (Antigravity cuts longer files off): keep this file under about 20 KB
and put new decisions in `DECISIONS.md`.

## Definition of done

- `python3 -m py_compile build_port.py make_recovery_zip.py lib/*.py` passes.
- `python3 build_port.py --check ...` says "ready to build".
- A full build finishes with no `FAILED` lines, and `BUILD_REPORT.txt` lists your new step.
- `README.md` describes the change in the partition table or the debloat/patch notes.
- The phone boots, and the feature was checked on the device by the user, or you said clearly that it
  wasn't.
