#!/usr/bin/env python3
"""OnePlus Nord 6 ColorOS 17 port builder.

Base  = stock Nord 6 OxygenOS 16 images (verified: 16.0.5.1300; earlier 16.0.5.702)
Donor = ColorOS 17 images (OnePlus 15 build; may be replaced by newer builds)

Every step below reproduces a fix that was made and verified on the device by hand
(see README.md). Steps that cannot find what they expect in a new donor stop the build
(or, with --keep-going, are reported as FAILED in BUILD_REPORT.txt) instead of silently
producing a broken image.

usage: build_port.py --base BASE --donor DONOR [--out DIR] [--work DIR]
       BASE / DONOR = images folder, payload.bin, OTA zip or fastboot zip
"""
import argparse
import glob
import gzip
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(KIT, 'lib'))
import patches  # noqa: E402
import misc  # noqa: E402
import subsysradio  # noqa: E402
from dexpatch import PatchError, manifest_package  # noqa: E402

PORT = os.path.dirname(KIT)

# ---------------------------------------------------------------- partition plan

TAKE_FROM_BASE = ['boot', 'init_boot', 'vendor_boot', 'dtbo', 'vendor_dlkm', 'system_dlkm']
TAKE_FROM_DONOR = ['product', 'my_bigball', 'my_carrier', 'my_engineering', 'my_heytap', 'my_region',
                   'my_company', 'my_preload']            # the last two only if the donor has them
VBMETA = ['vbmeta', 'vbmeta_system', 'vbmeta_vendor']      # base, verity + verification disabled
REBUILD = {                                                # partition -> source tree it starts from
    'vendor': 'base', 'odm': 'base',
    'system': 'donor', 'system_ext': 'donor', 'my_product': 'donor', 'my_stock': 'donor', 'my_manifest': 'donor',
}

# my_product files that must describe the Nord 6 hardware, taken from base as-is
BASE_MY_PRODUCT_FILES = [
    'etc/permissions/com.oplus.android-features.xml',
    'etc/permissions/com.oplus.product.connectivity.common.features.xml',
    'etc/permissions/com.oppo.features_allnet_android.xml',
    'etc/permissions/oplus.feature.android.xml',
    'etc/permissions/oplus.features.connectivity.xml',
    'etc/permissions/oplus.product.display_features.xml',
    'etc/permissions/oplus.product.feature_audio_route.xml',
    'etc/permissions/oplus.product.feature_multimedia_unique.xml',
    'etc/permissions/oplus.product.feature_video_unique.xml',
    'etc/permissions/oplus.product.features_audiox.xml',
    'etc/permissions/oplus.product.features_gameeco_common.xml',
    'etc/permissions/oplus.product.features_gameeco_unique.xml',
    'etc/permissions/oplus.product.features_multimedia_common.xml',
    'etc/permissions/privapp-permissions-google-comms-suite.xml',
    'etc/permissions/privapp-permissions-google-odad.xml',
    'etc/permissions/privapp-permissions-google-product.xml',
    'etc/permissions/privapp-permissions-google-system.xml',
    'etc/permissions/privapp-permissions-google-system_ext.xml',
    'etc/permissions/privapp-permissions-oplus-product.xml',
    'overlay/android_framework_res_rro_export_oneplus.apk',
    'overlay/aon.frameworkres.overlay.product.apk',
]
# Google DSP hotword: the enrollment apks carry the voice model loaded into the ADSP. The donor's
# (SM8850) model crashes the Nord 6 ADSP audio_process as soon as "Hey Google" is armed, and every
# ADSP restart drops charging + USB (Android Auto reconnect loop). Base apks = base model.
HOTWORD_APKS = [
    'priv-app/HotwordEnrollmentXGoogleHEXAGON_WIDEBAND.apk',
    'priv-app/HotwordEnrollmentYGoogleHEXAGON_WIDEBAND.apk',
]
# display and carrier-config overlays are per project id (donor 24863 -> base 24885); the donor carrier
# overlay turned on VoData and other 5G/NR policies for Airtel/Jio that the Nord 6 does not use
PROJECT_OVERLAYS = ['android_framework_res_overlay.display.product', 'oplus_framework_res_overlay.display.product',
                    'com.android.SystemUIResOverlay', 'CarrierConfigOverlay.product']
# RF calibration-side configs (cellular SAR backoff, Wi-Fi SAR/regulation/product for the WCN7750,
# RF events) describe the Nord 6 antennas and chips: always base
BASE_MY_PRODUCT_RF_RE = re.compile(r'^(sar_config.*|wifisarconfig|wifi_product_config|wifi_regulation_config.*|rf_event_config.*)\.xml$')
# radio/wlan oplus-feature declarations must equal base (donor OnePlus 15 modem/RF features such as
# rf_power_boost, hyper_uplink_mode_enable, rf_icc_support, esim_* now really reach the modem)
RADIO_FEATURE_RE = re.compile(r'^\s*<(oplus-feature|unavailable-oplus-feature)\s+name="(oplus\.software\.(?:radio|wlan)\.[^"]+)"\s*/>\s*$')
# donor-only things that have no hardware on Nord 6 or broke it
DONOR_MY_PRODUCT_REMOVE = [
    'priv-app/EuiccGoogle',                                 # no eSIM: NPE on every boot
    'etc/permissions/EuiccGoogle_grant_permissions_list.xml',
    'etc/default-permissions/default-permissions-euicc.xml',
    'etc/dolby_vision.cfg',                                 # base panel has no Dolby Vision
]
# panel/display files under my_product/vendor/etc come from base; donor ones are for its panels
PANEL_FILE_RE = re.compile(r'(display|brightness|eyeprotect|sensor_lock|apollo|multimedia_)', re.I)

MY_PRODUCT_PROPS_DELETE = [
    'ro.oplus.sys.unirender.composeuni.enable', 'persist.sys.unirender.composeuni.enable',
    'persist.sys.altair.composeuni.enable',                 # UniRender: screenshot band corruption
    'ro.oplus.lcd.display.screen.underlightsensor.screensize',
    'ro.display.brightness.dobly.enter.rate', 'ro.display.brightness.dobly.exit.rate',
    'persist.sys.feature.dolby_vision',
    'persist.oplus.display.vrr.adfr', 'persist.oplus.display.vrr.pdfr', 'persist.oplus.display.minifps.normalize',
    'ro.oplus.display.peak.brightness.duration_time', 'ro.oplus.display.peak.brightness.effect_interval_time',
    'ro.oplus.display.peak.brightness.effect_times_every_day', 'ro.oplus.display.sell_mode.max_normal_nit',
    'persist.sys.renderengine.maxLuminance',                # brightness parity with base
    'vendor.display.force_tonemapping',                     # donor odm value; base has none (forces HDR->SDR in the composer)
    'ro.vendor.wifi.manufacturer', 'ro.vendor.wifi.model',  # donor WCN7861; Nord 6 has WCN7750
    'ro.vendor.oplus.radio.esim.feature', 'setupwizard.feature.esim_enabled',  # no eSIM (base esim HAL acted on it)
    'ro.oplus.radio.5ge_type', 'ro.vendor.oplus.radio.pdn_already_exist',      # donor-only radio props
]
MY_PRODUCT_PROPS_FROM_BASE = [                              # replaced in place with the base value
    'ro.oplus.display.screenhole.positon', 'ro.lcd.display.screen.underlightsensor.region',
    'ro.oplus.lcd.display.screen.underlightsensor.region', 'persist.sys.feature.localhdr_version',
    'persist.sys.wifi.channel.version',
]
MY_PRODUCT_PROPS_APPEND = [
    ('Nord 6 (base) display / color / HDR values', [
        'persist.sys.feature.localhdr_secondary_display_support', 'ro.display.brightness.thread.priority',
        'ro.oplus.display.back_camera_disable_led', 'ro.oplus.display.colormode.cinema',
        'ro.oplus.display.colormode.colorful', 'ro.oplus.display.colormode.soft', 'ro.oplus.display.colormode.vivid',
        'ro.oplus.display.screen.heteromorphism', 'ro.build.device_family', 'ro.product.oplus.cpuinfo',
        'persist.sys.feature.colormanager.v1.plus']),
    ('Nord 6 (base) Wi-Fi auto TX power', ['persist.sys.oplus.wifi.atpc.backup_txpower']),
    ('extreme refresh rate: 120/165 Hz choice in Settings > Display > Screen refresh rate', {
        'persist.performance.rapid.refresh_rate.level': '165',
        'persist.performance.rapid.refresh_rate.is_perf_mode': 'true'}),
]
# SoC/board parity: the donor is SM8850 (canoe, OnePlus 15), the Nord 6 is SM8735 (sun).
# These my_product files are tuned for the board, chip or motor; the Nord 6 ones come from base.
SOC_BASE_FILES = [
    'etc/hw/usb_params.json',                               # USB PHY signal tuning (board traces)
    'etc/report_rate_config.xml',                           # touch report rate per scene (touch IC)
    'etc/vibrator/effect_waveform.xml',                     # haptic effects -> base AW8697 waveforms in odm/firmware
    'etc/vibrator/effect_waveform_override.xml',
    'etc/extension/sys_custom_osense_scene_event_config.xml',  # camera HAL thread boost ids of the base camx HAL
    'etc/extension/sys_game_manager_config.json',          # donor: SM8850 CPU/GPU freq table (adp), infiniti frame-quality specs, MEMC
    'etc/extension/sys_graphic_enhancement_config.json',   # donor: SM8850 super-resolution/frame lists, Adreno GPU profiles
    'etc/fusionlight_profile',                              # camera light-sensor profiles
]
SOC_DONOR_REMOVE = [
    'etc/extension/sys_graphics_game_gpu_control_panel.json',  # Adreno 840 private game profiles
    'etc/wifiedccaconfig.xml',                              # EDCCA thresholds of the donor Wi-Fi chip
]
SOC_DONOR_REMOVE_GLOB = ['etc/sysconfig/google_aicore_SM*.xml']  # AICore feature for the donor NPU; base has none
SOC_MODEL_RE = re.compile(r'_sm\d{4}', re.I)                # aisubsystem models are built per SoC
SOC_PROPS_DELETE = [
    'ro.oplus.fusionlight',                                 # donor camera light sensor
    'ro.oplus.audio.effect.speaker_geq',                    # donor speaker EQ
    'persist.sys.camera.private.log.enable',                # donor camera debug logging
    'persist.vendor.diag.manage_adpl',                      # donor modem diag
]
SOC_PROPS_DELETE_PREFIX = ['ro.oplus.haptic.']              # donor motor LRA levels (120-140 Hz; Nord 6 ~170 Hz)
SOC_PROPS_BASE_PREFIX = ['persist.bluetooth.', 'persist.sys.bluetooth.', 'persist.sys.oplus.bt.',  # BT chip/antenna/SAR
                         'persist.sys.bt.']                 # C.80 added persist.sys.bt.leacoexist (LE Audio + Classic
                                                            #   dual mode of the donor BT chip); base has only netless_over_blr
SOC_PROPS_FROM_BASE = [
    'ro.oplus.audio.4ch.aec.record', 'ro.oplus.audio.new_thermal_safety_mode', 'ro.oplus.audio.product.para',
    'ro.audio.spatializer_headtracking_support_hogp', 'vendor.audio.ble.enabled', 'ro.oplus.camera.livephoto.support',
]
SYSTEM_EXT_PROPS = {                                        # midasd/ostatsd/ostats_pullerd off for good
    'persist.sys.midasd.enable': '0', 'persist.sys.ostatsd.enable': '0',
    'persist.sys.ostats_pullerd.enable': '0', 'persist.sys.midas_ostats.restriction.force': '1',
}
# Bloat removed from the port: background telemetry/push/updaters, ads, third-party stubs, the install-time
# "app safety" scanner, store/browser/preinstalls nobody needs. OnePlus AI apps (AIUnit, aiassistant, AIMemory,
# AIWriter, AISeal, AONService, AICallAssistant, Gleaner, Metis, SandboxRuntime) are deliberately kept.
# Verified on device by hiding these dirs and restarting zygote: no crashes, installs go straight to the
# stock Android installer, only Play Store stays as package verifier.
DEBLOAT = {
    'my_stock': [
        'priv-app/StdSP',                    # com.oplus.stdsp: install-time scan screen + required verifier, ad SDK
        'priv-app/SecurityGuard',            # com.oplus.securityguard: cloud virus-scan engine
        'priv-app/DCS',                      # com.oplus.statistics.rom: usage statistics upload
        'app/RomUpdate',                     # com.oplus.romupdate: RUS server config pushes (can override port configs)
        'priv-app/Cota',                     # com.oplus.cota: carrier OTA customisation
        'app/MCS',                           # com.heytap.mcs: HeyTap push connection
        # 'app/Instant' kept: com.nearme.instant.platform (InstantWeb Service Framework) backs lock-screen widgets
        'priv-app/KeKeMarket',               # com.heytap.market: HeyTap app market
        'app/Browser',                       # com.heytap.browser: HeyTap browser (ads)
        'app/SoftsimRedteaRoaming',          # com.redteamobile.roaming: soft-SIM roaming service
        'priv-app/OPMemberShip',             # com.oneplus.membership: Red Cable Club
        'priv-app/DeviceIntegrationService', # com.microsoft.deviceintegrationservice: Link to Windows service
        'priv-app/LinktoWindows',            # com.microsoft.appmanager: Link to Windows
        'del-app/INOnePlusStore',            # removable preinstalls: OnePlus Store, Community, lock-screen
        'del-app/OPForum',                   #   magazine (downloads wallpapers), Tips
        'del-app/Pictorial',
        'del-app/Tips',
    ],
    'my_product': [
        'priv-app/Facebook-services',        # Facebook preload stubs (background jobs)
        'priv-app/Facebook-installer',
        'app/Facebook-appmanager',
        'del-app-pre/Facebook',
        'etc/permissions/facebook_privapp_permissions.xml',
        'etc/sysconfig/facebook_sysconfig.xml',
        'etc/default-permissions/facebook_default_permissions.xml',
        'app/Meet',                          # Google Meet
        'priv-app/FamilyLinkParentalControls',
        'app/YouTube',                       # YouTube + Google Photos: not preinstalled so they install as normal
        'app/Photos',                        #   user apps (Play Store / ReVanced-module stock apk); a newer system
                                             #   copy blocks the module's stock install (downgrade) and mount
    ],
    'system_ext': [
        'app/SystemAppUpdateService',        # com.oplus.sau: system-app updates for the donor model
        'app/SAUHelper',
    ],
    'system': [
        'system/app/Traceur',                # com.android.traceur: OplusQualityProtect/Olc/oplus-services start
                                             #   "health" traces through it (oplus TRACEUR_START_TRACING), which
                                             #   ran 24/7 (19 data sources, 124 MB ring buffer, ~1 h traced_probes
                                             #   CPU) and dumped ~35 MB health_trace files several times a day
        'system/app/CrossDeviceServiceBroker',  # com.microsoftsdk.crossdeviceservicebroker: Link to Windows backend
    ],
}
# Optional "minimal Google" variant (flash_all.bat asks): my_product_lite.img = my_product.img (DEBLOAT above
# already applied) minus every Google app except what Google app + Play Store + Android Auto need, plus what has
# no replacement on this ROM (Gboard = only keyboard, Messages = only SMS app, WebView + Trichrome). Kept:
# GmsCore, GSF, Phonesky, GoogleVelvet_CTS + hotword, SpeechServices (voice/TTS for Assistant + Android Auto),
# AndroidAutoStub, setup (SetupWizard, PartnerSetup, Restore), PackageInstaller, ExtShared, ConfigUpdater,
# DeveloperVerifier, EmergencyInfo, SearchSelector (setup search-engine choice screen, idle afterwards). No OnePlus app depends on the removed ones (manifest scan of my_product,
# my_stock, system, system_ext). ARCore lives in my_stock: flash_all.bat removes it for user 0 over adb.
GOOGLE_MINIMAL_ADB = [('my_stock', 'app/ARCore')]   # not in my_product: removed after boot (pm uninstall --user 0)
GOOGLE_MINIMAL = {
    'my_product': [
        'app/CalendarGoogle', 'app/Chrome64', 'app/GPay3', 'app/Gmail2', 'app/GoogleContacts',
        'app/GoogleGemini', 'app/GoogleLens', 'app/GoogleLocationHistory', 'app/GoogleWallet', 'app/Maps',
        'app/SwitchAccess', 'app/talkback', 'app/clouddpc',
        'priv-app/AICore', 'priv-app/AndroidSystemIntelligence_Features', 'priv-app/PrivateComputeServices',
        'priv-app/CrossDeviceServicesStub', 'priv-app/GoogleDialer', 'priv-app/GoogleFiles', 'priv-app/GoogleOdad',
        'priv-app/PersonalSafety', 'priv-app/PlayAutoInstallConfig_OnePlus', 'priv-app/Wellbeing',
        'non_overlay/priv-app/GoogleFeedback', 'non_overlay/app/GooglePrintRecommendationService',
        'del-app-pre/Drive_del', 'del-app-pre/GoogleFindMyDevice', 'del-app-pre/GoogleFitbit',
        'del-app-pre/GoogleHome', 'del-app-pre/GoogleOne', 'del-app-pre/Videos_del', 'del-app-pre/YTMusic_del',
    ],
}
SECCOMP_LSEEK = ['qsap_qapeservice', 'qesdksec', 'syshealthmon']  # SIGSYS loop with A17 libs
VERIFIED_BASE = 'CPH2793export_11_16.0.5.1300(EX01)_2026101221100203'   # was 16.0.5.702 (2026-04) until 2026-11-01


# ---------------------------------------------------------------- helpers

class Log:
    def __init__(self):
        self.lines, self.failed = [], []

    def __call__(self, msg):
        print('  ' + msg, flush=True)
        self.lines.append(msg)

    def step(self, msg):
        print('\n== ' + msg, flush=True)
        self.lines.append('')
        self.lines.append('== ' + msg)


LOG = Log()


def run(cmd, **kw):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kw)
    if r.returncode:
        raise RuntimeError('command failed (%d): %s\n%s' % (r.returncode, ' '.join(cmd), r.stdout[-3000:]))
    return r.stdout


def esc(path):
    return re.sub(r'([.^$*+?()\[\]{}|\\])', r'\\\1', path)


def unesc(path):
    return re.sub(r'\\(.)', r'\1', path)


def read_props(path):
    d = {}
    for line in open(path, errors='replace'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            d.setdefault(k, v)
    return d


def last_prop(path, key):
    v = None
    for line in open(path, errors='replace'):
        if line.startswith(key + '='):
            v = line.rstrip('\n').split('=', 1)[1]
    return v


def edit_props(path, delete=(), set_=None, append=None):
    """Delete keys, replace values in place (append if missing), add commented blocks."""
    set_ = dict(set_ or {})
    out, done = [], set()
    for line in open(path, errors='replace').read().split('\n'):
        k = line.split('=', 1)[0] if '=' in line and not line.startswith('#') else None
        if k is not None and k.strip() in delete:
            continue
        if k in set_:
            if k in done:
                continue
            line = '%s=%s' % (k, set_[k])
            done.add(k)
        out.append(line)
    while out and out[-1] == '':
        out.pop()
    missing = [k for k in set_ if k not in done]
    if missing:
        out += [''] + ['%s=%s' % (k, set_[k]) for k in missing]
    for title, kv in append or []:
        out += ['', '# --- %s ---' % title] + ['%s=%s' % kv_ for kv_ in kv.items()]
    open(path, 'w').write('\n'.join(out) + '\n')


class Part:
    """An extracted partition tree plus its fs_config / file_contexts."""

    def __init__(self, name, outdir):
        self.name, self.outdir = name, outdir
        self.root = os.path.join(outdir, name)
        cfg = os.path.join(outdir, 'config', name)
        self.fs = {}
        for line in open(cfg + '_fs_config'):
            if line.strip():
                self.fs[line.split(' ', 1)[0]] = line.rstrip('\n')
        self.ctx = {}
        for line in open(cfg + '_file_contexts'):
            if line.strip():
                p, c = line.rstrip('\n').rsplit(' ', 1)
                self.ctx[unesc(p)] = c
        opts = open(cfg + '_fs_options').read()
        self.uuid = re.search(r'-U ([0-9a-f-]+)', opts).group(1)

    def path(self, rel):
        return os.path.join(self.root, rel)

    def exists(self, rel):
        return os.path.lexists(self.path(rel))

    def key(self, rel):
        return '%s/%s' % (self.name, rel) if rel else self.name + '/'

    def remove(self, rel, why=None):
        p = self.path(rel)
        if not os.path.lexists(p):
            return False
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p)
        else:
            os.remove(p)
        k = self.key(rel)
        for d in (self.fs, self.ctx):
            pref = k if d is self.fs else '/' + k
            for x in [x for x in d if x == pref or x.startswith(pref + '/')]:
                del d[x]
        if why:
            LOG('removed %s/%s  (%s)' % (self.name, rel, why))
        return True

    def _meta_from(self, src, rel):
        k = self.key(rel)
        sk = src.key(rel)
        line = src.fs.get(sk)
        if line:
            self.fs[k] = k + line[len(sk):]
        else:
            isdir = os.path.isdir(self.path(rel))
            self.fs[k] = '%s 0 0 %s' % (k, '0755' if isdir else '0644')
        c = src.ctx.get('/' + sk)
        if c is None:
            c = self.ctx.get('/' + self.key(os.path.dirname(rel)).rstrip('/'), 'u:object_r:system_file:s0')
        self.ctx['/' + k] = c

    def add_from(self, src, rel, why=None):
        """Copy file/dir `rel` (recursively) from another Part, metadata included."""
        s, d = src.path(rel), self.path(rel)
        if not os.path.lexists(s):
            raise RuntimeError('%s/%s missing in source' % (src.name, rel))
        if os.path.lexists(d):
            self.remove(rel)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        parent = os.path.dirname(rel)
        while parent and self.key(parent) not in self.fs:
            self._meta_from(src, parent)
            parent = os.path.dirname(parent)
        if os.path.isdir(s) and not os.path.islink(s):
            shutil.copytree(s, d, symlinks=True)
            self._meta_from(src, rel)
            for dp, dns, fns in os.walk(d):
                for n in dns + fns:
                    self._meta_from(src, os.path.relpath(os.path.join(dp, n), self.root))
        else:
            shutil.copy2(s, d, follow_symlinks=False)
            self._meta_from(src, rel)
        if why:
            LOG('%s/%s <- %s  (%s)' % (self.name, rel, src.label, why))

    def add_new(self, rel, data, like):
        """Write a new file `rel`; owner, mode and SELinux label are copied from the existing file `like`."""
        if not self.exists(like):
            raise RuntimeError('%s/%s missing (metadata template for %s)' % (self.name, like, rel))
        with open(self.path(rel), 'w') as f:
            f.write(data)
        lk, k = self.key(like), self.key(rel)
        self.fs[k] = k + self.fs[lk][len(lk):]
        self.ctx['/' + k] = self.ctx['/' + lk]

    def write_config(self):
        cfg = os.path.join(self.outdir, 'config', self.name)
        with open(cfg + '_fs_config', 'w') as f:
            f.write('\n'.join(self.fs.values()) + '\n')
        with open(cfg + '_file_contexts', 'w') as f:
            f.write('\n'.join('%s %s' % (esc(p), c) for p, c in self.ctx.items()) + '\n')
        return cfg + '_fs_config', cfg + '_file_contexts'


def extract(tools, img, outdir, path=None):
    os.makedirs(outdir, exist_ok=True)
    cmd = [tools['extract'], '-i', img, '-o', outdir, '-s', '-f']
    cmd += ['-X', path] if path else ['-x']
    run(cmd)


def ref_part(tools, img, outdir, name, paths, label):
    """Extract only some paths of an image (the rest of the tree stays absent)."""
    for p in paths:
        extract(tools, img, outdir, p)
    part = Part(name, outdir)
    part.label = label
    return part


# ---------------------------------------------------------------- recipe steps

def perfboost_drop_l3(s):
    """SoC 655 = perf target "tuna"; its boosts request resource [0xD,0x20] which the HAL marks
    Supported="no", so every scroll logs errors. Drop that opcode/value pair from tuna configs only."""
    count = 0

    def fix(m):
        nonlocal count
        block = m.group(0)
        if 'Target="tuna"' not in block:
            return block
        new, k = re.subn(r',\s*0x43480000,\s*0x[0-9A-Fa-f]+', '', block)
        count += k
        return new
    s = re.sub(r'<Config\b.*?/>', fix, s, flags=re.S)
    if not count:
        raise RuntimeError('perfboostsconfig.xml: no tuna 0x43480000 entries found')
    return s, count


def do_vendor(v, dprops):
    LOG.step('vendor  (base tree)')
    f = v.path('etc/fstab.qcom')
    lines = open(f).read().split('\n')
    new = [re.sub(r',avb(=[\w.]+)?', '', re.sub(r'avb=vbmeta\w*,', '', l)) for l in lines]
    open(f, 'w').write('\n'.join(new))
    LOG('fstab.qcom: avb flags stripped on %d lines (images are not signed)' % sum(a != b for a, b in zip(lines, new)))
    for name in SECCOMP_LSEEK:
        f = v.path('etc/seccomp_policy/%s.policy' % name)
        s = open(f).read()
        if re.search(r'^lseek\s*:', s, re.M):
            continue
        s2 = re.sub(r'^(read: *1\n)', r'\1lseek: 1\n', s, count=1, flags=re.M)
        if s2 == s:
            s2 = s.rstrip('\n') + '\nlseek: 1\n'
        open(f, 'w').write(s2)
        LOG('seccomp %s: + lseek (service died with SIGSYS every 5 s)' % name)
    f = v.path('etc/perf/perfboostsconfig.xml')
    s, n = perfboost_drop_l3(open(f).read())
    open(f, 'w').write(s)
    LOG('perfboostsconfig.xml: removed [13,32] (0x43480000, L3 memlat min freq) from %d tuna boosts '
        '(targetresourceconfigs marks it unsupported -> "Failed to reset [13,32]" on every scroll)' % n)
    f = v.path('etc/selinux/vendor_property_contexts')
    keep, dropped = [], []
    for line in open(f).read().split('\n'):
        t = line.split()
        if t and not line.startswith('#') and t[0] in dprops:
            dropped.append(t[0])
            continue
        keep.append(line)
    open(f, 'w').write('\n'.join(keep))
    LOG('vendor_property_contexts: dropped %d entries already defined by donor system parts: %s'
        % (len(dropped), ' '.join(dropped)))


def do_odm(o, donor_odm):
    LOG.step('odm  (base tree)')
    o.add_from(donor_odm, 'lib64/libradioapis.so', 'radio API lib matching ColorOS 17 telephony')
    # Widevine L1 Provisioning 4.0 fails in the TEE on this phone (status 323, same TEE key path as the
    # broken KeyMint CSR), so Netflix stops at error 15001 (-93). Provisioning 3.0 (factory keybox) works.
    if not o.exists('build.prop') or 'vendor.wv.oemcrypto.debug.enable_prov40=' not in open(o.path('build.prop')).read():
        raise RuntimeError('odm build.prop has no vendor.wv.oemcrypto.debug.enable_prov40 line')
    edit_props(o.path('build.prop'), set_={'vendor.wv.oemcrypto.debug.enable_prov40': 'false'})
    LOG('odm build.prop: Widevine provisioning 4.0 off (Netflix 15001 fix)')
    a = os.path.join(KIT, 'assets', 'odm')
    for dp, _, fns in os.walk(a):
        for n in fns:
            rel = os.path.relpath(os.path.join(dp, n), a)
            if not o.exists(rel):
                raise RuntimeError('odm asset target %s missing in base odm' % rel)
            shutil.copy2(os.path.join(dp, n), o.path(rel))
            LOG('odm/%s <- kit asset (colour calibration incl. 24811_* render intents)' % rel)


def do_system(s, tools, work, keep_going):
    LOG.step('system  (donor tree)')
    jar = s.path('system/framework/oplus-services.jar')
    guard(lambda: patches.patch_services_jar(jar, tools, work, LOG), 'oplus-services.jar patches', keep_going)
    for f in glob.glob(s.path('system/framework/oat/*/oplus-services.*')):
        s.remove(os.path.relpath(f, s.root))
    LOG('removed stale oplus-services odex/vdex/art (jar changed; ART recompiles it)')
    jar = s.path('system/framework/services.jar')
    guard(lambda: misc.patch_services(jar, tools, work, LOG, patches.smali_patch_jar),
          'services.jar patches (Miscellaneous page)', keep_going)
    for f in glob.glob(s.path('system/framework/oat/*/services.*')):
        s.remove(os.path.relpath(f, s.root))
    LOG('removed stale services odex/vdex/art (jar changed; ART recompiles it)')
    guard(lambda: misc.patch_framework(s.path('system/framework/framework.jar'), tools, work, LOG,
                                       patches.rebuild_jar), 'framework.jar patches (Miscellaneous page)', keep_going)
    guard(lambda: misc.add_app_prop_contexts(s.path('system/etc/selinux/plat_property_contexts'), LOG),
          'property contexts for Miscellaneous props', keep_going)
    guard(lambda: misc.add_photos_sysconfig(s, LOG), 'Google Photos unlimited backup sysconfig', keep_going)
    edit_props(s.path('system/build.prop'), set_={misc.PHOTOS_PROP: '1'})
    LOG('system build.prop: %s=1 (Photos unlimited backup on by default; persist value overrides)' % misc.PHOTOS_PROP)
    debloat(s)


def do_system_ext(se, base_se, tools, args):
    LOG.step('system_ext  (donor tree)')
    se.remove('app/OTA', 'no OTA updates for a port')
    debloat(se)
    se.add_from(base_se, 'etc/display_brightness_config_common.xml', 'brightness parity with base')
    edit_props(se.path('etc/build.prop'), set_=SYSTEM_EXT_PROPS)
    LOG('build.prop: midasd/ostatsd/ostats_pullerd disabled (restriction.force=1)')
    apk = se.path('priv-app/Settings/Settings.apk')
    guard(lambda: patches.patch_settings(apk, args.banner_text, LOG), 'Settings.apk patches', args.keep_going)
    guard(lambda: misc.patch_settings(apk, tools, args.work, LOG), 'Settings > Miscellaneous page', args.keep_going)
    guard(lambda: misc.patch_anim_scale(apk, tools, args.work, LOG), 'Settings animation-scale box', args.keep_going)
    guard(lambda: misc.patch_settingsprovider(se.path('priv-app/SettingsProvider/SettingsProvider.apk'), tools,
                                              args.work, LOG), 'SettingsProvider (hide developer options)',
          args.keep_going)
    apk = se.path('priv-app/SystemUI/SystemUI.apk')
    guard(lambda: patches.patch_systemui(apk, LOG), 'SystemUI.apk patches', args.keep_going)
    guard(lambda: swap_launcher(se), 'OplusLauncher (Zuyqa 17.3.9 + Google search button)', args.keep_going)
    for app in ('Settings', 'SettingsProvider', 'SystemUI', 'OplusLauncher'):
        for f in glob.glob(se.path('priv-app/%s/oat/*/*' % app)):
            se.remove(os.path.relpath(f, se.root))
    se.remove('priv-app/SystemUI/oat')
    se.remove('priv-app/OplusLauncher/oat')
    LOG('removed stale Settings/SettingsProvider/SystemUI/OplusLauncher oat (apks changed)')
    done = []
    guard(lambda: done.extend(subsysradio.patch_subsys_jars(
        se.path('framework'), base_se.path('framework/vendor-subsystem-service.jar'), tools, args.work, LOG,
        patches.rebuild_jar)), 'subsystem jars (subsys_radio AIDL remap)', args.keep_going)
    for name in done:
        for f in glob.glob(se.path('framework/oat/*/%s.*' % name)):
            se.remove(os.path.relpath(f, se.root))
    if done:
        LOG('removed stale odex/vdex of %s' % ', '.join(done))


# /product/overlay merge. ColorOS init (libfs_mgr) merges the my_* overlay dirs plus the region's
# my_product/cust/<region>/overlay into /product/overlay. From C.80 on, libfs_mgr builds those lowerdirs
# from /my_<part>/overlay, because the OnePlus 15 vendor fstab mounts my_* at /my_*. The Nord 6 (base)
# vendor mounts them at /mnt/vendor/my_*, so every lowerdir is dropped as missing and the mount fails
# ("at least 2 lowerdir are needed"). Then no my_product/my_stock overlay is installed (the Nord 6
# display overlay with the centre punch hole, SystemUI/GMS config...), and the Oplus cust partition scan
# hands zygote /my_product/cust/<region>/overlay/*.apk, a path outside its fd allowlist: zygote aborts
# with "Not allowlisted" when forking system_server (bootloop). This rc redoes the C.75 mount; the second
# line stacks the region overlays on top and simply fails if that region has no overlay dir.
PRODUCT_OVERLAY_RC = 'etc/init/port_product_overlay.rc'
PRODUCT_OVERLAY_RC_DATA = """# port_kit: /product/overlay merge with the Nord 6 /mnt/vendor/my_* layout (see build_port.py)
on post-fs
    mount overlay overlay-overlay /product/overlay ro lowerdir=/mnt/vendor/my_region/overlay:/mnt/vendor/my_preload/overlay:/mnt/vendor/my_product/overlay:/mnt/vendor/my_heytap/overlay:/mnt/vendor/my_stock/overlay:/mnt/vendor/my_engineering/overlay:/product/overlay,userxattr
    mount overlay overlay-overlay /product/overlay ro lowerdir=/mnt/vendor/my_product/cust/${ro.oplus.pipeline.region}/overlay:/product/overlay,userxattr
"""


def product_overlay_fix(se):
    """Add PRODUCT_OVERLAY_RC (see above). Harmless if init's own merge works: identical layers on top."""
    like = 'etc/init/' + sorted(f for f in os.listdir(se.path('etc/init')) if f.endswith('.rc'))[0]
    se.add_new(PRODUCT_OVERLAY_RC, PRODUCT_OVERLAY_RC_DATA, like)
    LOG('system_ext/%s added: /product/overlay merged from /mnt/vendor/my_* + cust/<region> (donor libfs_mgr '
        'expects /my_*; without it no my_* overlay loads and zygote aborts on cust overlays)' % PRODUCT_OVERLAY_RC)


LAUNCHER_APK = os.path.join(KIT, 'assets', 'launcher', 'OplusLauncher.apk')
LAUNCHER_MD5 = 'b0dabd90747c7da2060d5bb58498e67b'


def swap_launcher(se):
    """The user's launcher (assets/launcher/README.txt) replaces the donor OplusLauncher."""
    if hashlib.md5(open(LAUNCHER_APK, 'rb').read()).hexdigest() != LAUNCHER_MD5:
        raise RuntimeError('assets/launcher/OplusLauncher.apk md5 mismatch')
    dst = se.path('priv-app/OplusLauncher/OplusLauncher.apk')
    if not os.path.exists(dst):
        raise RuntimeError('donor system_ext has no priv-app/OplusLauncher/OplusLauncher.apk')
    shutil.copyfile(LAUNCHER_APK, dst)
    os.chmod(dst, 0o644)
    for prof in glob.glob(se.path('priv-app/OplusLauncher/*.prof')):
        se.remove(os.path.relpath(prof, se.root))
    LOG('OplusLauncher: replaced with Zuyqa 17.3.9 (Google search button, no mod credits); donor .prof removed')


# Melody gets a versionCode above any Play Store release: Play updates it (it did on the device), and the
# update in /data/app would replace the patched system copy. A dirty flash drops an installed update.
MELODY_VERSION_CODE = 1999999999
# donor-only my_stock props the Nord 6 (base) does not have
MY_STOCK_PROPS_DELETE = [
    'ro.oplus.radio.global_regionlock.dynamic',  # C.80: SIM region lock follows a cloud policy synced for a device
                                                 #   identity (subsys-channel-lock-plugin RegionLockController) instead
                                                 #   of the local xml policy; base and the C.75 port use the local one
]


def do_my_stock(ms, base_ms, keep_going):
    LOG.step('my_stock  (donor tree)')
    n = 0
    for sub in ('media/audio/ringtones', 'media/audio/notifications'):
        if not os.path.isdir(base_ms.path(sub)):
            continue
        for f in sorted(os.listdir(base_ms.path(sub))):
            rel = sub + '/' + f
            if not ms.exists(rel):
                ms.add_from(base_ms, rel)
                n += 1
    LOG('added %d OnePlus ringtones/notification sounds from base' % n)
    have = [k for k in MY_STOCK_PROPS_DELETE if k in read_props(ms.path('build.prop'))]
    if have:
        edit_props(ms.path('build.prop'), delete=set(have))
        LOG('build.prop: donor-only props removed (base parity): ' + ' '.join(have))
    apk = ms.path('app/Melody/Melody.apk')
    if os.path.exists(apk):
        guard(lambda: patches.patch_melody(apk, LOG, MELODY_VERSION_CODE), 'Melody.apk patches', keep_going)
        ms.remove('app/Melody/oat')
    apk = ms.path('app/Aod/Aod.apk')
    if os.path.exists(apk):
        guard(lambda: patches.patch_aod(apk, LOG), 'Aod.apk patches', keep_going)
        ms.remove('app/Aod/oat')
    debloat(ms)


def debloat(part):
    n = sum(1 for rel in DEBLOAT.get(part.name, []) if part.remove(rel))
    LOG('debloat: removed %d of %d bloat entries' % (n, len(DEBLOAT.get(part.name, []))))


def xml_edit(path, fn, what):
    s = open(path, encoding='utf8').read()
    s2 = fn(s)
    if s2 != s:
        open(path, 'w', encoding='utf8').write(s2)
        LOG(what)
    else:
        LOG('(no change) ' + what)


def do_my_product(mp, base_mp, donor_prj):
    LOG.step('my_product  (donor tree)')
    for rel in DONOR_MY_PRODUCT_REMOVE:
        mp.remove(rel, 'not supported on Nord 6')
    for rel in BASE_MY_PRODUCT_FILES:
        mp.add_from(base_mp, rel)
    LOG('%d base permission/feature/overlay files copied (Nord 6 hardware description)' % len(BASE_MY_PRODUCT_FILES))
    for f in glob.glob(mp.path('priv-app/HotwordEnrollment*')) + glob.glob(mp.path('priv-app/oat/*/HotwordEnrollment*')):
        mp.remove(os.path.relpath(f, mp.root))
    for rel in HOTWORD_APKS:
        mp.add_from(base_mp, rel)
    LOG('hotword enrollment apks = base (donor DSP model crashed the ADSP: charging/Android Auto loop)')
    for ov in PROJECT_OVERLAYS:
        for f in glob.glob(mp.path('overlay/%s.*.apk' % ov)):
            mp.remove(os.path.relpath(f, mp.root), 'donor project overlay')
        for f in glob.glob(base_mp.path('overlay/%s.*.apk' % ov)):
            mp.add_from(base_mp, os.path.relpath(f, base_mp.root), 'Nord 6 project overlay')
    ve = 'vendor/etc'
    for dp, dns, fns in os.walk(mp.path(ve), topdown=False):
        for n in fns:
            rel = os.path.relpath(os.path.join(dp, n), mp.root)
            if PANEL_FILE_RE.search(rel):
                mp.remove(rel)
    if os.path.isdir(mp.path(ve + '/EyeProtect')) and not os.listdir(mp.path(ve + '/EyeProtect')):
        mp.remove(ve + '/EyeProtect')
    for dp, dns, fns in os.walk(base_mp.path(ve)):
        for n in fns:
            mp.add_from(base_mp, os.path.relpath(os.path.join(dp, n), base_mp.root))
    LOG('my_product/vendor/etc display/panel configs = base (donor panel files removed)')

    # build.prop
    bp = read_props(base_mp.path('build.prop'))
    gone = [k for k in MY_PRODUCT_PROPS_DELETE if k not in read_props(mp.path('build.prop'))]
    if gone:
        LOG('(not in this donor, nothing to remove) ' + ' '.join(gone))
    blocks = []
    for title, keys in MY_PRODUCT_PROPS_APPEND:
        kv = keys if isinstance(keys, dict) else {k: bp[k] for k in keys if k in bp}
        blocks.append((title, kv))
    edit_props(mp.path('build.prop'), delete=set(MY_PRODUCT_PROPS_DELETE) | set(k for _, kv in blocks for k in kv),
               set_={k: bp[k] for k in MY_PRODUCT_PROPS_FROM_BASE if k in bp}, append=blocks)
    LOG('build.prop: donor display/unirender props removed, Nord 6 panel values and 165 Hz props set')

    ext = mp.path('etc/extension')
    xml_edit(os.path.join(ext, 'com.oplus.app-features.xml'), lambda s: _app_features(s),
             'app-features: wireless charging and all-day panoramic AOD removed, battery health added')
    xml_edit(os.path.join(ext, 'feature_com.android.battery.xml'),
             lambda s: re.sub(r'^(?:[ \t]*<!--[^\n]*wireless[^\n]*-->\n)?[ \t]*<app_feature name="oplus\.power\.onwirelesscharger\.support"\s*/>\n',
                              '', s, flags=re.M | re.I),
             'battery features: wireless charging removed')
    xml_edit(os.path.join(ext, 'com.oplus.oplus-feature.xml'), _oplus_features,
             'oplus-feature: display features aligned with base panel')
    f = mp.path('etc/permissions/oplus.product.display_system_features.xml')
    xml_edit(f, lambda s: re.sub(r'^([ \t]*)<feature name="oplus\.software\.display\.wcg_2\.0_support"\s*/>\n',
                                 r'\1<feature name="oppo.display.screen.gloablehbm.support"/>\n'
                                 r'\1<feature name="oppo.high.brightness.support"/>\n', s, flags=re.M),
             'display_system_features: WCG 2.0 off, global HBM on')
    xml_edit(mp.path('etc/sys_gamespace_gamesettings.xml'),
             lambda s: re.sub(r'[ \t]*<!-- hdr -->\r?\n[ \t]*<item name="game_hdr">.*?</item>\r?\n', '', s, flags=re.S),
             'game settings: game HDR page removed')
    xml_edit(mp.path('etc/sys_global_uni_render_list.xml'),
             lambda s: re.sub(r'(<func_switch value=")1(")', r'\g<1>0\2', s),
             'UniRender off (fixes banded screenshots of launcher/recents)')

    # radio / RF / carrier: Nord 6 modem, antennas and carrier tuning
    rf = sorted(n for n in os.listdir(base_mp.path('etc')) if BASE_MY_PRODUCT_RF_RE.match(n))
    for n in rf:
        mp.add_from(base_mp, 'etc/' + n)
    LOG('RF configs = base (cellular SAR, Wi-Fi SAR/regulation/product, RF events): ' + ' '.join(rf))
    n = 0
    for d in sorted(os.listdir(base_mp.path('etc/extension'))):
        if not d[:1].isdigit():
            continue
        if not mp.exists('etc/extension/' + d):
            mp.add_from(base_mp, 'etc/extension/' + d)
            n += 1
            continue
        rel = 'etc/extension/%s/carrierReady/oplus_carrier_config.xml' % d
        if os.path.exists(base_mp.path(rel)):
            mp.add_from(base_mp, rel)
            n += 1
    LOG('carrier configs: %d Nord 6 carrierReady configs/dirs from base (e.g. Airtel/Jio NR mode)' % n)
    for rel in ['etc/extension/com.oplus.oplus-feature.xml'] + sorted(
            os.path.relpath(f, base_mp.root) for f in glob.glob(base_mp.path('cust/*/etc/extension/com.oplus.oplus-feature.xml'))):
        if mp.exists(rel):
            radio_feature_parity(mp.path(rel), base_mp.path(rel), rel)

    # refresh rate: base configs + 165 Hz switches
    mp.add_from(base_mp, 'etc/refresh_rate_config.xml')
    xml_edit(mp.path('etc/refresh_rate_config.xml'),
             lambda s: s if 'extremeHighEnable' in s else re.sub(r'(<config [^>]*?)\s*/>', r'\1 extremeHighEnable="true" />', s, count=1),
             'refresh_rate_config = base + extremeHighEnable (165 Hz option)')
    xml_edit(mp.path('etc/refresh_rate_config.xml'), _gallery_rate,
             'refresh_rate_config: Photos follows the screen refresh setting (its photo page asked for 90 Hz)')
    mp.add_from(base_mp, 'etc/oplus_vrr_config.json')
    xml_edit(mp.path('etc/oplus_vrr_config.json'),
             lambda s: re.sub(r'"mvt_fps_strategy"\s*:\s*\[.*?\]', '"mvt_fps_strategy": []', s, count=1, flags=re.S),
             'oplus_vrr_config = base, MVT 165->55 Hz strategy off')
    soc_parity(mp, base_mp)
    debloat(mp)
    left = [n for n in os.listdir(mp.path('overlay')) if donor_prj and donor_prj in n]
    if left:
        LOG('note: donor-project overlays kept (framework network overlay has the same values as base): '
            + ' '.join(left))


GALLERY_ITEM_RE = r'(<item package="(?:com\.coloros\.gallery3d|com\.oneplus\.gallery)" [^>]*?)'


def _gallery_rate(s):
    """The photo page requests 90 Hz. appreqfirst lets that request win outright and, outside the 165 Hz
    mode, the window override still lowers the rate to it; drop the first and disable the second."""
    s = re.sub(GALLERY_ITEM_RE + r' appreqfirst="true"', r'\1', s)
    return re.sub(GALLERY_ITEM_RE + r'(?<! enableWinOverride="false")( />)', r'\1 enableWinOverride="false"\2', s)


def soc_parity(mp, base_mp):
    """Board/chip-tuned my_product files and props = Nord 6 (base); donor SM8850-only ones removed."""
    for rel in SOC_BASE_FILES:
        mp.add_from(base_mp, rel)
    LOG('SoC/board configs = base: ' + ' '.join(os.path.basename(r) for r in SOC_BASE_FILES))
    gone = [r for r in SOC_DONOR_REMOVE if mp.remove(r)]
    for pat in SOC_DONOR_REMOVE_GLOB:
        gone += [os.path.relpath(f, mp.root) for f in glob.glob(mp.path(pat)) if mp.remove(os.path.relpath(f, mp.root))]
    LOG('donor chip-specific files removed: ' + ' '.join(gone))
    ai, n = 'etc/aisubsystem', 0
    for dp, dns, fns in os.walk(mp.path(ai)):
        for f in fns:
            if SOC_MODEL_RE.search(f):
                n += mp.remove(os.path.relpath(os.path.join(dp, f), mp.root))
    add = [os.path.relpath(os.path.join(dp, f), base_mp.root)
           for dp, dns, fns in os.walk(base_mp.path(ai)) for f in fns if SOC_MODEL_RE.search(f)]
    for rel in add:
        mp.add_from(base_mp, rel)
    LOG('aisubsystem: %d donor per-SoC model files removed, %d Nord 6 ones from base' % (n, len(add)))
    bp, pp = read_props(base_mp.path('build.prop')), read_props(mp.path('build.prop'))
    strip = lambda d: {k.strip(): v for k, v in d.items()}
    bp, pp = strip(bp), strip(pp)
    base_keys = [k for k in bp if k.startswith(tuple(SOC_PROPS_BASE_PREFIX))] + \
                [k for k in SOC_PROPS_FROM_BASE if k in bp]
    delete = set(SOC_PROPS_DELETE) | {k for k in pp if k.startswith(tuple(SOC_PROPS_DELETE_PREFIX))} | \
             {k for k in pp if k.startswith(tuple(SOC_PROPS_BASE_PREFIX)) and k not in bp}
    edit_props(mp.path('build.prop'), delete=delete, set_={k: bp[k] for k in base_keys})
    LOG('build.prop: %d donor motor/camera/audio/BT props removed, %d Nord 6 BT/audio/camera props from base'
        % (len(delete & set(pp)), len(base_keys)))


def radio_feature_parity(path, base_path, rel):
    """radio/wlan feature lines = base: donor-only ones dropped, base-only ones added."""
    port = open(path, encoding='utf8').read().split('\n')
    base = open(base_path, encoding='utf8').read().split('\n')
    want = [m.groups() for m in map(RADIO_FEATURE_RE.match, base) if m]
    wset, have, out, dropped = set(want), set(), [], 0
    for line in port:
        m = RADIO_FEATURE_RE.match(line)
        if m and m.groups() not in wset:
            dropped += 1
            continue
        if m:
            have.add(m.groups())
        out.append(line)
    add = [d for d in want if d not in have]
    end = max(i for i, line in enumerate(out) if '</oplus-config>' in line)
    out[end:end] = ['\t<%s name="%s"/>' % d for d in add]
    open(path, 'w', encoding='utf8').write('\n'.join(out))
    LOG('%s: radio/wlan features = base (%d donor-only removed, %d added)' % (rel, dropped, len(add)))


# Nord 6 display driver (msm_drm OFP, oplus_onscreenfingerprint.c in OnePlus's sm8735 nord_6 source) has
# a full-screen AOD mode: panel stays out of LP1 command mode and the "aod layer exist, filter backlight"
# rule is skipped, so doze brightness reaches the panel. It's gated by the panel DT property
# oplus,ofp-longrui-aod-config (bit 0x4 full screen, 0x8 full screen all day), which base leaves out
# (reads 0x0). SystemUI reads the same value as panel feature 217 and sends the mode itself.
LONGRUI_AOD_CONFIG = 0xC


def patch_dtbo(path):
    import struct
    import dtbo

    def edit(fdt):
        n = 0
        for _, node in fdt.walk():
            name = dtbo.prop(node, 'qcom,mdss-dsi-panel-name') or b''
            # the Nord 6 panel (AA610 A0034, P 3 and P 7 sources); the same dtbo also carries other
            # devices' panels (e.g. AC274 A0026), which are left alone
            if b'A0034' in name and dtbo.prop(node, 'oplus,ofp-fp-type') is not None \
                    and dtbo.prop(node, 'oplus,ofp-longrui-aod-config') is None:
                dtbo.set_prop(node, 'oplus,ofp-longrui-aod-config', struct.pack('>I', LONGRUI_AOD_CONFIG),
                              after='oplus,ofp-fp-type')
                n += 1
        return n > 0
    n = dtbo.edit_dtbo(path, path, edit)
    if not n:
        raise RuntimeError('dtbo: no OFP video-mode panel node found')
    LOG('dtbo: full-screen + all-day AOD capability (longrui_aod_config 0x%x) added to panel nodes in %d overlays'
        % (LONGRUI_AOD_CONFIG, n))


def _app_features(s):
    s = re.sub(r'^[ \t]*<app_feature name="[^"]*wireless[^"]*"[^\n]*\n', '', s, flags=re.M | re.I)
    # base doesn't declare all-day panoramic either; it isn't needed: all-day panoramic AOD is gated by the
    # panel capability the port adds to dtbo (longrui_aod_config 0xC, see patch_dtbo). Kept as base.
    s = re.sub(r'^[ \t]*<app_feature name="com\.oplus\.systemui\.panoramic_aod_all_day\.enable"[^\n]*\n', '', s, flags=re.M)
    if 'os.charge.settings.batterysettings.batteryhealth' not in s:
        i = s.index('<app_feature')
        s = s[:i] + '<app_feature name="os.charge.settings.batterysettings.batteryhealth"/>\n\t' + s[i:]
    return s


ADD_OPLUS_FEATURES = ['oplus.software.display.eyeprotect_game_support', 'oplus.software.display.oha_support',
                      'oplus.software.display.mura_enhance_brightness_support',
                      'oplus.software.display.game_dark_eyeprotect_support', 'oplus.software.display.manual_hbm.support']


def _oplus_features(s):
    s = re.sub(r'^[ \t]*<oplus-feature name="oplus\.hardware\.display\.allbrightness_colorappearance"\s*/>\n', '', s, flags=re.M)
    have = set(re.findall(r'name="([^"]+)"', s))
    add = ''.join('\t<oplus-feature name="%s"/>\n' % f for f in ADD_OPLUS_FEATURES if f not in have)
    i = s.rindex('</oplus-config>')
    return s[:i] + add + s[i:]


def do_my_manifest(mm, base_manifest_prop):
    LOG.step('my_manifest  (donor tree)')
    f = mm.path('build.prop')
    d = read_props(f)
    b = read_props(base_manifest_prop)
    subs = [(d['ro.product.model'], b['ro.product.model']), (d['ro.product.device'], b['ro.product.device'])]
    dm, bm = last_prop(f, 'ro.vendor.oplus.market.name'), last_prop(base_manifest_prop, 'ro.vendor.oplus.market.name')
    out = []
    for line in open(f).read().split('\n'):
        k = line.split('=', 1)[0]
        if k == 'ro.vendor.build.ab_ota_partitions':
            continue
        if k == 'ro.product.ab_ota_partitions':
            line = k + '=' + b[k]
        elif '=' in line and not line.startswith('#') and 'my_manifest' not in k:
            v = line.split('=', 1)[1]
            if k == 'ro.vendor.oplus.market.name' and v == dm:
                v = bm
            for a, c in subs:
                v = v.replace(a, c)
            line = k + '=' + v
        out.append(line)
    open(f, 'w').write('\n'.join(out))
    LOG('identity: %s/%s -> %s/%s, market name %r -> %r, ab_ota_partitions = base'
        % (subs[0][0], subs[1][0], subs[0][1], subs[1][1], dm, bm))


def guard(fn, what, keep_going):
    try:
        fn()
    except (PatchError, RuntimeError, subprocess.CalledProcessError) as e:
        LOG('FAILED: %s: %s' % (what, e))
        LOG.failed.append(what)
        if not keep_going:
            raise


# ---------------------------------------------------------------- main

def find_tools(args):
    """Tools ship inside the kit (tools/); the old ../tools layout is a fallback."""
    def pick(name, legacy):
        for p in (os.path.join(KIT, 'tools', name), os.path.join(PORT, legacy, name)):
            if os.path.exists(p):
                return p
        return os.path.join(KIT, 'tools', name)
    t = {
        'extract': args.extract or pick('extract.erofs', 'tools'),
        'mkfs': args.mkfs or pick('mkfs.erofs', 'tools'),
        'payload': pick('payload-dumper-go', 'tools'),
        'baksmali': pick('baksmali-2.5.2.jar', 'tools_extra'),
        'smali': pick('smali-2.5.2.jar', 'tools_extra'),
        'smali3': os.path.join(KIT, 'tools', 'smali3'),     # framework.jar only (see tools/smali3/README.txt)
    }
    for k, p in t.items():
        if not os.path.exists(p):
            sys.exit('missing tool %s: %s' % (k, p))
        if not p.endswith('.jar') and not os.access(p, os.X_OK):
            os.chmod(p, 0o755)          # unzip tools may drop the exec bit
    if not shutil.which('java'):
        sys.exit('java not found (needed for smali/baksmali): sudo apt install openjdk-21-jre-headless')
    return t


def prepare_images(src, work, tools, label):
    """Images folder, payload.bin, OTA zip (payload.bin inside) or fastboot zip (*.img inside)
    -> folder of .img files."""
    if os.path.isdir(src):
        return src
    if not os.path.isfile(src):
        sys.exit('%s not found: %s' % (label, src))
    imgdir = os.path.join(work, label + '_images')
    os.makedirs(imgdir, exist_ok=True)
    payload = src
    if zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as z:
            names = z.namelist()
            pl = [n for n in names if os.path.basename(n) == 'payload.bin']
            imgs = [n for n in names if n.endswith('.img')]
            if pl:
                payload = os.path.join(work, label + '_payload.bin')
                print('extracting %s payload.bin from zip ...' % label, flush=True)
                with z.open(pl[0]) as i, open(payload, 'wb') as o:
                    shutil.copyfileobj(i, o, 1 << 24)
            elif imgs:
                print('extracting %d %s images from zip ...' % (len(imgs), label), flush=True)
                for n in imgs:
                    with z.open(n) as i, open(os.path.join(imgdir, os.path.basename(n)), 'wb') as o:
                        shutil.copyfileobj(i, o, 1 << 24)
                return imgdir
            else:
                sys.exit('%s zip has neither payload.bin nor *.img: %s' % (label, src))
    print('unpacking %s payload (all partitions) ...' % label, flush=True)
    run([tools['payload'], '-o', imgdir, payload])
    if payload != src:
        os.remove(payload)
    if not glob.glob(os.path.join(imgdir, '*.img')):
        sys.exit('no images came out of the %s payload' % label)
    return imgdir


def build_vbmeta(src, dst):
    a = bytearray(open(src, 'rb').read())
    if a[:4] != b'AVB0':
        raise RuntimeError(src + ' is not a vbmeta image')
    a[123] |= 3                     # flags: HASHTREE_DISABLED | VERIFICATION_DISABLED
    open(dst, 'wb').write(a)


def describe_input(src):
    """What prepare_images would do with BASE / DONOR, without unpacking anything."""
    if os.path.isdir(src):
        n = len(glob.glob(os.path.join(src, '*.img')))
        return n > 0, 'images folder, %d .img files' % n
    if not os.path.isfile(src):
        return False, 'not found'
    if zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as z:
            names = z.namelist()
        if any(os.path.basename(n) == 'payload.bin' for n in names):
            return True, 'OTA zip (payload.bin inside)'
        if any(n.endswith('.img') for n in names):
            return True, 'fastboot zip (*.img inside)'
        return False, 'zip without payload.bin or *.img'
    with open(src, 'rb') as f:
        if f.read(4) == b'CrAU':
            return True, 'payload.bin'
    return False, 'unknown file type'


def preflight(args):
    """--check: everything a build needs, without building. Exit code 0 = ready."""
    ok = True

    def say(good, what):
        nonlocal ok
        ok = ok and good
        print('  %-4s %s' % ('ok' if good else 'FAIL', what))

    print('port_kit preflight')
    say(sys.version_info >= (3, 8), 'python %d.%d (3.8+ needed)' % sys.version_info[:2])
    try:
        tools = find_tools(args)
        say(True, 'tools: ' + ', '.join(sorted(tools)))
        r = subprocess.run(['java', '-version'], capture_output=True, text=True)
        say(r.returncode == 0, 'java: ' + (r.stderr.splitlines() or ['?'])[0])
        r = subprocess.run([tools['mkfs'], '--version'], capture_output=True, text=True)
        say(r.returncode == 0, 'mkfs.erofs runs: ' + (r.stdout + r.stderr).strip().splitlines()[0])
    except SystemExit as e:
        say(False, str(e))
    for label in ('base', 'donor'):
        src = getattr(args, label)
        if not src:
            say(False, '--%s not given' % label)
            continue
        good, what = describe_input(src)
        say(good, '%s: %s (%s)' % (label, src, what))
    if os.path.exists(args.out) and os.listdir(args.out):
        say(False, 'output dir is not empty: ' + args.out)
    else:
        say(True, 'output dir: ' + args.out)
    probe = args.work
    while not os.path.exists(probe):
        probe = os.path.dirname(probe)
    free = shutil.disk_usage(probe).free / 2**30
    need = 80 if any(not os.path.isdir(getattr(args, x) or '') for x in ('base', 'donor')) else 40
    say(free >= need, 'free space for --work %s: %.0f GB (about %d GB needed)' % (args.work, free, need))
    print('ready to build' if ok else 'not ready: fix the FAIL lines above')
    return 0 if ok else 1


def main():
    if sys.version_info < (3, 8):
        sys.exit('python 3.8 or newer is needed')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    legacy = lambda *p: os.path.join(PORT, *p) if os.path.isdir(os.path.join(PORT, *p)) else None  # noqa: E731
    ap.add_argument('--base', default=legacy('base', 'images'),
                    help='stock Nord 6 OxygenOS 16: images dir, payload.bin, OTA zip or fastboot zip')
    ap.add_argument('--donor', default=legacy('donor', 'images'),
                    help='ColorOS 17 donor: images dir, payload.bin, OTA zip or fastboot zip')
    ap.add_argument('--out', default='out_port', help='output dir (flashable), default ./out_port')
    ap.add_argument('--work', default='_work', help='scratch dir, default ./_work (60-80 GB free needed with zips)')
    ap.add_argument('--banner-text', default='by @UnkNwn019', help='About-device banner pill text ("" = keep stock)')
    ap.add_argument('--level', type=int, default=12, help='lz4hc level for rebuilt images (default 12)')
    ap.add_argument('--no-google-minimal', action='store_true',
                    help='do not build my_product_lite.img (the flash-time minimal Google option)')
    ap.add_argument('--keep-going', action='store_true', help='report failed patches instead of stopping')
    ap.add_argument('--keep-work', action='store_true', help='keep extracted trees after the build')
    ap.add_argument('--check', action='store_true', help='only check tools, java, inputs and free space, then exit')
    ap.add_argument('--extract', help=argparse.SUPPRESS)
    ap.add_argument('--mkfs', help=argparse.SUPPRESS)
    args = ap.parse_args()
    args.out, args.work = os.path.abspath(args.out), os.path.abspath(args.work)
    if args.check:
        return preflight(args)
    if not args.base or not args.donor:
        ap.error('--base and --donor are required')
    t0 = time.time()
    tools = find_tools(args)

    if os.path.exists(args.out) and os.listdir(args.out):
        sys.exit('output dir %s is not empty; move it away or pass another --out' % args.out)
    shutil.rmtree(args.work, ignore_errors=True)
    os.makedirs(args.work)
    os.makedirs(args.out, exist_ok=True)
    base = prepare_images(args.base, args.work, tools, 'base')
    donor = prepare_images(args.donor, args.work, tools, 'donor')

    def img(src, name):
        return os.path.join(base if src == 'base' else donor, name + '.img')

    need = [img('base', p) for p in TAKE_FROM_BASE + VBMETA] + [img(s, p) for p, s in REBUILD.items()] \
        + [img('donor', p) for p in TAKE_FROM_DONOR[:6]]
    missing = [p for p in need if not os.path.exists(p)]
    if missing:
        sys.exit('missing images:\n  ' + '\n  '.join(missing))

    W = lambda *p: os.path.join(args.work, *p)  # noqa: E731
    LOG.step('reading donor / base identity')
    extract(tools, img('donor', 'my_manifest'), W('probe'), 'build.prop')
    extract(tools, img('base', 'my_manifest'), W('probe_base'), 'build.prop')
    dprop = read_props(W('probe', 'my_manifest', 'build.prop'))
    LOG('donor: %s  (%s)' % (dprop.get('ro.build.display.full_id'), dprop.get('ro.build.fingerprint')))
    bid = read_props(W('probe_base', 'my_manifest', 'build.prop')).get('ro.build.display.full_id')
    LOG('base : %s' % bid)
    if bid != VERIFIED_BASE:
        LOG('WARNING: base is not %s (the build this kit was verified on); check odm colour calibration' % VERIFIED_BASE)
    if dprop.get('ro.build.version.release') != '17':
        LOG('WARNING: donor Android release is %s, recipe was verified on 17' % dprop.get('ro.build.version.release'))

    LOG.step('copying unchanged images')
    for p in TAKE_FROM_BASE:
        shutil.copy2(img('base', p), args.out)
        LOG('%-15s <- base' % p)
    patch_dtbo(os.path.join(args.out, 'dtbo.img'))
    for p in TAKE_FROM_DONOR:
        if os.path.exists(img('donor', p)):
            shutil.copy2(img('donor', p), args.out)
            LOG('%-15s <- donor' % p)
    for p in VBMETA:
        build_vbmeta(img('base', p), os.path.join(args.out, p + '.img'))
        LOG('%-15s <- base, flags=3 (verity/verification off)' % p)

    LOG.step('extracting partitions to rebuild')
    parts = {}
    for p, src in REBUILD.items():
        print('  extract %s (%s)' % (p, src), flush=True)
        extract(tools, img(src, p), W('src'))
        parts[p] = Part(p, W('src'))
        parts[p].label = src

    # reference files from the other side
    base_mp = ref_part(tools, img('base', 'my_product'), W('ref_base'), 'my_product',
                       BASE_MY_PRODUCT_FILES + HOTWORD_APKS + ['overlay', 'vendor/etc', 'build.prop', 'etc', 'cust'], 'base')
    base_ms = ref_part(tools, img('base', 'my_stock'), W('ref_base'), 'my_stock',
                       ['media/audio/ringtones', 'media/audio/notifications'], 'base')
    base_se = ref_part(tools, img('base', 'system_ext'), W('ref_base'), 'system_ext',
                       ['etc/display_brightness_config_common.xml', 'framework/vendor-subsystem-service.jar'], 'base')
    donor_odm = ref_part(tools, img('donor', 'odm'), W('ref_donor'), 'odm', ['lib64/libradioapis.so'], 'donor')
    ref_part(tools, img('donor', 'product'), W('ref_donor'), 'product', ['etc/selinux'], 'donor')
    dprops = set()
    for f in glob.glob(W('src', 'system', 'system', 'etc', 'selinux', '*property_contexts')) \
            + glob.glob(W('src', 'system_ext', 'etc', 'selinux', '*property_contexts')) \
            + glob.glob(W('ref_donor', 'product', 'etc', 'selinux', '*property_contexts')):
        for line in open(f, errors='replace'):
            t = line.split()
            if t and not t[0].startswith('#'):
                dprops.add(t[0])
    donor_prj = read_props(parts['my_product'].path('build.prop')).get('ro.oplus.image.my_product.type', '')
    base_prj = read_props(base_mp.path('build.prop')).get('ro.oplus.image.my_product.type', '')
    LOG('project ids: donor %s, base %s' % (donor_prj, base_prj))

    do_vendor(parts["vendor"], dprops)
    do_odm(parts['odm'], donor_odm)
    do_system(parts['system'], tools, args.work, args.keep_going)
    do_system_ext(parts['system_ext'], base_se, tools, args)
    product_overlay_fix(parts['system_ext'])
    do_my_product(parts["my_product"], base_mp, donor_prj)
    do_my_stock(parts['my_stock'], base_ms, args.keep_going)
    do_my_manifest(parts['my_manifest'], W('probe_base', 'my_manifest', 'build.prop'))

    LOG.step('building images (erofs lz4hc,%d)' % args.level)
    # File times = build time, not 0: the port's fingerprints never change between builds, so on a dirty
    # flash PackageManager only re-parses an apk whose mtime is newer than its package_cache entry.
    stamp = str(int(t0))
    for p, part in parts.items():
        fsc, ctx = part.write_config()
        out = os.path.join(args.out, p + '.img')
        print('  mkfs %s ...' % p, flush=True)
        run([tools['mkfs'], '-zlz4hc,level=%d' % args.level, '-C', '16384', '-T', stamp, '-U', part.uuid,
             '--mount-point=/' + p, '--fs-config-file=' + fsc, '--file-contexts=' + ctx, out, part.root])
        LOG('%-12s %6.0f MB' % (p, os.path.getsize(out) / 2**20))
    if not args.no_google_minimal:
        # google_minimal_packages.txt: packages flash_all.bat uninstalls after boot when the minimal option is
        # picked - a system app whose system copy is gone keeps its /data update as a user app on a dirty flash.
        # del-app-pre apps are user-removable preinstalls, they are left alone once installed.
        pk = []
        for p, rel in [(p, r) for p, rels in GOOGLE_MINIMAL.items() for r in rels if not r.startswith('del-app')] \
                + GOOGLE_MINIMAL_ADB:
            pk += [manifest_package(a) for a in sorted(glob.glob(os.path.join(parts[p].path(rel), '*.apk')))]
        open(os.path.join(args.out, 'google_minimal_packages.txt'), 'w', newline='\r\n').write('\n'.join(pk) + '\n')
        LOG('google_minimal_packages.txt: %d packages for the after-boot clean-up' % len(pk))
        for p, rels in GOOGLE_MINIMAL.items():
            part = parts[p]
            n = sum(1 for rel in rels if part.remove(rel))
            fsc, ctx = part.write_config()
            out = os.path.join(args.out, p + '_lite.img')
            print('  mkfs %s (minimal Google) ...' % p, flush=True)
            run([tools['mkfs'], '-zlz4hc,level=%d' % args.level, '-C', '16384', '-T', stamp, '-U', part.uuid,
                 '--mount-point=/' + p, '--fs-config-file=' + fsc, '--file-contexts=' + ctx, out, part.root])
            LOG('%-12s %6.0f MB  (minimal Google: removed %d of %d Google apps, flash_all.bat option)'
                % (p + '_lite', os.path.getsize(out) / 2**20, n, len(rels)))

    for f in ('flash_all.bat', 'ksu_root.ps1'):
        shutil.copy2(os.path.join(KIT, 'assets', f), args.out)
    # twrp_nord6.img: flash_all.bat installs it from the bootloader and flashes the port from its FastbootD. The kit
    # keeps it gzipped (the raw image is 100 MiB, GitHub's per-file limit).
    with gzip.open(os.path.join(KIT, 'assets', 'twrp_nord6.img.gz'), 'rb') as src, \
            open(os.path.join(args.out, 'twrp_nord6.img'), 'wb') as dst:
        shutil.copyfileobj(src, dst, 1 << 20)
    logical = ['system', 'system_ext', 'product', 'vendor', 'odm', 'vendor_dlkm', 'system_dlkm', 'my_product',
               'my_stock', 'my_heytap', 'my_region', 'my_bigball', 'my_manifest', 'my_engineering', 'my_company',
               'my_preload', 'my_carrier']
    tot = sum(os.path.getsize(os.path.join(args.out, p + '.img')) for p in logical
              if os.path.exists(os.path.join(args.out, p + '.img')))
    btot = sum(os.path.getsize(img('base', p)) for p in logical if os.path.exists(img('base', p)))
    LOG.step('done in %.0f min' % ((time.time() - t0) / 60))
    LOG('logical partitions total %.2f GB (stock base %.2f GB) - flash_all.bat frees super space first'
        % (tot / 2**30, btot / 2**30))
    if LOG.failed:
        LOG('FAILED STEPS (port may not behave like the verified build): ' + ', '.join(LOG.failed))
    LOG('after first boot (optional): adb shell cmd package compile -m speed-profile -f com.android.systemui '
        '&& adb shell cmd package compile -m speed-profile -f com.android.settings '
        '&& adb shell cmd package compile -m speed-profile -f com.android.launcher')
    open(os.path.join(args.out, 'BUILD_REPORT.txt'), 'w').write('\n'.join(LOG.lines).lstrip() + '\n')
    if not args.keep_work:
        shutil.rmtree(args.work, ignore_errors=True)
    print('\noutput:', args.out)
    return 1 if LOG.failed else 0


if __name__ == '__main__':
    sys.exit(main())
