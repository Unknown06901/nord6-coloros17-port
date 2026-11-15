"""ColorOS 17 radio subsystem <-> Nord 6 odm subsys_daemon: AIDL transaction-code remap.

The donor's system_ext subsystem jars (vendor-subsystem-service, oplus-subsystem-service,
oplus-subsystem-service-ext; each carries its own copy of the generated classes) talk to
vendor.oplus.hardware.subsys_interface.subsys_radio.ISubsysRadio with stubs generated from the
donor's re-baselined interface (V1). The base odm HAL is V9. Method numbering differs for almost
every call, so the HAL ran a different function than the one requested (setCallback ran readNv,
so every response was dropped and com.oplus.subsys hit "consecutive timeouts"; other calls landed
on modem setters). Shared methods keep identical signatures and parcelable layouts, so renumbering
is enough:
  - ISubsysRadio$Stub$Proxy: each transact() uses the base code of the same method name, or
    UNSUPPORTED (base answers UNKNOWN_TRANSACTION -> RemoteException "Unimplemented").
  - ISubsysRadioResponse$Stub / ISubsysRadioIndication$Stub: incoming base codes are translated
    to the donor's codes at the top of onTransact() (portMapCode).
Both code tables are read from the base and donor jars at build time.
"""
import os
import re
import shutil
import subprocess
import tempfile

from dexpatch import PatchError, Dex, ZipFile

PK = 'vendor/oplus/hardware/subsys_interface/subsys_radio/'
IFACES = ('ISubsysRadio', 'ISubsysRadioResponse', 'ISubsysRadioIndication')
JARS = ('vendor-subsystem-service', 'oplus-subsystem-service', 'oplus-subsystem-service-ext')
UNSUPPORTED = 0x7ffe
SPECIAL = 0xfffff0      # getInterfaceVersion/Hash and binder meta codes pass through


def _read(root, cls):
    p = os.path.join(root, PK + cls + '.smali')
    return open(p, encoding='utf8').read() if os.path.exists(p) else None


def interface_hash(root):
    m = re.search(r'HASH:Ljava/lang/String; = "([0-9a-f]+)"', _read(root, 'ISubsysRadio') or '')
    return m.group(1) if m else None


def code_names(root, iface):
    """name -> transaction code, from Stub.getDefaultTransactionName."""
    s = _read(root, iface + '$Stub')
    m = re.search(r'\.method public static getDefaultTransactionName\(I\).*?\.end method', s or '', re.S)
    if not m:
        raise PatchError('%s$Stub.getDefaultTransactionName not found' % iface)
    lines = m.group(0).split('\n')
    labels = {}
    for i, l in enumerate(lines):
        if l.strip().startswith(':'):
            labels.setdefault(l.strip(), i)
    codes = {}
    for sw in re.finditer(r'\.packed-switch (-?0x[0-9a-f]+)\n(.*?)\.end packed-switch', m.group(0), re.S):
        b = int(sw.group(1), 16)
        for k, lab in enumerate(re.findall(r':\w+', sw.group(2))):
            codes[b + k] = lab
    for sw in re.finditer(r'\.sparse-switch\n(.*?)\.end sparse-switch', m.group(0), re.S):
        for v, lab in re.findall(r'(-?0x[0-9a-f]+) -> (:\w+)', sw.group(1)):
            codes[int(v, 16)] = lab
    out = {}
    for c, lab in codes.items():
        for l in lines[labels[lab]:]:
            mm = re.search(r'const-string(?:/jumbo)? \w+, "(\w+)"', l)
            if mm:
                out[mm.group(1)] = c
                break
    return {n: c for n, c in out.items() if c < SPECIAL}


def _signatures(root, iface):
    return dict(re.findall(r'\.method public abstract (\w+)(\(.*?\)\S+)', _read(root, iface)))


def _layout(root, cls):
    s = _read(root, cls)
    if s is None:
        return None
    if os.path.exists(os.path.join(root, PK + cls + '$Stub.smali')):
        return 'binder'                        # callback interface: renumbered separately
    m = re.search(r'\.method public (?:final )?writeToParcel\(Landroid/os/Parcel;I\)V.*?\.end method', s, re.S)
    if not m:
        return s                               # enum/const holder: must be identical
    return tuple(re.findall(r'iget[\w-]* \w+, \w+, L[\w/$]+;->(\w+:\S+)', m.group(0)))


def _types(desc):
    return re.findall(r'L(' + re.escape(PK) + r'([\w$]+));', desc)


def _compatible(base, port, cls, memo, seen=()):
    if cls in memo:
        return memo[cls]
    if cls in seen:
        return True
    lb, lp = _layout(base, cls), _layout(port, cls)
    if lb is None or lp is None:
        ok = False
    elif isinstance(lb, tuple) and isinstance(lp, tuple):
        ok = lp[:len(lb)] == lb or lb[:len(lp)] == lp      # equal or append-only extension
        for f in set(lb) & set(lp) if ok else ():
            ok = ok and all(_compatible(base, port, t, memo, seen + (cls,)) for _, t in _types(f.split(':', 1)[1]))
    else:
        ok = lb == lp
    memo[cls] = ok
    return ok


def build_tables(base, port):
    """-> {iface: [(name, port_code, base_code_or_None)]}; raises if a shared method is incompatible."""
    memo, tables, bad = {}, {}, []
    for iface in IFACES:
        nb, np_ = code_names(base, iface), code_names(port, iface)
        sb, sp = _signatures(base, iface), _signatures(port, iface)
        rows = []
        for name, pc in sorted(np_.items(), key=lambda x: x[1]):
            if name not in nb:
                rows.append((name, pc, None))
                continue
            if sb.get(name) != sp.get(name) or not all(_compatible(base, port, t, memo) for _, t in _types(sp[name])):
                bad.append('%s.%s' % (iface, name))
                rows.append((name, pc, None))
                continue
            rows.append((name, pc, nb[name]))
        tables[iface] = rows
    if bad:
        raise PatchError('subsys_radio methods differ between base and donor: ' + ', '.join(bad[:10]))
    return tables


def _param_words(sig):
    n, i = 0, 0
    while i < len(sig):
        c = sig[i]
        if c == '[':
            while sig[i] == '[':
                i += 1
            if sig[i] == 'L':
                i = sig.index(';', i)
            n += 1
        elif c == 'L':
            i = sig.index(';', i)
            n += 1
        else:
            n += 2 if c in 'JD' else 1
        i += 1
    return n


TRANSACT = re.compile(r'invoke-interface \{(\w+), (\w+), (\w+), (\w+), (\w+)\}, Landroid/os/IBinder;->transact')


def _patch_proxy(root, rows):
    path = os.path.join(root, PK + 'ISubsysRadio$Stub$Proxy.smali')
    s = open(path, encoding='utf8').read()
    want = {n: (pc, bc) for n, pc, bc in rows}
    out, pos, done = [], 0, set()
    for m in re.finditer(r'(\.method public (\w+)\((.*?)\)\S+\n)(.*?)(\.end method)', s, re.S):
        name, sig, body = m.group(2), m.group(3), m.group(4)
        t = TRANSACT.search(body)
        if not t or name.startswith('getInterface'):
            continue
        if name not in want:
            raise PatchError('ISubsysRadio proxy method %s has no transaction name' % name)
        pc, bc = want[name]
        consts = re.findall(r'const(?:/4|/16)? ' + t.group(2) + r', (0x[0-9a-f]+)', body[:t.start()])
        if not consts or int(consts[-1], 16) != pc:
            raise PatchError('ISubsysRadio proxy %s: transact code is not %d' % (name, pc))
        nregs = int(re.search(r'\.registers (\d+)', body).group(1))
        k = nregs - 1 - _param_words(sig)          # new local right after the existing ones
        if k > 15:
            raise PatchError('ISubsysRadio proxy %s: no 4-bit register free' % name)
        body = body.replace('.registers %d' % nregs, '.registers %d' % (nregs + 1), 1)
        t = TRANSACT.search(body)
        body = (body[:t.start()] + 'const/16 v%d, 0x%x\n\n    ' % (k, UNSUPPORTED if bc is None else bc)
                + 'invoke-interface {%s, v%d, %s, %s, %s}, Landroid/os/IBinder;->transact'
                % (t.group(1), k, t.group(3), t.group(4), t.group(5)) + body[t.end():])
        out += [s[pos:m.start(4)], body]
        pos = m.end(4)
        done.add(name)
    if done != set(want):
        raise PatchError('ISubsysRadio proxy: %d calls not found' % len(set(want) - done))
    open(path, 'w', encoding='utf8').write(''.join(out) + s[pos:])
    return len(done)


def _patch_stub(root, iface, rows):
    cls = PK + iface + '$Stub'
    path = os.path.join(root, cls + '.smali')
    s = open(path, encoding='utf8').read()
    m = re.search(r'\.method public onTransact\(ILandroid/os/Parcel;Landroid/os/Parcel;I\)Z\n(.*?)\.end method', s, re.S)
    if not m or 'portMapCode' in s:
        raise PatchError('%s.onTransact not found or already patched' % iface)
    body = m.group(1)
    a = body.index('.end annotation\n') + len('.end annotation\n')
    body = body[:a] + '\n    invoke-static {p1}, L%s;->portMapCode(I)I\n\n    move-result p1\n' % cls + body[a:]
    table = sorted((bc, pc) for _, pc, bc in rows if bc is not None)
    cases = ''.join('\n    :pm_%d\n    const/16 v0, 0x%x\n\n    return v0\n' % (i, pc) for i, (bc, pc) in enumerate(table))
    switch = ''.join('\n        0x%x -> :pm_%d' % (bc, i) for i, (bc, pc) in enumerate(table))
    meth = ('\n.method private static portMapCode(I)I\n    .registers 2\n\n'
            '    sparse-switch p0, :pm_switch\n\n    const v0, 0x%x\n\n    if-lt p0, v0, :pm_unknown\n\n'
            '    return p0\n\n    :pm_unknown\n    const/16 v0, 0x%x\n\n    return v0\n%s\n'
            '    :pm_switch\n    .sparse-switch%s\n    .end sparse-switch\n.end method\n') % (SPECIAL, UNSUPPORTED, cases, switch)
    open(path, 'w', encoding='utf8').write(s[:m.start(1)] + body + s[m.end(1):] + meth)
    return len(table)


def _disassemble(jar, tools, out):
    """baksmali the dex of `jar` that defines ISubsysRadio -> (dex entry name, smali dir)."""
    z = ZipFile(jar)
    for n in sorted(z.entries):
        if n.startswith('classes') and n.endswith('.dex') and Dex(z.read(n)).has_class('L%sISubsysRadio;' % PK):
            dexf = os.path.join(out, n)
            open(dexf, 'wb').write(z.read(n))
            subprocess.run(['java', '-jar', tools['baksmali'], 'd', '-j', '8', '-o', os.path.join(out, 'smali'), dexf],
                           check=True, stdout=subprocess.DEVNULL)
            return n, os.path.join(out, 'smali')
    return None, None


def patch_subsys_jars(framework_dir, base_jar, tools, work, log, rebuild_jar):
    """Renumber the subsys_radio AIDL calls of the donor subsystem jars to the base HAL version.
    Returns the list of patched jar names."""
    tmp = tempfile.mkdtemp(dir=work)
    try:
        os.makedirs(os.path.join(tmp, 'base'))
        _, base = _disassemble(base_jar, tools, os.path.join(tmp, 'base'))
        if base is None:
            raise PatchError('base %s has no ISubsysRadio' % os.path.basename(base_jar))
        bh = interface_hash(base)
        patched, tables = [], None
        for name in JARS:
            jar = os.path.join(framework_dir, name + '.jar')
            if not os.path.exists(jar):
                raise PatchError('donor %s.jar missing' % name)
            d = os.path.join(tmp, name)
            os.makedirs(d)
            entry, port = _disassemble(jar, tools, d)
            if port is None:
                continue
            ph = interface_hash(port)
            if ph == bh:
                log('%s: subsys_radio interface already matches base (%s), unchanged' % (name, bh[:8]))
                continue
            if tables is None:
                tables = build_tables(base, port)
                r = tables['ISubsysRadio']
                log('subsys_radio: donor %s vs base %s, %d of %d shared calls had other codes, %d donor-only'
                    % (ph[:8], bh[:8], sum(1 for _, pc, bc in r if bc is not None and pc != bc),
                       sum(1 for _, _, bc in r if bc is not None), sum(1 for _, _, bc in r if bc is None)))
            _patch_proxy(port, tables['ISubsysRadio'])
            for iface in IFACES[1:]:
                _patch_stub(port, iface, tables[iface])
            newdex = os.path.join(d, 'new.dex')
            subprocess.run(['java', '-jar', tools['smali'], 'a', '--api', '28', '-j', '1', '-o', newdex, port],
                           check=True, stdout=subprocess.DEVNULL)
            rebuild_jar(jar, {entry: open(newdex, 'rb').read()})
            patched.append(name)
            log('%s.jar: subsys_radio calls renumbered to base HAL codes (%s rebuilt with smali)' % (name, entry))
        return patched
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
