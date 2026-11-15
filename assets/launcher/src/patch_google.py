# Zuyqa OplusLauncher 17.3.9: "Home screen search button" Breeno option -> Google.
#  - IndicatorEntry$Companion.getIndicatorAppLaunchIntent: Breeno (com.heytap.speechassist, not in
#    the port) -> android.search.action.GLOBAL_SEARCH in com.google.android.googlequicksearchbox
#  - resources.arsc global string pool: "Breeno" (launcher_bottom_button_breeno /
#    page_indicator_breeno_menu_title) -> "Google", "Ask anything" (breeno_entry_text) -> "Ask Google"
#  - res/xml/launcher_settings.xml + zuyqa_feature_settings.xml: the "(Powered By) ZuyQA \nTranslated By
#    ArticPorts" category titles -> ""
#  - AndroidManifest.xml versionName "17.3.9-Powered By Zuyqa" -> "17.3.9"
import os, re, shutil, struct, subprocess, sys, tempfile
KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
sys.path.insert(0, os.path.join(KIT, 'lib'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apkswap import replace_entries
from zipfile import ZipFile
TOOLS = os.path.join(KIT, 'tools')
CLS = 'com/android/launcher3/search/IndicatorEntry$Companion.smali'

def patch_smali(root):
    p = os.path.join(root, CLS); s = open(p, encoding='utf-8').read()
    a = s.index('.method public static getIndicatorAppLaunchIntent(')
    b = s.index('.end method', a)
    m = s[a:b]
    for old, new in (('const-string/jumbo v0, "heytap.intent.action.NEW_AI_CHAT_HOME_ENTRANCE"',
                      'const-string v0, "android.search.action.GLOBAL_SEARCH"'),
                     ('const-string v0, "com.heytap.speechassist"',
                      'const-string v0, "com.google.android.googlequicksearchbox"')):
        assert m.count(old) == 1, old
        m = m.replace(old, new)
    open(p, 'w', encoding='utf-8').write(s[:a] + m + s[b:])

def _len8(buf, o):
    n = buf[o]
    return ((n & 0x7f) << 8 | buf[o + 1], 2) if n & 0x80 else (n, 1)

def patch_arsc(data, repl, o=12):
    # o = offset of the string pool: 12 in resources.arsc (after ResTable header), 8 in binary xml
    buf = bytearray(data)
    typ, hsz, size, cnt, scnt, flags, sstart, _ = struct.unpack_from('<HHIIIIII', buf, o)
    assert typ == 1 and flags & 0x100, 'global pool not UTF-8'
    offs = struct.unpack_from('<%dI' % cnt, buf, o + hsz)
    done = {}
    for i, off in enumerate(offs):
        p = o + sstart + off
        cl, a = _len8(buf, p); bl, b = _len8(buf, p + a)
        t = bytes(buf[p + a + b:p + a + b + bl]).decode('utf-8', 'replace')
        if t in repl:
            new = repl[t].encode()
            assert len(new) <= bl and len(new) < 128
            if a == 2 or b == 2:      # 2-byte length fields: rewrite as 1-byte + shift text
                assert a == 2 and b == 2
                buf[p:p + 4 + bl + 1] = bytes([len(repl[t]), len(new)]) + new + b'\0' * (bl + 3 - len(new))
                done[t] = done.get(t, 0) + 1
                continue
            buf[p] = len(repl[t]); buf[p + 1] = len(new)
            buf[p + 2:p + 2 + bl + 1] = new + b'\0' * (bl + 1 - len(new))
            done[t] = done.get(t, 0) + 1
    assert set(done) == set(repl) and all(v == 1 for v in done.values()), done
    return bytes(buf)

def patch_xml16(data, repl):
    # binary xml with a UTF-16 string pool (AndroidManifest.xml): shorten strings in place
    buf = bytearray(data)
    o = 8
    typ, hsz, size, cnt, scnt, flags, sstart, _ = struct.unpack_from('<HHIIIIII', buf, o)
    assert typ == 1 and not flags & 0x100
    offs = struct.unpack_from('<%dI' % cnt, buf, o + hsz)
    done = 0
    for off in offs:
        p = o + sstart + off
        n, = struct.unpack_from('<H', buf, p)
        assert not n & 0x8000
        t = bytes(buf[p + 2:p + 2 + 2 * n]).decode('utf-16-le')
        if t in repl:
            new = repl[t]
            assert len(new) <= n
            struct.pack_into('<H', buf, p, len(new))
            buf[p + 2:p + 2 + 2 * n + 2] = new.encode('utf-16-le') + b'\0' * (2 * (n - len(new)) + 2)
            done += 1
    assert done == len(repl), done
    return bytes(buf)

def main(src, dst):
    shutil.copy(src, dst)
    z = ZipFile(dst)
    tmp = tempfile.mkdtemp(dir=os.path.dirname(os.path.abspath(dst)))
    try:
        open(os.path.join(tmp, 'classes.dex'), 'wb').write(z.read('classes.dex'))
        sm = os.path.join(tmp, 'sm')
        subprocess.run(['java', '-jar', TOOLS + '/baksmali-2.5.2.jar', 'd', '-j', '8', '-o', sm, os.path.join(tmp, 'classes.dex')], check=True)
        patch_smali(sm)
        nd = os.path.join(tmp, 'new.dex')
        subprocess.run(['java', '-jar', TOOLS + '/smali-2.5.2.jar', 'a', '--api', '35', '-j', '1', '-o', nd, sm], check=True)
        arsc = patch_arsc(z.read('resources.arsc'), {'Breeno': 'Google', 'Ask anything': 'Ask Google'})
        xml = patch_arsc(z.read('res/xml/launcher_settings.xml'), {'ZuyQA \nTranslated By ArticPorts': ''}, 8)
        xml2 = patch_arsc(z.read('res/xml/zuyqa_feature_settings.xml'), {'Powered By ZuyQA \nTranslated By ArticPorts': ''}, 8)
        man = patch_xml16(z.read('AndroidManifest.xml'), {'17.3.9-Powered By Zuyqa': '17.3.9'})
        z.close()
        replace_entries(dst, {'AndroidManifest.xml': man, 'classes.dex': open(nd, 'rb').read(), 'resources.arsc': arsc,
                              'res/xml/launcher_settings.xml': xml, 'res/xml/zuyqa_feature_settings.xml': xml2})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
    print('ok')
