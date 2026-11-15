# Code patches applied to donor apps / framework. Each patch locates its site by
# class + method + instruction pattern and refuses to write if the shape differs.
import os
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile

from dexpatch import (PatchError, Dex, ZipFile, dest_regs, find_one, patch_dex_in_zip, patch_any_dex_in_zip,
                      patch_arsc_string, insert_xml_attr, set_xml_int_attr, set_branch_offset,
                      restyle_xml_element_like)


def _next(ins, i):
    return ins[i + 1] if i + 1 < len(ins) else None


# ------------------------------------------------------------------ Settings.apk

def settings_about_banner(dex):
    """About device: show the ColorOS banner although com.oplus.ota is removed.
    OtaUpdateController.getAvailabilityStatus: neutralise `if-eqz isOtaEnabled -> UNSUPPORTED`."""
    ins = dex.insns('Lcom/oplus/settings/feature/deviceinfo/controller/OtaUpdateController;', 'getAvailabilityStatus')
    hits = [x for k, x in enumerate(ins) if x.op == 0x38 and k >= 2
            and ins[k - 2].ref() == 'Ljava/lang/Boolean;->booleanValue()Z' and ins[k - 1].op == 0x0a
            and _next(ins, k) is not None and _next(ins, k).op == 0x0f]
    set_branch_offset(find_one(hits, 'OtaUpdateController.getAvailabilityStatus'), 2)


def settings_hide_quick_glance(dex):
    """Settings 'Quick glance' card (stuck on 'Preparing content'): never send OS_USE_30_DAYS.
    MessageEntryUtils.sendNewVersionFunctionBroadcast: `if-nez support_settings_os_recommend` falls
    through to the stock 'do nothing not support' return."""
    ins = dex.insns('Lcom/oplus/settings/feature/homepage/messageentry/MessageEntryUtils;', 'sendNewVersionFunctionBroadcast')
    hits = []
    for k, x in enumerate(ins):
        if x.op == 0x39 and any(y.ref() == 'support_settings_os_recommend' for y in ins[max(0, k - 6):k]):
            n = _next(ins, k)
            if n is not None and n.op in (0x1a, 0x1b) and 'not support' in n.ref():
                hits.append(x)
    set_branch_offset(find_one(hits[:1], 'MessageEntryUtils.sendNewVersionFunctionBroadcast'), 2)


def settings_hide_software_update_row(dex):
    """System & update: keep the 'Software update' row hidden (the banner patch would show it).
    SoftwareUpdatePreferenceController.onResume: `isAvailable(); move-result R` -> `const/4 R, 0; nop*3`."""
    ins = dex.insns('Lcom/oplus/settings/feature/othersettings/controller/SoftwareUpdatePreferenceController;', 'onResume')
    hits = [k for k, x in enumerate(ins) if x.op in (0x6e, 0x74) and x.ref() and x.ref().endswith('->isAvailable()Z')
            and _next(ins, k) is not None and _next(ins, k).op == 0x0a
            and k + 2 < len(ins) and (ins[k + 2].ref() or '').endswith('->setVisible(Z)V')]
    k = find_one(hits, 'SoftwareUpdatePreferenceController.onResume')
    reg = ins[k + 1].aa
    if reg > 15:
        raise PatchError('register v%d too high for const/4' % reg)
    dex.d[ins[k].off:ins[k].off + 8] = bytes([0x12, reg]) + b'\0' * 6


# ------------------------------------------------------------------ SystemUI.apk

def systemui_seamless_aod(dex):
    """Seamless AOD style: base HAL returns panel feature 217 = 0, so SystemUI drops
    isSupportSmoothTransition. In the 'get feature error' path store the method's
    constant-true register instead of false."""
    ins = dex.insns('Lcom/oplus/systemui/aod/display/SmoothTransitionController;', 'initSmoothTransitionState')
    err = find_one([k for k, x in enumerate(ins) if x.op in (0x1a, 0x1b) and 'get feature error' in x.ref()],
                   'initSmoothTransitionState error string')
    k = next((k for k in range(err, len(ins)) if ins[k].op == 0x5c
              and ins[k].ref().endswith('->isSupportSmoothTransition:Z')), None)
    if k is None:
        raise PatchError('isSupportSmoothTransition store not found')
    one = None
    for j, x in enumerate(ins[:err]):
        if x.op == 0x12 and x.b4 == 1:
            one = (j, x.a4)
            break
    if one is None:
        raise PatchError('no const/4 vX, 0x1 before the error path')
    j, reg = one
    if any(reg in dest_regs(x) for x in ins[j + 1:k]):
        raise PatchError('v%d is overwritten before the error path' % reg)
    dex.d[ins[k].off + 1] = (dex.d[ins[k].off + 1] & 0xf0) | reg


def systemui_timeout_aod(dex):
    """Screen timeout goes to AOD like the power button: in onStartedGoingToSleep skip the
    `reason==timeout && !mKgShowingWhileGoingToSleep -> AodType 2003` branch."""
    ins = dex.insns('Lcom/oplus/systemui/keyguard/OplusKeyguardViewMediatorExImpl;', 'onStartedGoingToSleep')
    hits = [_next(ins, k) for k, x in enumerate(ins) if x.op == 0x55
            and x.ref().endswith('->mKgShowingWhileGoingToSleep:Z')
            and _next(ins, k) is not None and _next(ins, k).op == 0x38 and _next(ins, k).aa == x.a4]
    set_branch_offset(find_one(hits, 'onStartedGoingToSleep kgShowing branch'), 2)


# ------------------------------------------------------------------ oplus-services.jar

def services_engineer_checkservice(dex):
    """Engineer HAL is not declared on this device: waitForService() would block forever.
    Use checkService() (returns null immediately) like the working port."""
    wait = 'Landroid/os/ServiceManager;->waitForService(Ljava/lang/String;)Landroid/os/IBinder;'
    check = dex.method_index('Landroid/os/ServiceManager;->checkService(Ljava/lang/String;)Landroid/os/IBinder;')
    if check is None:
        raise PatchError('checkService method id not present in this dex')
    hits = []
    for _, off, units in dex.methods('Lcom/android/server/engineering/OplusEngineerFwService;'):
        ins = dex.insns_at(off, units)
        for k, x in enumerate(ins):
            if x.op == 0x71 and x.ref() == wait and k and ins[k - 1].op in (0x1a, 0x1b) \
                    and ins[k - 1].ref() == 'vendor.oplus.hardware.engineer.IEngineer/default':
                hits.append(x)
    x = find_one(hits, 'OplusEngineerFwService waitForService')
    dex.d[x.off + 2:x.off + 4] = check.to_bytes(2, 'little')


def services_timeout_doze(dex):
    """PowerManagerServiceExtImpl.getOplusDozeAfterOff: timeout sleep must go to DOZE (AOD),
    not OFF -> compare mGotoSleepReasonWithAod with -8 (never true) instead of 2 (timeout)."""
    ins = dex.insns('Lcom/android/server/power/PowerManagerServiceExtImpl;', 'getOplusDozeAfterOff')
    hits = [ins[k + 1] for k, x in enumerate(ins[:-2]) if x.op == 0x52
            and x.ref().endswith('->mGotoSleepReasonWithAod:I')
            and ins[k + 1].op == 0x12 and ins[k + 1].b4 == 2 and ins[k + 2].op == 0x33]
    x = find_one(hits, 'getOplusDozeAfterOff timeout compare')
    dex.d[x.off + 1] = 0x80 | x.a4


VRR_CLASS = 'Lcom/oplus/vrr/OPlusExternalRefreshRateManager;'

VRR_METHODS = r'''
.method private isPortExtremeMode()Z
    .registers 5

    const/4 v0, 0x0

    :try_start_1
    iget-object v1, p0, Lcom/oplus/vrr/OPlusExternalRefreshRateManager;->mContext:Landroid/content/Context;

    invoke-virtual {v1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v1

    const-string v2, "oplus_customize_screen_refresh_rate"

    const/4 v3, 0x0

    invoke-static {v1, v2, v3}, Landroid/provider/Settings$Secure;->getInt(Landroid/content/ContentResolver;Ljava/lang/String;I)I

    move-result v1
    :try_end_f
    .catchall {:try_start_1 .. :try_end_f} :catchall_14

    const/16 v2, 0x8

    if-ne v1, v2, :cond_14

    const/4 v0, 0x1

    :catchall_14
    :cond_14
    return v0
.end method

.method private portCheckExtremeIdle()V
    .registers 5

    invoke-direct {p0}, Lcom/oplus/vrr/OPlusExternalRefreshRateManager;->isPortExtremeMode()Z

    move-result v0

    iget-boolean v1, p0, Lcom/oplus/vrr/OPlusExternalRefreshRateManager;->mPortExtremeIdle:Z

    if-eq v0, v1, :cond_1f

    iput-boolean v0, p0, Lcom/oplus/vrr/OPlusExternalRefreshRateManager;->mPortExtremeIdle:Z

    iget-object v1, p0, Lcom/oplus/vrr/OPlusExternalRefreshRateManager;->mHandler:Landroid/os/Handler;

    sget-object v2, Lcom/oplus/vrr/OPlusExternalRefreshRateManager$ExternalMsg;->TI_CONFIG:Lcom/oplus/vrr/OPlusExternalRefreshRateManager$ExternalMsg;

    iget v2, v2, Lcom/oplus/vrr/OPlusExternalRefreshRateManager$ExternalMsg;->mId:I

    invoke-virtual {v1, v2}, Landroid/os/Handler;->removeMessages(I)V

    const/4 v3, 0x0

    invoke-static {v3}, Ljava/lang/Boolean;->valueOf(Z)Ljava/lang/Boolean;

    move-result-object v3

    invoke-virtual {v1, v2, v3}, Landroid/os/Handler;->obtainMessage(ILjava/lang/Object;)Landroid/os/Message;

    move-result-object v3

    invoke-virtual {v3}, Landroid/os/Message;->sendToTarget()V

    :cond_1f
    return-void
.end method

.method private portIdleLowestRate(I)I
    .registers 4

    invoke-direct {p0}, Lcom/oplus/vrr/OPlusExternalRefreshRateManager;->isPortExtremeMode()Z

    move-result v0

    iput-boolean v0, p0, Lcom/oplus/vrr/OPlusExternalRefreshRateManager;->mPortExtremeIdle:Z

    if-eqz v0, :cond_d

    const/16 v1, 0x78

    if-ge p1, v1, :cond_d

    move p1, v1

    :cond_d
    return p1
.end method
'''


def _method_body(text, name):
    m = re.search(r'^\.method [^\n]* %s\([^\n]*\n.*?^\.end method' % re.escape(name), text, re.M | re.S)
    if not m:
        raise PatchError('smali method %s not found' % name)
    return m


def services_vrr_smali(smali_file):
    """165 Hz mode (Secure oplus_customize_screen_refresh_rate == 8): touch-idle lowest rate is
    clamped to 120 Hz; re-sent on every touch-idle state update so it follows mode switches."""
    s = open(smali_file, encoding='utf8').read()
    if 'portIdleLowestRate' in s:
        return
    for f in ('->mContext:Landroid/content/Context;', '->mHandler:Landroid/os/Handler;',
              'OPlusExternalRefreshRateManager$ExternalMsg;->TI_CONFIG:'):
        if f not in s:
            raise PatchError('reference %s missing' % f)
    # 1) clamp before TouchIdleBean.setLowestRate(vY) in handleTouchIdleConfig
    m = _method_body(s, 'handleTouchIdleConfig')
    body = m.group(0)
    calls = re.findall(r'^(\s*)invoke-virtual \{(v\d+|p\d+), (v\d+)\}, Lcom/oplus/vrr/bean/TouchIdleBean;->setLowestRate\(I\)V$', body, re.M)
    if len(calls) != 1:
        raise PatchError('setLowestRate call found %d times' % len(calls))
    ind, _, reg = calls[0]
    body = re.sub(r'^(\s*invoke-virtual \{(?:v\d+|p\d+), %s\}, Lcom/oplus/vrr/bean/TouchIdleBean;->setLowestRate\(I\)V)$' % reg,
                  '%sinvoke-direct {p0, %s}, %s->portIdleLowestRate(I)I\n\n%smove-result %s\n\n\\1' % (ind, reg, VRR_CLASS, ind, reg),
                  body, count=1, flags=re.M)
    s = s[:m.start()] + body + s[m.end():]
    # 2) re-check mode at the start of the synchronized block of handleTouchIdleState
    m = _method_body(s, 'handleTouchIdleState')
    body = m.group(0)
    mm = re.search(r'^([ \t]*)monitor-enter (v\d+)\n(?:[ \t]*(?:\.line \d+)?\n)*[ \t]*:try_start_\w+\n', body, re.M)
    if not mm:
        raise PatchError('handleTouchIdleState: monitor-enter/try_start not found')
    ins = '%sinvoke-direct {p0}, %s->portCheckExtremeIdle()V\n\n' % (mm.group(1), VRR_CLASS)
    body = body[:mm.end()] + ins + body[mm.end():]
    s = s[:m.start()] + body + s[m.end():]
    # 3) field + helper methods
    s = re.sub(r'^(\.field private mPdfrSwitch:Z)$', r'\1\n\n.field private mPortExtremeIdle:Z', s, count=1, flags=re.M) \
        if re.search(r'^\.field private mPdfrSwitch:Z$', s, re.M) else \
        re.sub(r'^(# instance fields)$', r'\1\n.field private mPortExtremeIdle:Z\n', s, count=1, flags=re.M)
    if 'mPortExtremeIdle:Z\n' not in s.split('# direct methods')[0]:
        raise PatchError('could not add field mPortExtremeIdle')
    s = s.rstrip('\n') + '\n' + VRR_METHODS
    open(smali_file, 'w', encoding='utf8').write(s)


IMS_EXT_CLASS = 'Lcom/android/server/input/InputManagerServiceExtImpl;'

TOUCH_SYNC_METHOD = r'''
.method private static portTouchRefreshSync(IF)V
    .registers 6

    if-nez p0, :cond_ret

    const/high16 v0, 0x43200000    # 160.0f

    cmpl-float v1, p1, v0

    if-ltz v1, :cond_144

    const-string v2, "165"

    goto :goto_write

    :cond_144
    const/high16 v0, 0x430c0000    # 140.0f

    cmpl-float v1, p1, v0

    if-ltz v1, :cond_default

    const-string v2, "144"

    goto :goto_write

    :cond_default
    const-string v2, "0"

    :goto_write
    sget-object v0, Lcom/android/server/input/InputManagerServiceExtImpl;->sPortTouchSync:Ljava/lang/String;

    invoke-virtual {v2, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-nez v1, :cond_ret

    sput-object v2, Lcom/android/server/input/InputManagerServiceExtImpl;->sPortTouchSync:Ljava/lang/String;

    :try_start_w
    invoke-static {}, Lcom/oplus/touchnode/OplusTouchNodeManager;->getInstance()Lcom/oplus/touchnode/OplusTouchNodeManager;

    move-result-object v0

    const/4 v1, 0x0

    const/16 v3, 0xf2

    invoke-virtual {v0, v1, v3, v2}, Lcom/oplus/touchnode/OplusTouchNodeManager;->writeNodeFileByDevice(IILjava/lang/String;)Z
    :try_end_w
    .catch Ljava/lang/Throwable; {:try_start_w .. :try_end_w} :catch_w

    :cond_ret
    return-void

    :catch_w
    move-exception v0

    return-void
.end method
'''


def services_touch_sync_smali(smali_file):
    """Touch HAL node 242 (refresh_rate) picks the refresh rate the touch IC report rate syncs to.
    Only COSA writes it, and only for games; otherwise the HAL syncs to 120 Hz, so in 165 Hz mode
    touch stayed at 120. On every display mode-spec change of display 0 write 165/144 when the
    render cap is >= 160/140 Hz, else 0 (HAL default 120 Hz sync, as stock)."""
    s = open(smali_file, encoding='utf8').read()
    if 'portTouchRefreshSync' in s:
        return
    if '->writeNodeFileByDevice(IILjava/lang/String;)Z' not in s:
        raise PatchError('OplusTouchNodeManager.writeNodeFileByDevice not referenced')
    m = _method_body(s, 'notifyDisplayModeSpecsChanged')
    body = m.group(0)
    if not body.startswith('.method public notifyDisplayModeSpecsChanged(IF)V'):
        raise PatchError('notifyDisplayModeSpecsChanged signature changed')
    mm = re.search(r'^([ \t]*)\.registers \d+\n(?:[ \t]*\.param [^\n]*\n|[ \t]*\n)*', body, re.M)
    if not mm:
        raise PatchError('notifyDisplayModeSpecsChanged: .registers not found')
    body = body[:mm.end()] + '    invoke-static {p1, p2}, %s->portTouchRefreshSync(IF)V\n\n' % IMS_EXT_CLASS + body[mm.end():]
    s = s[:m.start()] + body + s[m.end():]
    s, n = re.subn(r'^(# static fields)$', r'\1\n.field private static sPortTouchSync:Ljava/lang/String;\n', s, count=1, flags=re.M)
    if not n:
        raise PatchError('could not add field sPortTouchSync')
    s = s.rstrip('\n') + '\n' + TOUCH_SYNC_METHOD
    open(smali_file, 'w', encoding='utf8').write(s)


MELODY_DTO = 'Lcom/oplus/melody/common/data/WhitelistConfigDTO;'


def _is_brand_check(dex, off, units, brand):
    """Body is exactly `return "<brand>".equalsIgnoreCase(Build.BRAND)`."""
    ins = dex.insns_at(off, units)
    return [x.op for x in ins] == [0x1a, 0x62, 0x6e, 0x0a, 0x0f] and ins[0].ref() == brand \
        and ins[1].ref() == 'Landroid/os/Build;->BRAND:Ljava/lang/String;' \
        and ins[2].ref() == 'Ljava/lang/String;->equalsIgnoreCase(Ljava/lang/String;)Z'


def melody_realme_whitelist(dex, checks):
    """Melody (earbuds app): keep realme earbuds in the model whitelist on a non-realme phone.
    The app ships one whitelist for OPPO, OnePlus and realme models (realme Buds Air6 Pro etc.), but
    while loading it drops every entry whose brand is "realme" unless Build.BRAND is realme:
        if (!isRealmePhone && "realme".equalsIgnoreCase(dto.getBrand())) continue;
    Without the entry Melody ignores realme earbuds completely (log: findWhitelistConfigByDevice
    NOT_FOUND). With it the earbuds get their Melody page in Bluetooth settings (verified 2026-11-08 with
    realme Buds Air6 Pro). Product images, EQ layout and the case-open popup images come from Melody's
    server, which answers 404 for realme models on this phone, so those stay generic or absent. The `if-nez isRealmePhone` becomes an unconditional goto (same size).
    Class names are obfuscated and change with every Melody build, so the site is found by shape;
    `checks` = signatures of the isRealmePhone method (it may sit in another dex)."""
    getmin = dex.method_index(MELODY_DTO + '->getMinVersion()I')
    getbrand = dex.method_index(MELODY_DTO + '->getBrand()Ljava/lang/String;')
    if getmin is None or getbrand is None:
        return False
    sites = []
    needle = struct.pack('<H', getmin)
    for sig, off, n in dex.methods(None):
        if needle not in dex.d[off:off + 2 * n]:
            continue
        ins = dex.insns_at(off, n)
        for k in range(len(ins) - 4):
            x = ins[k]
            if x.op != 0x39 or ins[k + 1].op != 0x6e or ins[k + 1].ref() != dex.method(getbrand) \
                    or ins[k + 3].op != 0x1a or ins[k + 3].ref() != 'realme':
                continue
            src = [j for j in range(k) if ins[j].op == 0x71 and ins[j].ref() in checks
                   and ins[j + 1].op == 0x0a and ins[j + 1].aa == x.aa]
            if src and not any(x.aa in dest_regs(y) for y in ins[src[-1] + 2:k]):
                sites.append(x)
    if not sites:
        return False
    x = find_one(sites, 'Melody whitelist realme filter')
    dex.d[x.off] = 0x29          # if-nez vAA, +off  ->  goto/16 +off  (both 2 code units)
    dex.d[x.off + 1] = 0
    return True


# ------------------------------------------------------------------ drivers

def patch_melody(apk, log, version_code=None):
    z = ZipFile(apk)
    checks = set()
    for n in z.entries:
        if n.startswith('classes') and n.endswith('.dex'):
            dex = Dex(z.read(n))
            checks |= {sig for sig, off, u in dex.methods(None) if u == 9 and _is_brand_check(dex, off, u, 'realme')}
    if len(checks) != 1:
        raise PatchError('Melody: isRealmePhone method found %d times (expected 1)' % len(checks))
    patch_any_dex_in_zip(apk, lambda dex: melody_realme_whitelist(dex, checks), 'Melody realme whitelist')
    log('Melody: realme earbuds kept in the model whitelist (recognised, Bluetooth device page)')
    if version_code:
        old = set_xml_int_attr(apk, 'AndroidManifest.xml', 'manifest', 0x0101021b, version_code)
        log('Melody: versionCode %d -> %d (a Play Store update would replace the patched app)' % (old, version_code))


def patch_settings(apk, banner_text, log):
    patch_dex_in_zip(apk, 'Lcom/oplus/settings/feature/deviceinfo/controller/OtaUpdateController;',
                     settings_about_banner, 'about banner')
    log('Settings: About-device ColorOS banner available without OTA app')
    patch_dex_in_zip(apk, 'Lcom/oplus/settings/feature/homepage/messageentry/MessageEntryUtils;',
                     settings_hide_quick_glance, 'quick glance')
    log('Settings: Quick glance card disabled')
    patch_dex_in_zip(apk, 'Lcom/oplus/settings/feature/othersettings/controller/SoftwareUpdatePreferenceController;',
                     settings_hide_software_update_row, 'software update row')
    log('Settings: Software update row hidden')
    # C.80+ made the 'up to date' label (id update_text) a plain COUITextView; C.75 had it as the
    # translucent pill COUIButton. Rebuild it from the sibling 'find newer' pill (id update_find):
    # keep its own id/visibility/marginTop/text, drop the arrow drawableEnd.
    for lay in ('res/layout/about_device_ota_item.xml', 'res/layout/about_device_ota_item_phone.xml'):
        if lay in ZipFile(apk).entries:
            log('Settings: banner pill %s: %s' % (lay.split('/')[-1], restyle_xml_element_like(
                apk, lay, 0x7f0b1071, 0x7f0b1070, keep=(0x010100dc, 0x010100f8, 0x0101014f),
                drop=(0x01010393,))))
    if banner_text:
        log('Settings: banner pill text: ' + patch_arsc_string(apk, 'string', 'about_phone_already_last_version', banner_text))


def patch_systemui(apk, log):
    patch_dex_in_zip(apk, 'Lcom/oplus/systemui/aod/display/SmoothTransitionController;',
                     systemui_seamless_aod, 'seamless aod')
    log('SystemUI: Seamless AOD enabled')
    patch_dex_in_zip(apk, 'Lcom/oplus/systemui/keyguard/OplusKeyguardViewMediatorExImpl;',
                     systemui_timeout_aod, 'timeout aod')
    log('SystemUI: screen-timeout AOD like power button')
    # carrier label on lock screen was ~2 px low: paddingBottom 1.3359dip (4 px) on its RelativeLayout
    r = insert_xml_attr(apk, 'res/layout/keyguard_status_bar.xml', 'RelativeLayout', 0x010103b7,
                        0x010100d9, 0x05, 0xab11)
    log('SystemUI: lock-screen carrier label alignment ' + r)


def patch_services_jar(jar, tools, work, log):
    """Binary patches in place, then the smali patch (needs a dex rebuild) on the VRR class."""
    patch_dex_in_zip(jar, 'Lcom/android/server/engineering/OplusEngineerFwService;',
                     services_engineer_checkservice, 'engineer checkService')
    log('oplus-services: engineer HAL lookup no longer blocks (checkService)')
    patch_dex_in_zip(jar, 'Lcom/android/server/power/PowerManagerServiceExtImpl;',
                     services_timeout_doze, 'timeout doze')
    log('oplus-services: screen timeout dozes into AOD')

    targets = smali_patch_jar(jar, tools, work, {VRR_CLASS: services_vrr_smali,
                                                  IMS_EXT_CLASS: services_touch_sync_smali})
    log('oplus-services: 165 Hz mode idles at 120 Hz (%s rebuilt with smali)' % targets[VRR_CLASS])
    log('oplus-services: touch panel refresh sync follows 144/165 Hz (%s rebuilt with smali)' % targets[IMS_EXT_CLASS])


def smali_patch_jar(jar, tools, work, patchers):
    """Disassemble the dex holding each class, run its smali patcher, reassemble, rebuild the jar.
    Returns {class: dex name}."""
    z = ZipFile(jar)
    where = {}
    for n in sorted(z.entries):
        if n.startswith('classes') and n.endswith('.dex'):
            d = Dex(z.read(n))
            for cls in patchers:
                if d.has_class(cls):
                    where[cls] = n
    for cls in patchers:
        if cls not in where:
            raise PatchError('%s not found in %s' % (cls, os.path.basename(jar)))
    tmp = tempfile.mkdtemp(dir=work)
    replace = {}
    try:
        for target in sorted(set(where.values())):
            dexf = os.path.join(tmp, target)
            open(dexf, 'wb').write(z.read(target))
            out = os.path.join(tmp, 'smali_' + target)
            subprocess.run(['java', '-jar', tools['baksmali'], 'd', '-j', '8', '-o', out, dexf],
                           check=True, stdout=subprocess.DEVNULL)
            for cls, fn in patchers.items():
                if where[cls] == target:
                    fn(os.path.join(out, cls[1:-1] + '.smali'))
            newdex = os.path.join(tmp, 'new_' + target)
            subprocess.run(['java', '-jar', tools['smali'], 'a', '--api', '28', '-j', '1', '-o', newdex, out],
                           check=True, stdout=subprocess.DEVNULL)
            replace[target] = open(newdex, 'rb').read()
        rebuild_jar(jar, replace)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return where


def rebuild_jar(jar, replace, add=()):
    """Rewrite a jar with some entries replaced and `add` [(name, data)] appended; dex entries stored and
    4-byte aligned."""
    src = zipfile.ZipFile(jar)
    items = [(i, replace.get(i.filename, None) or src.read(i.filename)) for i in src.infolist()]
    src.close()
    for name, data in add:
        if any(i.filename == name for i, _ in items):
            raise PatchError('%s already in %s' % (name, os.path.basename(jar)))
        ref = next(i for i, _ in items if i.filename == 'classes.dex')
        zi = zipfile.ZipInfo(name, ref.date_time)
        zi.external_attr = ref.external_attr
        items.append((zi, data))
    tmp = jar + '.new'
    with zipfile.ZipFile(tmp, 'w') as out:
        for info, data in items:
            zi = zipfile.ZipInfo(info.filename, info.date_time)
            zi.external_attr = info.external_attr
            zi.compress_type = zipfile.ZIP_STORED if info.filename.endswith('.dex') else info.compress_type
            if zi.compress_type == zipfile.ZIP_STORED:
                off = out.fp.tell() + 30 + len(info.filename.encode())
                zi.extra = b'\0' * ((4 - off % 4) % 4)
            out.writestr(zi, data)
    os.replace(tmp, jar)
