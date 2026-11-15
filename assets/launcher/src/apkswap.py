# Replace entries (stored or deflated) of a signed apk in place, keeping the APK Signing Block and
# every other byte; each replaced entry's extra field is padded so later data moves by a multiple
# of 4096 (keeps page-aligned .so / aligned resources.arsc). Preinstalled system apps only have
# their certificate read, so the stale v3 digest is accepted (same as port_kit lib/dock.py).
import struct, zlib

def replace_entries(apk, replace):
    a = open(apk, 'rb').read()
    e = a.rfind(b'PK\x05\x06')
    n, = struct.unpack_from('<H', a, e + 10)
    cd_off, = struct.unpack_from('<I', a, e + 16)
    assert a[cd_off - 16:cd_off] == b'APK Sig Block 42', 'no signing block'
    sb_size, = struct.unpack_from('<Q', a, cd_off - 24)
    sb_off = cd_off - sb_size - 8
    cds, o = [], cd_off
    for _ in range(n):
        fl, el, cl = struct.unpack_from('<HHH', a, o + 28)
        cds.append((o, a[o + 46:o + 46 + fl].decode(), struct.unpack_from('<I', a, o + 42)[0], 46 + fl + el + cl))
        o += 46 + fl + el + cl
    order = sorted(cds, key=lambda c: c[2])
    bounds = [c[2] for c in order] + [sb_off]
    todo = dict(replace)
    out, newpos, cdpatch, shift = bytearray(), {}, {}, 0
    for i, c in enumerate(order):
        start, end = bounds[i], bounds[i + 1]
        newpos[c[1]] = len(out)
        if c[1] not in todo:
            out += a[start:end]
            continue
        flg, meth = struct.unpack_from('<HH', a, start + 6)
        assert meth in (0, 8) and not flg & 8, c[1]
        fl, = struct.unpack_from('<H', a, start + 26)
        data = todo.pop(c[1])
        crc = zlib.crc32(data) & 0xffffffff
        if meth == 8:
            co = zlib.compressobj(9, zlib.DEFLATED, -15)
            body = co.compress(data) + co.flush()
        else:
            body = data
        hdr = bytearray(a[start:start + 30 + fl])
        struct.pack_into('<III', hdr, 14, crc, len(body), len(data))
        base = len(hdr) + len(body) - (end - start) + shift
        pad = (-base) % 4096
        struct.pack_into('<H', hdr, 28, pad)
        out += hdr + b'\0' * pad + body
        shift = base + pad
        cdpatch[c[1]] = (crc, len(body), len(data))
    assert not todo, todo
    out += a[sb_off:cd_off]
    new_cd = len(out)
    for o, name, _, ln in cds:
        ent = bytearray(a[o:o + ln])
        struct.pack_into('<I', ent, 42, newpos[name])
        if name in cdpatch:
            struct.pack_into('<III', ent, 16, *cdpatch[name])
        out += ent
    eocd = bytearray(a[e:])
    struct.pack_into('<I', eocd, 16, new_cd)
    out += eocd
    open(apk, 'wb').write(out)
