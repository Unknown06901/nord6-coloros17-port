# Same-size bytecode / resource patching inside APK and JAR files.
#
# Patch sites are located by class + method + instruction pattern (string, field
# and method references are resolved), never by fixed file offsets, so the same
# patch keeps working on a newer donor build as long as the code shape is unchanged.
# When a pattern is not found exactly once a PatchError is raised and nothing is written.
import hashlib
import struct
import zlib


class PatchError(Exception):
    pass


# ---------------------------------------------------------------- zip (stored entries)

class ZipFile:
    """In-place access to a zip whose entries we only rewrite with the same size."""

    def __init__(self, path):
        self.path = path
        self.a = bytearray(open(path, 'rb').read())
        e = self.a.rfind(b'PK\x05\x06')
        n, = struct.unpack_from('<H', self.a, e + 10)
        o, = struct.unpack_from('<I', self.a, e + 16)
        self.cd_off = o
        self.entries = {}
        for _ in range(n):
            flg, meth = struct.unpack_from('<HH', self.a, o + 8)
            csz, usz = struct.unpack_from('<II', self.a, o + 20)
            fl, el, cl = struct.unpack_from('<HHH', self.a, o + 28)
            lho, = struct.unpack_from('<I', self.a, o + 42)
            name = self.a[o + 46:o + 46 + fl].decode()
            self.entries[name] = dict(cd=o, flg=flg, meth=meth, csz=csz, usz=usz, lho=lho, name=name)
            o += 46 + fl + el + cl

    def data_range(self, name):
        t = self.entries[name]
        lfl, lel = struct.unpack_from('<HH', self.a, t['lho'] + 26)
        ds = t['lho'] + 30 + lfl + lel
        return ds, ds + t['csz']

    def read(self, name):
        t = self.entries[name]
        ds, de = self.data_range(name)
        raw = bytes(self.a[ds:de])
        return raw if t['meth'] == 0 else zlib.decompress(raw, -15)

    def write_stored(self, name, data):
        t = self.entries[name]
        if t['meth'] != 0:
            raise PatchError('%s: entry %s is compressed, same-size patch impossible' % (self.path, name))
        ds, de = self.data_range(name)
        if len(data) != de - ds:
            raise PatchError('size changed for ' + name)
        self.a[ds:de] = data
        crc = zlib.crc32(data) & 0xffffffff
        struct.pack_into('<I', self.a, t['cd'] + 16, crc)
        if t['flg'] & 8:
            p = de + (4 if self.a[de:de + 4] == b'PK\x07\x08' else 0)
            struct.pack_into('<I', self.a, p, crc)
        if struct.unpack_from('<I', self.a, t['lho'] + 14)[0] or not t['flg'] & 8:
            struct.pack_into('<I', self.a, t['lho'] + 14, crc)

    def save(self, path=None):
        open(path or self.path, 'wb').write(self.a)


# ---------------------------------------------------------------- dex

# instruction size in 16-bit code units, by opcode
_SIZE = [1] * 256
for _r, _n in (((0x02, 0x05, 0x08), 2), ((0x03, 0x06, 0x09), 3), ((0x13, 0x15, 0x16, 0x19), 2),
               ((0x14, 0x17), 3), ((0x18,), 5), ((0x1a, 0x1c, 0x1f, 0x20, 0x22, 0x23), 2),
               ((0x1b, 0x24, 0x25, 0x26, 0x2a, 0x2b, 0x2c), 3), ((0x29,), 2),
               ((0xfa, 0xfb), 4), ((0xfc, 0xfd), 3), ((0xfe, 0xff), 2)):
    for _o in _r:
        _SIZE[_o] = _n
for _o in list(range(0x2d, 0x3e)) + list(range(0x44, 0x6e)) + list(range(0x90, 0xb0)) + list(range(0xd0, 0xe3)):
    _SIZE[_o] = 2
for _o in list(range(0x6e, 0x73)) + list(range(0x74, 0x79)):
    _SIZE[_o] = 3

STRING_OPS = (0x1a, 0x1b)
FIELD_OPS = range(0x52, 0x6e)
METHOD_OPS = tuple(range(0x6e, 0x73)) + tuple(range(0x74, 0x79))


class Insn:
    def __init__(self, dex, off, addr):
        self.dex, self.off, self.addr = dex, off, addr
        d = dex.d
        self.op = d[off]
        if self.op == 0 and d[off + 1] in (1, 2, 3):          # switch / array payloads
            kind = d[off + 1]
            if kind == 1:
                self.size = struct.unpack_from('<H', d, off + 2)[0] * 2 + 4
            elif kind == 2:
                self.size = struct.unpack_from('<H', d, off + 2)[0] * 4 + 2
            else:
                w, = struct.unpack_from('<H', d, off + 2)
                cnt, = struct.unpack_from('<I', d, off + 4)
                self.size = (w * cnt + 1) // 2 + 4
            self.payload = True
        else:
            self.size = _SIZE[self.op]
            self.payload = False

    @property
    def raw(self):
        return bytes(self.dex.d[self.off:self.off + 2 * self.size])

    @property
    def a4(self):
        return self.dex.d[self.off + 1] & 0xf

    @property
    def b4(self):
        return self.dex.d[self.off + 1] >> 4

    @property
    def aa(self):
        return self.dex.d[self.off + 1]

    def ref(self):
        """Resolved string / field / method reference of this instruction, or None."""
        d = self.dex
        if self.op == 0x1a:
            return d.string(struct.unpack_from('<H', d.d, self.off + 2)[0])
        if self.op == 0x1b:
            return d.string(struct.unpack_from('<I', d.d, self.off + 2)[0])
        if self.op in FIELD_OPS:
            return d.field(struct.unpack_from('<H', d.d, self.off + 2)[0])
        if self.op in METHOD_OPS:
            return d.method(struct.unpack_from('<H', d.d, self.off + 2)[0])
        return None

    def __repr__(self):
        return '@%x op=%02x %s' % (self.addr, self.op, self.ref() or '')


class Dex:
    def __init__(self, data):
        self.d = bytearray(data)
        if self.d[:4] != b'dex\n':
            raise PatchError('not a dex')
        (self.sid_sz, self.sid_off, self.tid_sz, self.tid_off, self.pid_sz, self.pid_off,
         self.fid_sz, self.fid_off, self.mid_sz, self.mid_off, self.cd_sz, self.cd_off) = struct.unpack_from('<12I', self.d, 56)
        self._s = {}

    def _uleb(self, p):
        r = s = 0
        while True:
            b = self.d[p]
            p += 1
            r |= (b & 0x7f) << s
            s += 7
            if b < 0x80:
                return r, p

    def string(self, i):
        if i not in self._s:
            o, = struct.unpack_from('<I', self.d, self.sid_off + 4 * i)
            _, o = self._uleb(o)
            self._s[i] = self.d[o:self.d.index(b'\0', o)].decode('utf8', 'replace')
        return self._s[i]

    def type(self, i):
        return self.string(struct.unpack_from('<I', self.d, self.tid_off + 4 * i)[0])

    def proto(self, i):
        _, ret, params = struct.unpack_from('<III', self.d, self.pid_off + 12 * i)
        ps = ''
        if params:
            n, = struct.unpack_from('<I', self.d, params)
            ps = ''.join(self.type(struct.unpack_from('<H', self.d, params + 4 + 2 * k)[0]) for k in range(n))
        return '(%s)%s' % (ps, self.type(ret))

    def field(self, i):
        c, t, n = struct.unpack_from('<HHI', self.d, self.fid_off + 8 * i)
        return '%s->%s:%s' % (self.type(c), self.string(n), self.type(t))

    def method(self, i):
        c, p, n = struct.unpack_from('<HHI', self.d, self.mid_off + 8 * i)
        return '%s->%s%s' % (self.type(c), self.string(n), self.proto(p))

    def method_index(self, sig):
        for i in range(self.mid_sz):
            if self.method(i) == sig:
                return i
        return None

    def has_class(self, cls):
        return any(self.type(struct.unpack_from('<I', self.d, self.cd_off + 32 * c)[0]) == cls for c in range(self.cd_sz))

    def methods(self, cls, name=None):
        """[(signature, insns_offset, insns_units)] for methods `name` (all if None) of class `cls`
        (every class if `cls` is None, for obfuscated apps whose class names change between builds)."""
        out = []
        for c in range(self.cd_sz):
            ci, _, _, _, _, _, cdata, _ = struct.unpack_from('<8I', self.d, self.cd_off + 32 * c)
            if not cdata or (cls is not None and self.type(ci) != cls):
                continue
            p = cdata
            sf, p = self._uleb(p)
            inf, p = self._uleb(p)
            dm, p = self._uleb(p)
            vm, p = self._uleb(p)
            for _ in range(sf + inf):
                _, p = self._uleb(p)
                _, p = self._uleb(p)
            mi = 0
            for k in range(dm + vm):
                if k == dm:
                    mi = 0
                dlt, p = self._uleb(p)
                mi += dlt
                _, p = self._uleb(p)
                co, p = self._uleb(p)
                if co and (name is None or self.method(mi).split('->')[1].startswith(name + '(')):
                    n, = struct.unpack_from('<I', self.d, co + 12)
                    out.append((self.method(mi), co + 16, n))
        return out

    def insns(self, cls, name):
        ms = self.methods(cls, name)
        if len(ms) != 1:
            raise PatchError('%s->%s: expected 1 method, found %d' % (cls, name, len(ms)))
        return self.insns_at(ms[0][1], ms[0][2])

    def insns_at(self, off, units):
        out, a = [], 0
        while a < units:
            i = Insn(self, off + 2 * a, a)
            out.append(i)
            a += i.size
        return out

    def fix_checksums(self):
        self.d[12:32] = hashlib.sha1(bytes(self.d[32:])).digest()
        struct.pack_into('<I', self.d, 8, zlib.adler32(bytes(self.d[12:])) & 0xffffffff)


def set_branch_offset(insn, units):
    """Rewrite the 16-bit branch offset of an if-test / if-testz instruction."""
    if not (0x32 <= insn.op <= 0x3d):
        raise PatchError('not a conditional branch: %r' % insn)
    struct.pack_into('<h', insn.dex.d, insn.off + 2, units)


def find_one(seq, what):
    if len(seq) != 1:
        raise PatchError('%s: pattern matched %d times (expected 1)' % (what, len(seq)))
    return seq[0]


# registers written by an instruction (used to prove that a constant register survives)
_WRITE_A4 = {0x01, 0x04, 0x07, 0x12, 0x20, 0x21, 0x23} | set(range(0x52, 0x59)) | set(range(0x7b, 0x90)) \
    | set(range(0xb0, 0xd0)) | set(range(0xd0, 0xd8))
_WRITE_AA = {0x02, 0x05, 0x08, 0x0a, 0x0b, 0x0c, 0x0d, 0x1a, 0x1b, 0x1c, 0x1f, 0x22, 0xfe, 0xff} \
    | set(range(0x13, 0x1a)) | set(range(0x2d, 0x32)) | set(range(0x44, 0x4b)) | set(range(0x60, 0x67)) \
    | set(range(0x90, 0xb0)) | set(range(0xd8, 0xe3))
_WRITE_A16 = {0x03, 0x06, 0x09}
_WIDE = {0x04, 0x05, 0x06, 0x0b, 0x16, 0x17, 0x18, 0x19, 0x45, 0x53, 0x61, 0x7d, 0x80, 0x81, 0x83, 0x86,
         0x88, 0x89, 0x8b} | set(range(0x9b, 0xa6)) | set(range(0xab, 0xb0)) | set(range(0xbb, 0xc6)) \
    | set(range(0xcb, 0xd0))


def dest_regs(i):
    if i.payload:
        return set()
    if i.op in _WRITE_A4:
        r = i.a4
    elif i.op in _WRITE_AA:
        r = i.aa
    elif i.op in _WRITE_A16:
        r = struct.unpack_from('<H', i.dex.d, i.off + 2)[0]
    else:
        return set()
    return {r, r + 1} if i.op in _WIDE else {r}


# ---------------------------------------------------------------- apk / jar dex patching

def patch_dex_in_zip(zip_path, cls, fn, label):
    """Find the stored classesN.dex holding `cls`, let fn(dex) patch it in place, fix sums."""
    z = ZipFile(zip_path)
    names = sorted((n for n in z.entries if n.startswith('classes') and n.endswith('.dex')),
                   key=lambda n: int(n[7:-4] or 1))
    for n in names:
        dex = Dex(z.read(n))
        if not dex.has_class(cls):
            continue
        fn(dex)
        dex.fix_checksums()
        z.write_stored(n, bytes(dex.d))
        z.save()
        return n
    raise PatchError('%s: class %s not found' % (label, cls))


def patch_any_dex_in_zip(zip_path, fn, label):
    """Like patch_dex_in_zip for obfuscated apps: fn(dex) returns True when it patched that dex."""
    z = ZipFile(zip_path)
    names = sorted((n for n in z.entries if n.startswith('classes') and n.endswith('.dex')),
                   key=lambda n: int(n[7:-4] or 1))
    for n in names:
        dex = Dex(z.read(n))
        if not fn(dex):
            continue
        dex.fix_checksums()
        z.write_stored(n, bytes(dex.d))
        z.save()
        return n
    raise PatchError('%s: pattern not found in any dex' % label)


# ---------------------------------------------------------------- resources.arsc string

def _pool(a, p):
    t, hs, sz, sc, stc, fl, ss, sts = struct.unpack_from('<HHIIIIII', a, p)
    return dict(p=p, sc=sc, stc=stc, fl=fl, ss=ss, offs=struct.unpack_from('<%dI' % sc, a, p + hs))


def _pool_str(a, pi, i):
    q = pi['p'] + pi['ss'] + pi['offs'][i]
    if pi['fl'] & 0x100:
        n = a[q]; q += 1
        if n & 0x80:
            n = ((n & 0x7f) << 8) | a[q]; q += 1
        bl = a[q]; q += 1
        if bl & 0x80:
            bl = ((bl & 0x7f) << 8) | a[q]; q += 1
        return a[q:q + bl].decode('utf8', 'replace'), q, bl, n
    n, = struct.unpack_from('<H', a, q)
    return a[q + 2:q + 2 + 2 * n].decode('utf-16le', 'replace'), q + 2, 2 * n, n


def _type_entries(a, p, chs):
    tid, flags, _, ec, es = struct.unpack_from('<BBHII', a, p + 8)
    if flags & 1:
        items = [(e, o * 4) for e, o in (struct.unpack_from('<HH', a, p + chs + 4 * i) for i in range(ec))]
    elif flags & 2:
        items = [(i, o * 4) for i, o in enumerate(struct.unpack_from('<%dH' % ec, a, p + chs)) if o != 0xffff]
    else:
        items = [(i, o) for i, o in enumerate(struct.unpack_from('<%dI' % ec, a, p + chs)) if o != 0xffffffff]
    return tid, [(eid, p + es + o) for eid, o in items]


def patch_arsc_string(apk_path, res_type, res_name, text):
    """Point every configuration of string resource `res_name` at its default string and
    overwrite that string in place (resources.arsc must be stored; size stays the same)."""
    z = ZipFile(apk_path)
    a = bytearray(z.read('resources.arsc'))
    _, hs, size = struct.unpack_from('<HHI', a, 0)
    p, gpool, pkg = hs, None, None
    while p < size:
        ct, _, csz = struct.unpack_from('<HHI', a, p)
        if ct == 1 and gpool is None:
            gpool = p
        if ct == 0x200 and pkg is None:
            pkg = p
        p += csz
    gpi = _pool(a, gpool)
    _, phs, psz = struct.unpack_from('<HHI', a, pkg)
    tstr, _, kstr, _ = struct.unpack_from('<IIII', a, pkg + 268)
    tpi, kpi = _pool(a, pkg + tstr), _pool(a, pkg + kstr)
    refs, targets = {}, []
    p = pkg + phs
    while p < pkg + psz:
        ct, chs, csz = struct.unpack_from('<HHI', a, p)
        if ct == 0x201:
            tid, items = _type_entries(a, p, chs)
            tname = _pool_str(a, tpi, tid - 1)[0]
            for eid, e in items:
                esz, efl, key = struct.unpack_from('<HHI', a, e)
                if efl & 1 or efl & 8:          # complex / compact entries are never our target
                    continue
                vo = e + esz
                _, _, dt, data = struct.unpack_from('<HBBI', a, vo)
                if dt == 3:
                    refs[data] = refs.get(data, 0) + 1
                if tname == res_type and _pool_str(a, kpi, key)[0] == res_name:
                    targets.append((vo, dt, data))
        p += csz
    if not targets or any(t[1] != 3 for t in targets):
        raise PatchError('%s/%s not found as plain string' % (res_type, res_name))
    base = targets[0][2]
    if refs[base] != sum(1 for t in targets if t[2] == base):
        raise PatchError('default string of %s is shared with other resources' % res_name)
    if base < gpi['stc']:
        raise PatchError('string has style spans')
    for vo, _, _ in targets:
        struct.pack_into('<I', a, vo + 4, base)
    old, q, bl, nch = _pool_str(a, gpi, base)
    nb = text.encode()
    if not gpi['fl'] & 0x100 or len(nb) > bl or len(nb) >= 0x80 or bl >= 0x80 or nch >= 0x80:
        raise PatchError('replacement text does not fit (%d bytes available)' % bl)
    start = q - 2
    a[start] = len(text)
    a[start + 1] = len(nb)
    a[q:q + bl + 1] = nb + b'\0' * (bl + 1 - len(nb))
    z.write_stored('resources.arsc', bytes(a))
    z.save()
    return '%d configs -> %r (was %r)' % (len(targets), text, old)


# ---------------------------------------------------------------- binary XML attribute insert

def _read_deflated(z, entry):
    T = z.entries[entry]
    if T['meth'] != 8:
        raise PatchError(entry + ' is not deflated')
    ds, _ = z.data_range(entry)
    return bytearray(zlib.decompress(bytes(z.a[ds:ds + T['csz']]), -15))


def _rewrite_deflated(z, entry, x):
    """Store new content `x` for a deflated entry. The re-deflated entry may grow; later entries
    move into the zero gap that sits in front of the APK Signing Block, so the signing block and
    central directory stay byte-identical. Returns (size delta, gap)."""
    a = z.a
    T = z.entries[entry]

    def dend(t):
        lfl, lel = struct.unpack_from('<HH', a, t['lho'] + 26)
        ds = t['lho'] + 30 + lfl + lel
        de = ds + t['csz']
        if t['flg'] & 8:
            de += 16 if a[de:de + 4] == b'PK\x07\x08' else 12
        return ds, de

    ds, de = dend(T)
    entries_end = max(dend(t)[1] for t in z.entries.values())
    cdoff = z.cd_off
    if a[cdoff - 16:cdoff] != b'APK Sig Block 42':
        raise PatchError('no APK signing block in front of central directory')
    blk = cdoff - struct.unpack_from('<Q', a, cdoff - 24)[0] - 8
    gap = blk - entries_end
    if any(a[entries_end:blk]):
        raise PatchError('gap before signing block is not empty')

    best = None
    for lvl in range(1, 10):
        for mem in range(1, 10):
            for strat in range(5):
                c = zlib.compressobj(lvl, 8, -15, mem, strat)
                r = c.compress(bytes(x)) + c.flush()
                if best is None or len(r) < len(best):
                    best = r
    delta = len(best) - T['csz']
    if delta > gap:
        raise PatchError('compressed entry grew %d bytes, only %d free before signing block' % (delta, gap))
    crc = zlib.crc32(x) & 0xffffffff
    desc = b''
    if T['flg'] & 8:
        sig = a[ds + T['csz']:ds + T['csz'] + 4] == b'PK\x07\x08'
        desc = (b'PK\x07\x08' if sig else b'') + struct.pack('<III', crc, len(best), len(x))
    else:
        struct.pack_into('<III', a, T['lho'] + 14, crc, len(best), len(x))
    new = a[:ds] + best + desc + a[de:entries_end]
    new += bytes(blk - len(new)) + a[blk:]
    struct.pack_into('<III', new, T['cd'] + 16, crc, len(best), len(x))
    for t in z.entries.values():
        if t['lho'] > T['lho']:
            struct.pack_into('<I', new, t['cd'] + 42, t['lho'] + delta)
    z.a = new
    z.save()
    return delta, gap


def _xml_tables(x):
    p, resmap, pool = 8, [], []
    while p < len(x):
        t, hs, sz = struct.unpack_from('<HHI', x, p)
        if t == 1:
            pi = _pool(x, p)
            pool = [_pool_str(x, pi, i)[0] for i in range(pi['sc'])]
        if t == 0x180:
            resmap = list(struct.unpack_from('<%dI' % ((sz - 8) // 4), x, p + 8))
        p += sz
    return resmap, pool


def _xml_elements(x, resmap, pool, elem_name, has_attr):
    p, found = 8, []
    while p < len(x):
        t, hs, sz = struct.unpack_from('<HHI', x, p)
        if t == 0x102:
            nm, = struct.unpack_from('<I', x, p + 20)
            ast, asz, acnt, idi, cli, sti = struct.unpack_from('<HHHHHH', x, p + 24)
            at = [struct.unpack_from('<IIIHBBI', x, p + 16 + ast + i * asz) for i in range(acnt)]
            ids = [resmap[q[1]] if q[1] < len(resmap) else 0xffffffff for q in at]
            if pool[nm] == elem_name and has_attr in ids:
                found.append((p, sz, ast, asz, acnt, idi, cli, sti, at, ids))
        p += sz
    return find_one(found, '<%s> with %#x' % (elem_name, has_attr))


def insert_xml_attr(apk_path, entry, elem_name, has_attr, attr, vtype, vdata):
    """Add attribute `attr` (android res id) to the single <elem_name> carrying `has_attr`."""
    z = ZipFile(apk_path)
    x = _read_deflated(z, entry)
    resmap, pool = _xml_tables(x)
    if attr not in resmap:
        raise PatchError('attribute %#x has no slot in the resource map' % attr)
    nameidx = resmap.index(attr)
    p, sz, ast, asz, acnt, idi, cli, sti, at, ids = _xml_elements(x, resmap, pool, elem_name, has_attr)
    if attr in ids:
        return 'already present'
    andns = [q[0] for q, r in zip(at, ids) if r >> 24 == 1][0]
    pos = sum(1 for r in ids if r < attr)
    x[p + 16 + ast + pos * asz:p + 16 + ast + pos * asz] = struct.pack('<IIIHBBI', andns, nameidx, 0xffffffff, 8, 0, vtype, vdata)
    struct.pack_into('<I', x, p + 4, sz + asz)
    struct.pack_into('<H', x, p + 28, acnt + 1)
    for o, v in ((p + 30, idi), (p + 32, cli), (p + 34, sti)):
        if v and v > pos:
            struct.pack_into('<H', x, o, v + 1)
    struct.pack_into('<I', x, 4, len(x))
    delta, gap = _rewrite_deflated(z, entry, x)
    return 'inserted at position %d (entry %+d bytes, gap %d)' % (pos, delta, gap)


def set_xml_int_attr(apk_path, entry, elem_name, attr, value):
    """Set the integer value of attribute `attr` (android res id) on the single <elem_name> that has
    it, e.g. android:versionCode on <manifest>. Returns the old value."""
    z = ZipFile(apk_path)
    x = _read_deflated(z, entry)
    resmap, pool = _xml_tables(x)
    p, sz, ast, asz, acnt, idi, cli, sti, at, ids = _xml_elements(x, resmap, pool, elem_name, attr)
    k = ids.index(attr)
    q = at[k]
    if q[2] != 0xffffffff or q[5] not in (0x10, 0x11):
        raise PatchError('%s %#x is not a plain integer' % (elem_name, attr))
    if q[6] == value:
        return value
    struct.pack_into('<I', x, p + 16 + ast + k * asz + 16, value)
    _rewrite_deflated(z, entry, x)
    return q[6]


ANDROID_ID = 0x010100d0


def restyle_xml_element_like(apk_path, entry, dst_id, src_id, keep, drop=()):
    """Give the element with android:id `dst_id` the tag and attributes of the element with
    android:id `src_id` (same layout), keeping dst's own values for the attrs in `keep` (android
    res ids, android:id always kept) and leaving out the attrs in `drop`. The style attribute and
    the id/class/style indices follow from the copied list. Returns a status string."""
    z = ZipFile(apk_path)
    x = _read_deflated(z, entry)
    resmap, pool = _xml_tables(x)
    els = {}
    p = 8
    while p < len(x):
        t, hs, sz = struct.unpack_from('<HHI', x, p)
        if t == 0x102:
            nm, = struct.unpack_from('<I', x, p + 20)
            ast, asz, acnt = struct.unpack_from('<HHH', x, p + 24)
            at = [bytes(x[p + 16 + ast + i * asz:p + 16 + ast + (i + 1) * asz]) for i in range(acnt)]
            ids = [resmap[struct.unpack_from('<I', a, 4)[0]] if struct.unpack_from('<I', a, 4)[0] < len(resmap)
                   else None for a in at]
            if ANDROID_ID in ids:
                v = struct.unpack_from('<I', at[ids.index(ANDROID_ID)], 16)[0]
                if v in (dst_id, src_id):
                    if v in els:
                        raise PatchError('%s: id %#x on more than one element' % (entry, v))
                    els[v] = (p, sz, nm, ast, asz, at, ids)
        p += sz
    if set(els) != {dst_id, src_id}:
        raise PatchError('%s: ids %#x/%#x not both found' % (entry, dst_id, src_id))
    p, sz, nm, ast, asz, dat, dids = els[dst_id]
    _, _, snm, sast, sasz, sat, sids = els[src_id]
    if asz != sasz:
        raise PatchError('%s: attribute record sizes differ' % entry)
    keep = set(keep) | {ANDROID_ID}
    if nm == snm and not any(r in dids for r in drop):
        return 'already a <%s>' % pool[snm]
    new = []
    for a, r in zip(sat, sids):
        if r in drop:
            continue
        if r in keep:
            if r not in dids:
                raise PatchError('%s: dst element has no %#x to keep' % (entry, r))
            a = dat[dids.index(r)]
        new.append((a, r))
    missing = [r for r in keep if r not in [q[1] for q in new]]
    if missing:
        raise PatchError('%s: src element lacks kept attrs %s' % (entry, [hex(m) for m in missing]))

    def idx(pred):
        hits = [i + 1 for i, (a, r) in enumerate(new) if pred(a, r)]
        return hits[0] if hits else 0
    idi = idx(lambda a, r: r == ANDROID_ID)
    sti = idx(lambda a, r: r is None and pool[struct.unpack_from('<I', a, 4)[0]] == 'style'
              and struct.unpack_from('<I', a, 0)[0] == 0xffffffff)
    cli = idx(lambda a, r: r is None and pool[struct.unpack_from('<I', a, 4)[0]] == 'class'
              and struct.unpack_from('<I', a, 0)[0] == 0xffffffff)
    head = bytearray(x[p:p + 16 + ast])
    struct.pack_into('<I', head, 20, snm)
    struct.pack_into('<HHHH', head, 28, len(new), idi, cli, sti)
    body = head + b''.join(a for a, r in new)
    struct.pack_into('<I', body, 4, len(body))
    # matching end tag must directly follow (self-closing element)
    e = p + sz
    t, hs, esz = struct.unpack_from('<HHI', x, e)
    if t != 0x103 or struct.unpack_from('<I', x, e + 20)[0] != nm:
        raise PatchError('%s: dst element is not self-closing' % entry)
    struct.pack_into('<I', x, e + 20, snm)
    x[p:p + sz] = body
    struct.pack_into('<I', x, 4, len(x))
    delta, gap = _rewrite_deflated(z, entry, x)
    return '<%s> -> <%s>, %d attrs (entry %+d bytes, gap %d)' % (pool[nm], pool[snm], len(new), delta, gap)


def manifest_package(apk_path):
    """package="..." of an APK's binary AndroidManifest.xml (stdlib zip, no aapt)."""
    import zipfile as _zf
    with _zf.ZipFile(apk_path) as z:
        x = z.read('AndroidManifest.xml')
    _, pool = _xml_tables(x)
    p = 8
    while p < len(x):
        t, hs, sz = struct.unpack_from('<HHI', x, p)
        if t == 0x102:
            ast, asz, acnt = struct.unpack_from('<HHH', x, p + 24)
            for i in range(acnt):
                ns, nm, raw = struct.unpack_from('<III', x, p + 16 + ast + i * asz)
                if pool[nm] == 'package' and raw != 0xffffffff:
                    return pool[raw]
            break
        p += sz
    raise PatchError(apk_path + ': no package attribute')
