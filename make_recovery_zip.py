#!/usr/bin/env python3
"""Pack a built port (the images folder build_port.py writes) into a zip for the Nord 6 TWRP:
Install from internal storage or USB-OTG, or `adb sideload` from any PC or phone.

The zip holds every image zstd-compressed (stored, so recovery streams it without unpacking),
port/manifest.txt (sizes + sha256 of the raw images) and assets/recovery/update-binary, which
recreates the logical partitions in super with TWRP's lptools and verifies every write.
A folder with only some images (e.g. system_ext.img + my_product.img) gives a fix package
that replaces just those partitions, like a dirty flash_all.bat run.

The zip never writes firmware. The manifest carries the sha256 of the base build's firmware images
(--firmware-ref, default ../base/images), so the installer can tell the user whether the phone's
firmware is the one the port was built and tested on.

usage: make_recovery_zip.py IMAGES_DIR OUT.zip [--level 19] [--title TEXT] [--firmware-ref DIR]
                            [--reuse OLD.zip]
needs: python3, zstd; dump.erofs (erofs-utils) is optional, for the version line
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import threading
import time
import zipfile

KIT = os.path.dirname(os.path.abspath(__file__))
BINARY = os.path.join(KIT, 'assets', 'recovery', 'update-binary')

# Same order as flash_all.bat. Raw = written to <name>_<slot> directly.
LOGICAL = ['vendor', 'odm', 'vendor_dlkm', 'system_dlkm', 'system', 'system_ext', 'product', 'my_product',
           'my_stock', 'my_heytap', 'my_region', 'my_bigball', 'my_manifest', 'my_engineering', 'my_company',
           'my_preload', 'my_carrier']
RAW = ['vbmeta', 'vbmeta_system', 'vbmeta_vendor', 'boot', 'init_boot', 'vendor_boot', 'dtbo']
# Firmware in the base OTA (everything that is neither a port image nor recovery). Only checked, never written.
FIRMWARE = ['xbl', 'xbl_config', 'xbl_ramdump', 'abl', 'tz', 'hyp', 'keymaster', 'devcfg', 'qupfw', 'uefi',
            'uefisecapp', 'imagefv', 'shrm', 'cpucp', 'cpucp_dtb', 'aop', 'aop_config', 'modem', 'dsp', 'bluetooth',
            'spuservice', 'featenabler', 'oplus_sec', 'pvmfw', 'soccp_debug', 'soccp_dcd', 'engineering_cdt',
            'splash', 'oplusstanvbk']
CHUNK = 1 << 20


def erofs_prop(img, path, key):
    """Value of `key` in a build.prop inside an erofs image, or '' when it can't be read."""
    if not shutil.which('dump.erofs') or not os.path.exists(img):
        return ''
    r = subprocess.run(['dump.erofs', '--cat', '--path=' + path, img], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.startswith(key + '='):
            return line.split('=', 1)[1].strip()
    return ''


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while b := f.read(CHUNK):
            h.update(b)
    return h.hexdigest()


def add_zst(zf, img, arcname, level, old=None):
    """Compress img with zstd straight into a stored zip entry, or copy the entry from `old`
    (an earlier zip whose manifest has the same sha256 for this image)."""
    zi = zipfile.ZipInfo(arcname, time.localtime()[:6])
    zi.compress_type = zipfile.ZIP_STORED
    zi.external_attr = 0o644 << 16
    if old:
        with old.open(arcname) as src, zf.open(zi, 'w', force_zip64=True) as out:
            while b := src.read(CHUNK):
                out.write(b)
        return zf.getinfo(arcname).file_size
    p = subprocess.Popen(['zstd', '-%d' % level, '-T0', '-q', '-c', '--no-progress', img], stdout=subprocess.PIPE)
    with zf.open(zi, 'w', force_zip64=True) as out:
        while b := p.stdout.read(CHUNK):
            out.write(b)
    if p.wait():
        raise SystemExit('zstd failed on ' + img)
    return zf.getinfo(arcname).file_size


def verify(zpath, entries):
    """Unpack every image from the finished zip through zstd and compare the sha256."""
    with zipfile.ZipFile(zpath) as zf:
        for name, size, digest in entries:
            p = subprocess.Popen(['zstd', '-dcq'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            h, n = hashlib.sha256(), 0
            def feed():
                with zf.open('port/%s.img.zst' % name) as src:
                    while b := src.read(CHUNK):
                        p.stdin.write(b)
                p.stdin.close()
            t = threading.Thread(target=feed)
            t.start()
            while b := p.stdout.read(CHUNK):
                h.update(b)
                n += len(b)
            t.join()
            if p.wait() or n != size or h.hexdigest() != digest:
                raise SystemExit('verify FAILED: %s' % name)
            print('  verified', name)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('images')
    ap.add_argument('out')
    ap.add_argument('--level', type=int, default=19, help='zstd level (default 19)')
    ap.add_argument('--title', default='OnePlus Nord 6 - ColorOS 17 port')
    ap.add_argument('--no-verify', action='store_true', help='skip unpacking the finished zip to check it')
    ap.add_argument('--firmware-ref', default=os.path.join(os.path.dirname(KIT), 'base', 'images'),
                    help='base images folder whose firmware the installer compares the phone with')
    ap.add_argument('--reuse', help='earlier zip: images with an unchanged sha256 are copied, not recompressed')
    a = ap.parse_args()

    if not shutil.which('zstd'):
        raise SystemExit('zstd not found (sudo apt install zstd)')
    plan = [('logical', n) for n in LOGICAL if os.path.exists(os.path.join(a.images, n + '.img'))]
    plan += [('raw', n) for n in RAW if os.path.exists(os.path.join(a.images, n + '.img'))]
    if not plan:
        raise SystemExit('no partition images in ' + a.images)
    for _, n in plan:
        if os.path.getsize(os.path.join(a.images, n + '.img')) % 4096:
            raise SystemExit(n + '.img size is not a multiple of 4096')

    version = erofs_prop(os.path.join(a.images, 'my_manifest.img'), '/build.prop', 'ro.build.display.id')
    sdk = erofs_prop(os.path.join(a.images, 'system.img'), '/system/build.prop', 'ro.system.build.version.sdk')
    if any(n == 'system' for _, n in plan) and not sdk:
        print('note: could not read the SDK level from system.img (dump.erofs missing?);'
              ' the installer will then not detect an Android version change')

    fw = [n for n in FIRMWARE if os.path.exists(os.path.join(a.firmware_ref, n + '.img'))]
    fwversion = erofs_prop(os.path.join(a.firmware_ref, 'my_manifest.img'), '/build.prop', 'ro.build.display.id')
    if not fw:
        print('note: no firmware images in %s, the installer will skip the firmware check' % a.firmware_ref)

    entries, lines = [], ['title=' + a.title, 'version=' + version, 'sdk=' + sdk,
                          'built=' + time.strftime('%Y-%m-%d %H:%M'), 'fwversion=' + (fwversion or 'the base build')]
    for kind, n in plan:
        img = os.path.join(a.images, n + '.img')
        size, digest = os.path.getsize(img), sha256(img)
        entries.append((n, size, digest))
        lines.append('img %s %s %d %s' % (kind, n, size, digest))
    for n in fw:
        img = os.path.join(a.firmware_ref, n + '.img')
        lines.append('fw %s %d %s' % (n, os.path.getsize(img), sha256(img)))
    manifest = '\n'.join(lines) + '\n'

    old, reusable = None, {}
    if a.reuse:
        old = zipfile.ZipFile(a.reuse)
        names = set(old.namelist())
        for line in old.read('port/manifest.txt').decode().splitlines():
            f = line.split()
            if f and f[0] == 'img' and 'port/%s.img.zst' % f[2] in names:
                reusable[f[2]] = (int(f[3]), f[4])

    tmp = a.out + '.part'
    t0 = time.time()
    with zipfile.ZipFile(tmp, 'w', allowZip64=True) as zf:
        zi = zipfile.ZipInfo('META-INF/com/google/android/update-binary', time.localtime()[:6])
        zi.external_attr = 0o755 << 16
        zi.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(zi, open(BINARY, 'rb').read())
        zf.writestr('META-INF/com/google/android/updater-script', '#PORT (the installer is update-binary)\n')
        zf.writestr('port/manifest.txt', manifest)
        total = 0
        for kind, n in plan:
            img = os.path.join(a.images, n + '.img')
            size, digest = next((s, d) for m, s, d in entries if m == n)
            src = old if reusable.get(n) == (size, digest) else None
            c = add_zst(zf, img, 'port/%s.img.zst' % n, a.level, src)
            total += c
            print('  %-15s %6d MB -> %6d MB  (%ds)%s' % (n, size >> 20, c >> 20, time.time() - t0,
                                                         '  reused' if src else ''), flush=True)
    if not a.no_verify:
        print('verifying the zip...')
        verify(tmp, entries)
    os.replace(tmp, a.out)
    print('wrote %s (%.2f GB, %d images)' % (a.out, os.path.getsize(a.out) / 1e9, len(plan)))
    print(manifest)


if __name__ == '__main__':
    main()
