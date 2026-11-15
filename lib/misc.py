# Settings > Miscellaneous: a port_kit page with switches for features ColorOS hides or gates, plus the
# services.jar patches some of them need.
#
# The page is one extra dex appended to Settings.apk (built in code, so resources.arsc stays untouched)
# and one row in top_level_settings_oplus.xml. The apk keeps its platform signing block: system-partition
# apps are not re-verified by the package manager. Each switch writes 1/0 to the keys in its spec; the
# reader of each key is listed in SPECS.
import os
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
import zlib

from dexpatch import PatchError, ZipFile, Dex, _pool, _pool_str, _type_entries, _read_deflated, \
    _rewrite_deflated, _xml_tables, find_one, patch_dex_in_zip

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(KIT, 'assets', 'misc')
PKG = 'com.android.settings.portmisc'
FRAGMENT = PKG + '.MiscFragment'
TITLE = 'Miscellaneous'
ICON = 'settings_laboratory_ic'                 # drawable of the top-level row
ANCHOR_CATEGORY = 'connect_settings_category'   # the row's card goes right before this one
DOWNGRADE_PROP = 'persist.sys.port.allow_downgrade'

# (type, targets, title, summary). targets = "table:key[,table:key]", table = system|secure|global|prop.
SPECS = [
    ('C', '', 'Screenshots and recording'),
    # WindowManagerService honours disable_secure_windows only on debuggable builds; services_secure_windows
    # drops that check.
    # + persist.sys.port.secure_video for SurfaceView layers (framework_surfaceview_smali).
    ('S', 'secure:disable_secure_windows,prop:persist.sys.port.secure_video', 'Allow screenshots in secure apps',
     'Screenshots and screen recording also work in apps that block them (FLAG_SECURE), video and camera views '
     'included. DRM video stays black. Reopen the app after changing.'),
    # Read by the ColorOS screen recorder (OplusScreenRecorder, ScreenOffMonitor): when 1 it no longer
    # stops recording on SCREEN_OFF.
    ('S', 'system:recording_settings_enable_screen_off_pause', 'Keep recording when locked',
     'A screen recording started while unlocked continues when the phone locks or the screen turns off.'),
    ('C', '', 'Apps'),
    # Read by PackageManagerServiceUtils.isDowngradePermitted (services_downgrade_smali).
    ('S', 'prop:' + DOWNGRADE_PROP, 'Allow app downgrades',
     'Install an older version of an app over a newer one, keeping its data.'),
    # SettingsProvider answers 0 to the chosen apps (settingsprovider_smali; list = Global port_hide_dev_pkgs).
    ('S', 'global:port_hide_dev', 'Hide developer options from apps',
     'The apps you choose see Developer options and USB debugging as off. Force stop the app after changing.'),
    ('L', 'com.android.settings.portmisc.AppsFragment', 'Choose apps', ''),
    # PortSpoof.onNewApplication (framework_instrumentation_smali).
    ('S', 'prop:persist.sys.port.spoof_snapchat', 'Snapchat as Pixel',
     'Snapchat sees this phone as a Google Pixel XL. Force stop Snapchat after changing.'),
    # add_photos_sysconfig + framework_package_manager_smali; default 1 from system build.prop.
    ('S', 'prop:persist.sys.port.photos_unlimited', 'Google Photos unlimited backup',
     'Google Photos backs up photos and videos from this phone without using your storage. '
     'Force stop Photos after changing.'),
]


# ---------------------------------------------------------------- services.jar

WMS_OBSERVER = 'Lcom/android/server/wm/WindowManagerService$SettingsObserver;'
PMS_UTILS = 'Lcom/android/server/pm/PackageManagerServiceUtils;'


def services_secure_windows(dex):
    """WindowManagerService$SettingsObserver.updateDisableSecureWindows() returns early unless
    ro.debuggable is set, so Settings.Secure disable_secure_windows (AOSP's own switch that makes
    WindowState.isSecureLocked() false) does nothing on a user build. The `if-nez <debuggable>` that
    skips the early return becomes `goto/16` to the same target (same 21t/20t layout)."""
    ins = dex.insns(WMS_OBSERVER, 'updateDisableSecureWindows')
    sites = []
    for k in range(len(ins) - 4):
        a, b, c, d = ins[k:k + 4]
        if a.op in (0x1a, 0x1b) and a.ref() == 'ro.debuggable' and b.op in (0x12, 0x13) \
                and c.op == 0x71 and (c.ref() or '').endswith('SystemProperties;->getBoolean(Ljava/lang/String;Z)Z') \
                and d.op == 0x0a and ins[k + 4].op == 0x39:
            sites.append(ins[k + 4])
    x = find_one(sites, 'ro.debuggable check in updateDisableSecureWindows')
    dex.d[x.off] = 0x29
    dex.d[x.off + 1] = 0


def services_downgrade_smali(smali_file):
    """PackageManagerServiceUtils.isDowngradePermitted(installFlags, isAppDebuggable) allows a downgrade
    only for `adb install -d` on debuggable builds or debuggable apps. With persist.sys.port.allow_downgrade=1
    (Settings > Miscellaneous) it returns true first, so any installer can install an older version
    over a newer one (data kept)."""
    s = open(smali_file, encoding='utf8').read()
    if DOWNGRADE_PROP in s:
        return
    m = re.search(r'^\.method public static isDowngradePermitted\(IZ\)Z\n\s*\.registers (\d+)\n', s, re.M)
    if not m:
        raise PatchError('isDowngradePermitted(IZ)Z not found')
    if int(m.group(1)) < 4:
        raise PatchError('isDowngradePermitted has too few registers')
    ins = ('\n    const-string v0, "%s"\n\n    const/4 v1, 0x0\n\n'
           '    invoke-static {v0, v1}, Landroid/os/SystemProperties;->getBoolean(Ljava/lang/String;Z)Z\n\n'
           '    move-result v0\n\n    if-eqz v0, :cond_port_downgrade\n\n    const/4 v0, 0x1\n\n    return v0\n\n'
           '    :cond_port_downgrade\n' % DOWNGRADE_PROP)
    open(smali_file, 'w', encoding='utf8').write(s[:m.end()] + ins + s[m.end():])


def patch_services(jar, tools, work, log, smali_patch_jar):
    patch_dex_in_zip(jar, WMS_OBSERVER, services_secure_windows, 'secure windows')
    log('services: Settings.Secure disable_secure_windows works on user builds (Miscellaneous switch)')
    where = smali_patch_jar(jar, tools, work, {PMS_UTILS: services_downgrade_smali})
    log('services: app downgrades follow %s (%s rebuilt with smali)' % (DOWNGRADE_PROP, where[PMS_UTILS]))


# ---------------------------------------------------------------- framework.jar (smali 3)

SPOOF = 'Lcom/android/internal/util/port/PortSpoof;'
INSTR = 'Landroid/app/Instrumentation;'
SURFACE_VIEW = 'Landroid/view/SurfaceView;'
SECURE_VIDEO_PROP = 'persist.sys.port.secure_video'
SNAPCHAT_PROP = 'persist.sys.port.spoof_snapchat'
PHOTOS_PROP = 'persist.sys.port.photos_unlimited'     # default 1 from system build.prop
APP_PM = 'Landroid/app/ApplicationPackageManager;'
# App processes read these, so they need an app-readable label; Settings (system_app) may set exported_system_prop.
APP_PROPS = [SECURE_VIDEO_PROP, SNAPCHAT_PROP, PHOTOS_PROP]


def _insert_at_method_start(s, sig, code, what):
    """Insert smali `code` before the first instruction of method `sig` (after .registers/.param/annotations)."""
    m = list(re.finditer(r'^\.method [^\n]*' + re.escape(sig) + r'\n', s, re.M))
    if len(m) != 1:
        raise PatchError('%s: %d methods match %s' % (what, len(m), sig))
    end = s.index('\n.end method', m[0].end())
    body = s[m[0].end():end]
    pos, in_ann = 0, False
    for line in body.splitlines(keepends=True):
        t = line.strip()
        if in_ann:
            in_ann = not t.startswith('.end annotation')
        elif t.startswith('.annotation'):
            in_ann = True
        elif t and not t.startswith(('.registers', '.locals', '.param', '.end param', '.line', '.local ',
                                     '.prologue', '#')):
            break
        pos += len(line)
    return s[:m[0].end() + pos] + code + s[m[0].end() + pos:]


def framework_instrumentation_smali(smali_file):
    """Instrumentation.newApplication (both overloads) calls PortSpoof.onNewApplication(context) first, so
    per-app Build values are in place before the app's code runs (as Lunaris AOSP does with PixelPropsUtils)."""
    s = open(smali_file, encoding='utf8').read()
    if SPOOF in s:
        raise PatchError('Instrumentation already calls PortSpoof')
    call = '    invoke-static {%s}, ' + SPOOF + '->onNewApplication(Landroid/content/Context;)V\n\n'
    s = _insert_at_method_start(s, 'newApplication(Ljava/lang/Class;Landroid/content/Context;)Landroid/app/Application;',
                                call % 'p1', 'Instrumentation static newApplication')
    s = _insert_at_method_start(s, 'newApplication(Ljava/lang/ClassLoader;Ljava/lang/String;Landroid/content/Context;)'
                                   'Landroid/app/Application;', call % 'p3', 'Instrumentation newApplication')
    open(smali_file, 'w', encoding='utf8').write(s)


def framework_surfaceview_smali(smali_file):
    """SurfaceView.setSecure(true) becomes setSecure(false) while persist.sys.port.secure_video is on, so video
    and camera previews in secure apps show up in screenshots and recordings (WindowManager's
    disable_secure_windows only covers windows, not SurfaceView layers). DRM-protected layers stay black."""
    s = open(smali_file, encoding='utf8').read()
    code = ('    if-eqz p1, :cond_port_secure_video\n\n'
            '    invoke-static {}, ' + SPOOF + '->secureVideoAllowed()Z\n\n'
            '    move-result v0\n\n'
            '    if-eqz v0, :cond_port_secure_video\n\n'
            '    const/4 p1, 0x0\n\n'
            '    :cond_port_secure_video\n')
    s = _insert_at_method_start(s, 'setSecure(Z)V', code, 'SurfaceView.setSecure')
    m = re.search(r'setSecure\(Z\)V\n\s*\.registers (\d+)', s)
    if not m or int(m.group(1)) < 3:
        raise PatchError('SurfaceView.setSecure has no free v0 register')
    open(smali_file, 'w', encoding='utf8').write(s)


def framework_package_manager_smali(smali_file):
    """ApplicationPackageManager.hasSystemFeature(String, int) answers false for Google Photos' preload features
    while persist.sys.port.photos_unlimited is 0, so the always-present sysconfig features become a switch.
    It runs in the app's own process, so the change applies when Photos restarts."""
    s = open(smali_file, encoding='utf8').read()
    code = ('    invoke-static {p1}, ' + SPOOF + '->hideFeature(Ljava/lang/String;)Z\n\n'
            '    move-result v0\n\n'
            '    if-eqz v0, :cond_port_feature\n\n'
            '    const/4 v0, 0x0\n\n'
            '    return v0\n\n'
            '    :cond_port_feature\n')
    s = _insert_at_method_start(s, 'hasSystemFeature(Ljava/lang/String;I)Z', code,
                                'ApplicationPackageManager.hasSystemFeature')
    open(smali_file, 'w', encoding='utf8').write(s)


def _smali3(tools, *args):
    subprocess.run(['java', '-cp', os.path.join(tools['smali3'], '*')] + list(args), check=True,
                   stdout=subprocess.DEVNULL)


def patch_framework(jar, tools, work, log, rebuild_jar):
    """framework.jar: secure video and the Snapchat spoof. Needs smali 3 (tools/smali3): baksmali 2.5.2 fails on
    framework's newer hidden-API flags. Assembled with -a 29 (dex 039, hidden-API flags kept)."""
    patchers = {INSTR: framework_instrumentation_smali, SURFACE_VIEW: framework_surfaceview_smali,
                APP_PM: framework_package_manager_smali}
    z = ZipFile(jar)
    names = sorted(n for n in z.entries if re.fullmatch(r'classes\d*\.dex', n))
    where = {}
    for n in names:
        d = Dex(z.read(n))
        if d.has_class(SPOOF):
            raise PatchError('framework.jar already has PortSpoof')
        for cls in patchers:
            if d.has_class(cls):
                where[cls] = n
    for cls in patchers:
        if cls not in where:
            raise PatchError('%s not found in framework.jar' % cls)
    tmp = tempfile.mkdtemp(dir=work)
    try:
        replace = {}
        for target in sorted(set(where.values())):
            dexf = os.path.join(tmp, target)
            open(dexf, 'wb').write(z.read(target))
            out = os.path.join(tmp, 'smali_' + target)
            _smali3(tools, 'com.android.tools.smali.baksmali.Main', 'd', '-o', out, dexf)
            for cls, fn in patchers.items():
                if where[cls] == target:
                    fn(os.path.join(out, cls[1:-1] + '.smali'))
            newdex = os.path.join(tmp, 'new_' + target)
            _smali3(tools, 'com.android.tools.smali.smali.Main', 'a', '-a', '29', '-o', newdex, out)
            replace[target] = open(newdex, 'rb').read()
        spoofdex = os.path.join(tmp, 'spoof.dex')
        _smali3(tools, 'com.android.tools.smali.smali.Main', 'a', '-a', '29', '-o', spoofdex,
                os.path.join(KIT, 'assets', 'misc', 'framework'))
        nxt = 'classes%d.dex' % (max(int(n[7:-4] or 1) for n in names) + 1)
        rebuild_jar(jar, replace, add=[(nxt, open(spoofdex, 'rb').read())])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    log('framework: SurfaceView.setSecure follows %s (%s); Instrumentation.newApplication -> PortSpoof (%s); '
        'hasSystemFeature hides the Photos features unless %s (%s); PortSpoof added as %s'
        % (SECURE_VIDEO_PROP, where[SURFACE_VIEW], where[INSTR], PHOTOS_PROP, where[APP_PM], nxt))


def add_app_prop_contexts(path, log):
    """Label the Miscellaneous props that app processes read as exported_system_prop (persist.sys.* is
    system_prop, which apps can't read)."""
    s = open(path, encoding='utf8').read()
    add = ''.join('%s u:object_r:exported_system_prop:s0 exact bool\n' % p for p in APP_PROPS
                  if not re.search(r'^' + re.escape(p) + r'\s', s, re.M))
    if not add:
        return
    if not s.endswith('\n'):
        s += '\n'
    open(path, 'w', encoding='utf8').write(s + '# port_kit: Settings > Miscellaneous (read by app processes)\n' + add)
    log('%s: %s labelled exported_system_prop' % (os.path.basename(path), ', '.join(APP_PROPS)))


# ---------------------------------------------------------------- SettingsProvider: hide developer options

SP_CLASS = 'Lcom/android/providers/settings/SettingsProvider;'
HIDE_DEV_KEY = 'port_hide_dev'              # Global, "1" = on
HIDE_DEV_PKGS = 'port_hide_dev_pkgs'        # Global, comma-separated packages
PORT_DEV_HIDDEN = '''
.method private portDevHidden(Ljava/lang/String;)Z
    .registers 9

    const/4 v0, 0x0

    invoke-static {p1}, Lcom/android/providers/settings/PortDevHide;->isDevSetting(Ljava/lang/String;)Z

    move-result v1

    if-eqz v1, :out

    invoke-static {}, Landroid/os/Binder;->getCallingUid()I

    move-result v1

    invoke-static {}, Landroid/os/Binder;->clearCallingIdentity()J

    move-result-wide v2

    :try_start
    const-string v4, "%s"

    invoke-direct {p0, v4}, Lcom/android/providers/settings/SettingsProvider;->getGlobalSetting(Ljava/lang/String;)Lcom/android/providers/settings/SettingsState$Setting;

    move-result-object v4

    const-string v5, "%s"

    invoke-direct {p0, v5}, Lcom/android/providers/settings/SettingsProvider;->getGlobalSetting(Ljava/lang/String;)Lcom/android/providers/settings/SettingsState$Setting;

    move-result-object v5

    invoke-virtual {p0}, Landroid/content/ContentProvider;->getContext()Landroid/content/Context;

    move-result-object v6

    invoke-static {v6, v1, v4, v5}, Lcom/android/providers/settings/PortDevHide;->shouldHide(Landroid/content/Context;ILcom/android/providers/settings/SettingsState$Setting;Lcom/android/providers/settings/SettingsState$Setting;)Z

    move-result v0
    :try_end
    .catchall {:try_start .. :try_end} :restore

    :restore
    invoke-static {v2, v3}, Landroid/os/Binder;->restoreCallingIdentity(J)V

    :out
    return v0
.end method
''' % (HIDE_DEV_KEY, HIDE_DEV_PKGS)


def settingsprovider_smali(smali_file):
    """SettingsProvider.packageValueForCallResult(type, name, ...) builds the reply to every Settings.*.get* call.
    When Global port_hide_dev is 1 and the calling app is in port_hide_dev_pkgs, it answers "0" for
    development_settings_enabled / adb_enabled / adb_wifi_enabled (apps that refuse to run with Developer options
    or USB debugging on). The reply carries no generation, so the app doesn't cache it."""
    s = open(smali_file, encoding='utf8').read()
    if 'portDevHidden' in s:
        raise PatchError('SettingsProvider already patched')
    if '->getGlobalSetting(Ljava/lang/String;)Lcom/android/providers/settings/SettingsState$Setting;' not in s:
        raise PatchError('SettingsProvider.getGlobalSetting(String) not found')
    sig = 'packageValueForCallResult(ILjava/lang/String;IILcom/android/providers/settings/SettingsState$Setting;Z)' \
          'Landroid/os/Bundle;'
    m = re.search(r'^\.method [^\n]*' + re.escape(sig) + r'\n\s*\.registers (\d+)', s, re.M)
    if not m or int(m.group(1)) < 9:      # 7 parameter registers + v0, v1
        raise PatchError('SettingsProvider.packageValueForCallResult: unexpected signature/registers')
    code = ('    invoke-direct {p0, p2}, ' + SP_CLASS + '->portDevHidden(Ljava/lang/String;)Z\n\n'
            '    move-result v0\n\n'
            '    if-eqz v0, :cond_port_dev\n\n'
            '    const-string v0, "value"\n\n'
            '    const-string v1, "0"\n\n'
            '    invoke-static {v0, v1}, Landroid/os/Bundle;->forPair(Ljava/lang/String;Ljava/lang/String;)Landroid/os/Bundle;\n\n'
            '    move-result-object v0\n\n'
            '    return-object v0\n\n'
            '    :cond_port_dev\n')
    s = _insert_at_method_start(s, sig, code, 'SettingsProvider.packageValueForCallResult')
    s = s.rstrip('\n') + '\n' + PORT_DEV_HIDDEN
    open(smali_file, 'w', encoding='utf8').write(s)


def replace_entries_keep_sigblock(apk, replace):
    """Rewrite an apk with some entries replaced (stored entries stay 4-byte aligned, .so 4096) and the original
    APK Signing Block put back in front of the central directory. Like add_stored_entry, the block's digests no
    longer match; system apps on this ROM are not re-verified (Settings and Melody rely on the same)."""
    a = open(apk, 'rb').read()
    eocd = a.rfind(b'PK\x05\x06')
    cdoff, = struct.unpack_from('<I', a, eocd + 16)
    if a[cdoff - 16:cdoff] != b'APK Sig Block 42':
        raise PatchError('no APK signing block in ' + os.path.basename(apk))
    sigblock = a[cdoff - struct.unpack_from('<Q', a, cdoff - 24)[0] - 8:cdoff]
    src = zipfile.ZipFile(apk)
    tmp = apk + '.new'
    with zipfile.ZipFile(tmp, 'w') as out:
        for info in src.infolist():
            data = replace.get(info.filename) or src.read(info.filename)
            zi = zipfile.ZipInfo(info.filename, info.date_time)
            zi.external_attr = info.external_attr
            zi.compress_type = zipfile.ZIP_STORED if info.filename in replace else info.compress_type
            if zi.compress_type == zipfile.ZIP_STORED:
                align = 4096 if info.filename.endswith('.so') else 4
                off = out.fp.tell() + 30 + len(info.filename.encode())
                zi.extra = b'\0' * ((align - off % align) % align)
            out.writestr(zi, data)
    src.close()
    b = open(tmp, 'rb').read()
    e = b.rfind(b'PK\x05\x06')
    cd, = struct.unpack_from('<I', b, e + 16)
    end = bytearray(b[e:])
    struct.pack_into('<I', end, 16, cd + len(sigblock))
    open(tmp, 'wb').write(b[:cd] + sigblock + b[cd:e] + bytes(end))
    os.replace(tmp, apk)


def patch_settingsprovider(apk, tools, work, log):
    z = ZipFile(apk)
    names = sorted(n for n in z.entries if re.fullmatch(r'classes\d*\.dex', n))
    target = [n for n in names if Dex(z.read(n)).has_class(SP_CLASS)]
    if len(target) != 1:
        raise PatchError('SettingsProvider class in %d dex files' % len(target))
    target = target[0]
    tmp = tempfile.mkdtemp(dir=work)
    try:
        dexf = os.path.join(tmp, target)
        open(dexf, 'wb').write(z.read(target))
        out = os.path.join(tmp, 'smali')
        subprocess.run(['java', '-jar', tools['baksmali'], 'd', '-o', out, dexf], check=True,
                       stdout=subprocess.DEVNULL)
        settingsprovider_smali(os.path.join(out, SP_CLASS[1:-1] + '.smali'))
        helper = os.path.join('com', 'android', 'providers', 'settings', 'PortDevHide.smali')
        shutil.copy(os.path.join(KIT, 'assets', 'misc', 'settingsprovider', helper), os.path.join(out, helper))
        newdex = os.path.join(tmp, 'new.dex')
        subprocess.run(['java', '-jar', tools['smali'], 'a', '--api', '28', '-o', newdex, out], check=True,
                       stdout=subprocess.DEVNULL)
        replace_entries_keep_sigblock(apk, {target: open(newdex, 'rb').read()})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    log('SettingsProvider: Global %s / %s hide developer options and USB debugging from the chosen apps (%s)'
        % (HIDE_DEV_KEY, HIDE_DEV_PKGS, target))


PHOTOS_XML = 'system/etc/sysconfig/port_photos_unlimited.xml'


def add_photos_sysconfig(s, log):
    """Google Photos unlimited backup. Photos grants it to devices that declare its Pixel/Nexus preload
    features; it reads them with hasSystemFeature, so a sysconfig file is enough (no Build spoof).
    The features are always declared; the Misc page switch (persist.sys.port.photos_unlimited) hides them from
    apps through framework_package_manager_smali."""
    d = os.path.dirname(PHOTOS_XML)
    like = sorted(f for f in os.listdir(s.path(d)) if f.endswith('.xml'))
    if not like:
        raise RuntimeError('system/%s has no xml to copy metadata from' % d)
    s.add_new(PHOTOS_XML, open(os.path.join(KIT, 'assets', 'misc', 'sysconfig', os.path.basename(PHOTOS_XML))).read(),
              like=d + '/' + like[0])
    log('system/%s: Google Photos Pixel preload features (unlimited backup)' % PHOTOS_XML)


# ---------------------------------------------------------------- Settings page dex

def _smali_str(s):
    out = []
    for ch in s:
        o = ord(ch)
        if ch in '"\\':
            out.append('\\' + ch)
        elif 0x20 <= o < 0x7f:
            out.append(ch)
        else:
            out.append('\\u%04x' % o)
    return '"%s"' % ''.join(out)


def _spec_line(s):
    s = list(s) + [''] * (4 - len(s))
    if '|' in ''.join(s):
        raise PatchError('"|" in Miscellaneous spec ' + s[2])
    return '|'.join(s)


def _specs_method(title, specs):
    lines = ['.method public pageTitle()Ljava/lang/String;', '    .registers 2', '',
             '    const-string v0, ' + _smali_str(title), '', '    return-object v0', '.end method', '',
             '.method public specs()[Ljava/lang/String;', '    .registers 3', '',
             '    const/16 v0, 0x%x' % len(specs), '', '    new-array v0, v0, [Ljava/lang/String;', '']
    for i, s in enumerate(specs):
        lines += ['    const/16 v1, 0x%x' % i, '', '    const-string v2, ' + _smali_str(_spec_line(s)), '',
                  '    aput-object v2, v0, v1', '']
    lines += ['    return-object v0', '.end method']
    return '\n'.join(lines)


def build_dex(tools, work):
    """Assemble assets/misc/smali with the generated specs() method."""
    tmp = tempfile.mkdtemp(dir=work)
    try:
        src = os.path.join(tmp, 'smali')
        shutil.copytree(os.path.join(ASSETS, 'smali'), src)
        f = os.path.join(src, *PKG.split('.'), 'MiscFragment.smali')
        t = open(f).read()
        if t.count('#@SPECS@') != 1:
            raise PatchError('MiscFragment.smali: no #@SPECS@ marker')
        open(f, 'w').write(t.replace('#@SPECS@', _specs_method(TITLE, SPECS)))
        out = os.path.join(tmp, 'misc.dex')
        subprocess.run(['java', '-jar', tools['smali'], 'a', '--api', '28', '-o', out, src],
                       check=True, stdout=subprocess.DEVNULL)
        return open(out, 'rb').read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _class_index(data):
    """{class: (superclass, {name+proto of every declared method})} of one dex."""
    d = Dex(data)
    out = {}
    for c in range(d.cd_sz):
        ci, _, sup, _, _, _, cdata, _ = struct.unpack_from('<8I', d.d, d.cd_off + 32 * c)
        ms = set()
        if cdata:
            p = cdata
            sf, p = d._uleb(p)
            inf, p = d._uleb(p)
            dm, p = d._uleb(p)
            vm, p = d._uleb(p)
            for _ in range(sf + inf):
                _, p = d._uleb(p)
                _, p = d._uleb(p)
            mi = 0
            for k in range(dm + vm):
                if k == dm:
                    mi = 0
                dlt, p = d._uleb(p)
                mi += dlt
                _, p = d._uleb(p)
                _, p = d._uleb(p)
                ms.add(d.method(mi).split('->', 1)[1])
        out[d.type(ci)] = (d.type(sup) if sup != 0xffffffff else None, ms)
    return out


def check_refs(apk, dex):
    """Every Settings class/method the page calls must exist in this Settings build (walking up the
    class hierarchy until it leaves the apk, where the framework takes over)."""
    z = zipfile.ZipFile(apk)
    idx = {}
    for n in z.namelist():
        if re.fullmatch(r'classes\d*\.dex', n):
            idx.update(_class_index(z.read(n)))
    own = _class_index(dex)
    d = Dex(dex)
    missing = []
    for i in range(d.mid_sz):
        cls, m = d.method(i).split('->', 1)
        if cls in own or cls.startswith(('Ljava/', 'Landroid/', 'Ldalvik/')):
            continue
        c = cls
        while c in idx and m not in idx[c][1]:
            c = idx[c][0]
        if c is None or (c in idx and m in idx[c][1]):
            continue
        if cls not in idx:
            missing.append(cls)
        elif c not in idx:
            continue                    # inherited from a framework class
        else:
            missing.append(cls + '->' + m)
    for i in range(d.tid_sz):
        t = d.type(i).lstrip('[')
        if t.startswith('L') and not t.startswith(('Ljava/', 'Landroid/', 'Ldalvik/')) \
                and t not in own and t not in idx:
            missing.append(t)
    if missing:
        raise PatchError('Settings lacks what the Miscellaneous page uses: ' + ', '.join(sorted(set(missing))[:8]))


def add_stored_entry(apk, name, data):
    """Append a stored (uncompressed, 4-byte aligned) entry. The APK Signing Block moves behind the new
    entry unchanged and the central directory gets one more record."""
    z = ZipFile(apk)
    if name in z.entries:
        raise PatchError(name + ' already in ' + os.path.basename(apk))
    a = z.a
    ends = []
    for t in z.entries.values():
        ds, de = z.data_range(t['name'])
        if t['flg'] & 8:
            de += 16 if a[de:de + 4] == b'PK\x07\x08' else 12
        ends.append(de)
    entries_end = max(ends)
    cdoff = z.cd_off
    if a[cdoff - 16:cdoff] != b'APK Sig Block 42':
        raise PatchError('no APK signing block in front of central directory')
    blk = cdoff - struct.unpack_from('<Q', a, cdoff - 24)[0] - 8
    eocd = a.rfind(b'PK\x05\x06')
    ref = z.entries['classes.dex']
    ver, = struct.unpack_from('<H', a, ref['lho'] + 4)
    tm, dt = struct.unpack_from('<HH', a, ref['lho'] + 10)
    nb = name.encode()
    pad = (4 - (entries_end + 30 + len(nb)) % 4) % 4
    crc = zlib.crc32(data) & 0xffffffff
    local = struct.pack('<IHHHHHIIIHH', 0x04034b50, ver, 0, 0, tm, dt, crc, len(data), len(data), len(nb), pad) \
        + nb + bytes(pad) + data
    vmade, = struct.unpack_from('<H', a, ref['cd'] + 4)
    cdrec = struct.pack('<IHHHHHHIIIHHHHHII', 0x02014b50, vmade, ver, 0, 0, tm, dt, crc, len(data), len(data),
                        len(nb), 0, 0, 0, 0, 0, entries_end) + nb
    sigblock = a[blk:cdoff]
    cd = a[cdoff:eocd] + cdrec
    new = a[:entries_end] + local + sigblock
    newcd = len(new)
    end = bytearray(a[eocd:])
    n, = struct.unpack_from('<H', end, 10)
    struct.pack_into('<HHII', end, 8, n + 1, n + 1, len(cd), newcd)
    z.a = new + cd + end
    z.save()


# ---------------------------------------------------------------- top-level row

def res_id(apk, rtype, rname):
    a = ZipFile(apk).read('resources.arsc')
    _, hs, size = struct.unpack_from('<HHI', a, 0)
    p, pkg = hs, None
    while p < size:
        ct, _, csz = struct.unpack_from('<HHI', a, p)
        if ct == 0x200:
            pkg = p
            break
        p += csz
    pid, = struct.unpack_from('<I', a, pkg + 8)
    _, phs, psz = struct.unpack_from('<HHI', a, pkg)
    tstr, _, kstr, _ = struct.unpack_from('<IIII', a, pkg + 268)
    tpi, kpi = _pool(a, pkg + tstr), _pool(a, pkg + kstr)
    found = set()
    p = pkg + phs
    while p < pkg + psz:
        ct, chs, csz = struct.unpack_from('<HHI', a, p)
        if ct == 0x201:
            tid, items = _type_entries(a, p, chs)
            if _pool_str(a, tpi, tid - 1)[0] == rtype:
                for eid, e in items:
                    esz, efl, key = struct.unpack_from('<HHI', a, e)
                    if efl & 8:
                        key = esz                 # compact entry: key index sits in the size field
                    if _pool_str(a, kpi, key)[0] == rname:
                        found.add((pid << 24) | (tid << 16) | eid)
        p += csz
    return find_one(sorted(found), '%s/%s in resources.arsc' % (rtype, rname))


def _encode_pool(strings, utf8):
    data, offs = bytearray(), []
    for s in strings:
        offs.append(len(data))
        if utf8:
            b = s.encode('utf8')
            for n in (len(s), len(b)):
                data += bytes([0x80 | (n >> 8), n & 0xff]) if n >= 0x80 else bytes([n])
            data += b + b'\0'
        else:
            b = s.encode('utf-16le')
            n = len(b) // 2
            data += struct.pack('<HH', 0x8000 | (n >> 16), n & 0xffff) if n >= 0x8000 else struct.pack('<H', n)
            data += b + b'\0\0'
    while len(data) % 4:
        data += b'\0'
    hs = 28
    ss = hs + 4 * len(strings)
    hdr = struct.pack('<HHIIIIII', 1, hs, ss + len(data), len(strings), 0, 0x100 if utf8 else 0, ss, 0)
    return hdr + struct.pack('<%dI' % len(strings), *offs) + data


def _start_elem(line, name, attrs):
    body = struct.pack('<IIHHHHHH', 0xffffffff, name, 20, 20, len(attrs), 0, 0, 0)
    for at in attrs:
        body += struct.pack('<IIIHBBI', *at)
    return struct.pack('<HHIII', 0x102, 16, 16 + len(body), line, 0xffffffff) + body


def _end_elem(line, name):
    return struct.pack('<HHIIIII', 0x103, 16, 24, line, 0xffffffff, 0xffffffff, name)


def insert_top_level_row(apk, entry='res/xml/top_level_settings_oplus.xml'):
    """Add a card with one row "Miscellaneous" that opens MiscFragment. The card copies the attributes
    of an existing HomepageTopCategory, the row those of the "Display & brightness" row (icon tint, layout)."""
    z = ZipFile(apk)
    x = _read_deflated(z, entry)
    resmap, pool = _xml_tables(x)
    if FRAGMENT in pool:
        return 'already present'
    A = {'icon': 0x01010002, 'title': 0x010101e1, 'key': 0x010101e8, 'fragment': 0x010102e3}
    chunks, p = [], 8
    while p < len(x):
        t, hs, sz = struct.unpack_from('<HHI', x, p)
        chunks.append((t, p, sz))
        p += sz
    pool_chunk = [c for c in chunks if c[0] == 1][0]
    pi = _pool(x, pool_chunk[1])
    if pi['stc']:
        raise PatchError(entry + ': string pool has styles')

    def elem(p):
        nm, = struct.unpack_from('<I', x, p + 20)
        ast, asz, acnt = struct.unpack_from('<HHH', x, p + 24)
        at = [list(struct.unpack_from('<IIIHBBI', x, p + 16 + ast + i * asz)) for i in range(acnt)]
        return pool[nm], nm, at

    def keyof(at):
        for q in at:
            if q[1] < len(resmap) and resmap[q[1]] == A['key'] and q[2] != 0xffffffff:
                return pool[q[2]]

    anchor = row = extra = None
    for i, (t, p, sz) in enumerate(chunks):
        if t != 0x102:
            continue
        name, nm, at = elem(p)
        k = keyof(at)
        if name.endswith('.HomepageTopCategory') and k == ANCHOR_CATEGORY:
            anchor = (i, p, name, nm, at)
        if name.endswith('.SettingsSimpleJumpPreference') and k == 'display_and_brightness':
            row = (i, p, name, nm, at)
            nt, np_, _ = chunks[i + 1]
            if nt == 0x102 and elem(np_)[0] == 'extra':
                extra = elem(np_)
    if not anchor or not row:
        raise PatchError('%s: anchor category or Display row not found' % entry)
    strings = list(pool)

    def sidx(s):
        if s not in strings:
            strings.append(s)
        return strings.index(s)

    def setattr_(at, rid, s=None, ref=None):
        for q in at:
            if q[1] < len(resmap) and resmap[q[1]] == rid:
                if ref is not None:
                    q[2], q[5], q[6] = 0xffffffff, 0x01, ref
                else:
                    q[2], q[5], q[6] = sidx(s), 0x03, sidx(s)
                return
        raise PatchError('attribute %#x missing on the cloned element' % rid)

    line, = struct.unpack_from('<I', x, anchor[1] + 8)
    cat_at = [list(q) for q in anchor[4]]
    setattr_(cat_at, A['key'], 'port_misc_category')
    keep = {A['icon'], A['title'], A['key'], A['fragment']}
    names = {'layoutCategory', 'needChangeDrawType', 'showTwoToneColor', 'tintIconNew', 'tintType', 'showSummary'}
    row_at = [list(q) for q in row[4]
              if q[1] < len(resmap) and (resmap[q[1]] in keep or pool[q[1]] in names)]
    setattr_(row_at, A['icon'], ref=res_id(apk, 'drawable', ICON))
    setattr_(row_at, A['title'], TITLE)
    setattr_(row_at, A['key'], 'port_misc_entry')
    setattr_(row_at, A['fragment'], FRAGMENT)
    new = _start_elem(line, anchor[3], cat_at) + _start_elem(line, row[3], row_at)
    if extra:
        new += _start_elem(line, extra[1], extra[2]) + _end_elem(line, extra[1])
    new += _end_elem(line, row[3]) + _end_elem(line, anchor[3])
    out = bytearray(x[:8])
    for t, p, sz in chunks:
        if p == anchor[1]:
            out += new
        out += _encode_pool(strings, pi['fl'] & 0x100) if t == 1 else x[p:p + sz]
    struct.pack_into('<I', out, 4, len(out))
    delta, gap = _rewrite_deflated(z, entry, out)
    return 'added before %s (entry %+d bytes)' % (ANCHOR_CATEGORY, delta)


def patch_settings(apk, tools, work, log):
    dex = build_dex(tools, work)
    check_refs(apk, dex)
    z = ZipFile(apk)
    names = [n for n in z.entries if re.fullmatch(r'classes\d*\.dex', n)]
    if any(Dex(z.read(n)).has_class('L%s;' % FRAGMENT.replace('.', '/')) for n in names):
        raise PatchError('Settings.apk already has the Miscellaneous page')
    nxt = 'classes%d.dex' % (max(int(n[7:-4] or 1) for n in names) + 1)
    add_stored_entry(apk, nxt, dex)
    log('Miscellaneous: page code added to Settings as %s (%d bytes, %d rows)' % (nxt, len(dex), len(SPECS)))
    log('Miscellaneous: Settings top-level row ' + insert_top_level_row(apk))
