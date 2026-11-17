"""Minimal dtbo.img / flattened-device-tree editor (no dtc needed).

dtbo.img = DTBO header + entry table + one FDT overlay blob per entry, optionally followed by an AVB
hash footer. We only ever add properties to existing nodes, so each blob is re-serialised and the
image is rebuilt with the same entry order. The AVB footer (if any) is kept in place and its
original_image_size updated; its hash goes stale, which is fine because the port's vbmeta has
verification disabled (flags 3).
"""
import struct

FDT_MAGIC = 0xd00dfeed
DTBO_MAGIC = 0xd7b7ab1e
BEGIN, END_NODE, PROP, NOP, END = 1, 2, 3, 4, 9


def _pad4(n):
    return (n + 3) & ~3


class Fdt:
    """Parsed FDT: tree of nodes [name, props(list of [name, bytes]), children]."""

    def __init__(self, blob):
        (magic, total, off_struct, off_strings, off_rsv, version, last_comp, boot_cpu,
         size_strings, size_struct) = struct.unpack('>10I', blob[:40])
        if magic != FDT_MAGIC:
            raise ValueError('not an FDT blob')
        self.version, self.last_comp, self.boot_cpu = version, last_comp, boot_cpu
        self.rsvmap = blob[off_rsv:off_struct] if off_rsv < off_struct else b'\0' * 16
        strings = blob[off_strings:off_strings + size_strings]
        self.strings = bytes(strings)
        p = off_struct
        stack, self.root = [], None
        while True:
            tok = struct.unpack('>I', blob[p:p + 4])[0]
            p += 4
            if tok == BEGIN:
                e = blob.index(b'\0', p)
                node = [blob[p:e].decode(), [], []]
                p = _pad4(e + 1)
                if stack:
                    stack[-1][2].append(node)
                else:
                    self.root = node
                stack.append(node)
            elif tok == END_NODE:
                stack.pop()
            elif tok == PROP:
                ln, noff = struct.unpack('>II', blob[p:p + 8])
                p += 8
                name = strings[noff:strings.index(b'\0', noff)].decode()
                stack[-1][1].append([name, blob[p:p + ln], noff])  # keep dtc's name offset
                p = _pad4(p + ln)
            elif tok == NOP:
                pass
            elif tok == END:
                break
            else:
                raise ValueError('bad FDT token %d' % tok)

    def walk(self, node=None, path=''):
        node = node or self.root
        here = path + '/' + node[0] if node is not self.root else ''
        yield here or '/', node
        for c in node[2]:
            yield from self.walk(c, here)

    def pack(self):
        # keep dtc's string table (it shares suffixes) and only append names it doesn't have
        strings, st = bytearray(self.strings), bytearray()

        def soff(name):
            key = name.encode() + b'\0'
            i = 0
            while True:
                i = strings.find(key, i)
                if i < 0:
                    i = len(strings)
                    strings.extend(key)
                    return i
                if i == 0 or strings[i - 1] == 0 or key in self.strings[i:i + len(key)]:
                    return i
                i += 1

        def emit(node):
            nm = node[0].encode() + b'\0'
            st.extend(struct.pack('>I', BEGIN) + nm + b'\0' * (_pad4(len(nm)) - len(nm)))
            for pr in node[1]:
                name, val = pr[0], pr[1]
                off = pr[2] if len(pr) > 2 else soff(name)
                st.extend(struct.pack('>III', PROP, len(val), off) + val
                          + b'\0' * (_pad4(len(val)) - len(val)))
            for c in node[2]:
                emit(c)
            st.extend(struct.pack('>I', END_NODE))

        emit(self.root)
        st.extend(struct.pack('>I', END))
        off_rsv = 40
        off_struct = off_rsv + len(self.rsvmap)
        off_strings = off_struct + len(st)
        total = off_strings + len(strings)
        hdr = struct.pack('>10I', FDT_MAGIC, total, off_struct, off_strings, off_rsv, self.version,
                          self.last_comp, self.boot_cpu, len(strings), len(st))
        return hdr + bytes(self.rsvmap) + bytes(st) + bytes(strings)


def prop(node, name):
    return next((p[1] for p in node[1] if p[0] == name), None)


def set_prop(node, name, value, after=None):
    """Set (or add) a property. New properties go right after `after` if present."""
    for p in node[1]:
        if p[0] == name:
            p[1] = value
            return
    idx = next((i + 1 for i, p in enumerate(node[1]) if p[0] == after), len(node[1]))
    node[1].insert(idx, [name, value])


def edit_dtbo(path, out, edit):
    """Run edit(fdt) -> bool(changed) on every overlay blob in dtbo image `path`, write `out`.
    Returns the number of blobs changed."""
    img = open(path, 'rb').read()
    magic, total, hsize, esize, count, eoff, page, ver = struct.unpack('>8I', img[:32])
    if magic != DTBO_MAGIC:
        raise ValueError(path + ' is not a dtbo image')
    entries = [list(struct.unpack('>8I', img[eoff + i * esize:eoff + (i + 1) * esize])) for i in range(count)]
    blobs, changed = [], 0
    for e in entries:
        b = img[e[1]:e[1] + e[0]]
        f = Fdt(b)
        if edit(f):
            b = f.pack()
            changed += 1
        blobs.append(b)
    if not changed:
        return 0
    body = bytearray(img[:eoff + count * esize])
    pos = len(body)
    for e, b in zip(entries, blobs):
        e[0], e[1] = len(b), pos
        body.extend(b)
        pos += len(b)
    for i, e in enumerate(entries):
        body[eoff + i * esize:eoff + (i + 1) * esize] = struct.pack('>8I', *e)
    body[4:8] = struct.pack('>I', len(body))
    new = bytes(body)
    if img[-64:-60] == b'AVBf':
        foot = bytearray(img[-64:])
        vb_off, vb_size = struct.unpack('>QQ', foot[20:36])
        if len(new) > vb_off:
            raise ValueError('edited dtbo no longer fits before its AVB metadata')
        foot[12:20] = struct.pack('>Q', len(new))
        new = new.ljust(vb_off, b'\0') + img[vb_off:vb_off + vb_size]
        new = new.ljust(len(img) - 64, b'\0') + bytes(foot)
    elif len(new) < len(img):
        new = new.ljust(len(img), b'\0')
    open(out, 'wb').write(new)
    return changed
