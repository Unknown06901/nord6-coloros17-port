#!/usr/bin/env python3
"""Write the Nord 6 firmware fix folder: the base build's firmware images + a Windows flasher.

Why: the port's "Hey Google" DSP voice model (base ColorOS 17.0.0.100, same as the donor's) crashes the
audio DSP when the phone still runs OxygenOS 16 firmware. Every ADSP crash drops charging and USB, so
wired Android Auto keeps reconnecting. With the base build's own firmware it runs clean (tested
2026-11-20: Hey Google armed + Desktop Head Unit session, 0 crashes). The DSP code is in modem.img; the
other images keep the firmware one matched set, as an official update ships it.

The folder holds images/ (firmware only, never boot/init_boot/vendor_boot or any port image), md5.txt,
flash_firmware.bat, README.txt and fastboot_driver/. flash_firmware.bat flashes the current slot with
no wipe: modem from the bootloader (fastbootd can't open it, recovery has it mounted), the rest from
fastbootd (the bootloader refuses critical partitions unless `flashing unlock_critical`, which wipes).

usage: make_firmware_fix.py BASE OUT_DIR [--skip-same-as DIR] [--all]
  BASE            base images folder, payload.bin or full OTA zip (Nord 6 ColorOS 17.0.0.100)
  --skip-same-as  folder of the firmware the phones have now (e.g. a slot backup or OxygenOS 16 images);
                  images identical to it are left out as well (modem must differ, or there is nothing to fix)
  --all           write every firmware image, including the ones that are the same on 16.0.5.1300
needs: python3; payload-dumper-go (tools/) when BASE is a zip or payload.bin
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

KIT = os.path.dirname(os.path.abspath(__file__))
# The base OTA's firmware, in flash order. modem first: the flasher writes it from the bootloader.
FIRMWARE = ['modem', 'xbl', 'xbl_config', 'xbl_ramdump', 'abl', 'tz', 'hyp', 'keymaster', 'devcfg', 'qupfw',
            'uefi', 'uefisecapp', 'imagefv', 'shrm', 'cpucp', 'cpucp_dtb', 'aop', 'aop_config', 'bluetooth',
            'featenabler', 'pvmfw', 'soccp_debug', 'soccp_dcd', 'engineering_cdt', 'oplusstanvbk',
            'dsp', 'spuservice', 'oplus_sec', 'splash']
# Byte-identical between OxygenOS 16.0.5.1300 and ColorOS 17.0.0.100 (splash: the logo data is the same,
# the phone stamps its own 5-byte header), so the default folder leaves them out.
SAME_ON_16 = {'dsp', 'spuservice', 'oplus_sec', 'splash'}
VERIFIED_BASE = 'CPH2793export_11_17.0.0.100(EX01)'   # build_port.py VERIFIED_BASE prefix


def md5(path, size=None):
    h = hashlib.md5()
    left = size if size is not None else os.path.getsize(path)
    with open(path, 'rb') as f:
        while left > 0:
            b = f.read(min(left, 1 << 20))
            if not b:
                break
            h.update(b)
            left -= len(b)
    return h.hexdigest()


def base_images(base, tmp, names):
    """Return a folder holding <name>.img for every name, unpacking a zip/payload.bin if needed."""
    if os.path.isdir(base):
        return base
    tool = shutil.which('payload-dumper-go') or os.path.join(KIT, 'tools', 'payload-dumper-go')
    out = os.path.join(tmp, 'base')
    subprocess.run([tool, '-p', ','.join(names), '-o', out, base], check=True,
                   stdout=subprocess.DEVNULL)
    return out


def base_version(folder):
    """ro.build.display.id-style version from my_manifest/build.prop, '' if it can't be read."""
    img = os.path.join(folder, 'my_manifest.img')
    tool = shutil.which('extract.erofs') or os.path.join(KIT, 'tools', 'extract.erofs')
    if not os.path.exists(img) or not os.path.exists(tool):
        return ''
    with tempfile.TemporaryDirectory() as t:
        subprocess.run([tool, '-i', img, '-X', '/build.prop', '-o', t],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for dp, _, fns in os.walk(t):
            if 'build.prop' in fns:
                for line in open(os.path.join(dp, 'build.prop'), errors='replace'):
                    if line.startswith('ro.build.display.full_id='):
                        return line.split('=', 1)[1].strip()
    return ''


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('base')
    ap.add_argument('out')
    ap.add_argument('--skip-same-as', metavar='DIR')
    ap.add_argument('--all', action='store_true')
    a = ap.parse_args()

    names = list(FIRMWARE) if a.all else [n for n in FIRMWARE if n not in SAME_ON_16]
    with tempfile.TemporaryDirectory() as tmp:
        src = base_images(a.base, tmp, names + ['my_manifest'])
        missing = [n for n in names if not os.path.exists(os.path.join(src, n + '.img'))]
        if missing:
            sys.exit('base has no %s' % ', '.join(n + '.img' for n in missing))
        ver = base_version(src)
        print('base: %s' % (ver or 'unknown version (no my_manifest.img)'))
        if ver and not ver.startswith(VERIFIED_BASE):
            print('WARNING: tested with %s; check the new firmware before handing it out' % VERIFIED_BASE)

        if a.skip_same_as:
            keep = []
            for n in names:
                old = os.path.join(a.skip_same_as, n + '.img')
                new = os.path.join(src, n + '.img')
                if os.path.exists(old) and md5(old, os.path.getsize(new)) == md5(new):
                    print('  same as current firmware, left out: %s' % n)
                else:
                    keep.append(n)
            names = keep
        if 'modem' not in names:
            sys.exit('modem.img is the same as the current firmware: nothing to fix')

        img_out = os.path.join(a.out, 'images')
        os.makedirs(img_out, exist_ok=True)
        sums = []
        for n in names:
            shutil.copy2(os.path.join(src, n + '.img'), img_out)
            sums.append('%s  %s.img' % (md5(os.path.join(img_out, n + '.img')), n))
        open(os.path.join(a.out, 'md5.txt'), 'w', newline='\r\n').write('\n'.join(sums) + '\n')

    # The flasher's PARTS list (fastbootd) = everything written except modem (bootloader).
    bat = open(os.path.join(KIT, 'assets', 'firmware', 'flash_firmware.bat'), newline='').read()
    parts = ' '.join(n for n in names if n != 'modem')
    lines = [('set PARTS=' + parts + '\r\n') if l.startswith('set PARTS=') else l
             for l in bat.splitlines(keepends=True)]
    bat = ''.join(lines).replace('All 25 firmware', 'All %d firmware' % len(names)) \
        .replace('the other 24 from FASTBOOTD', 'the other %d from FASTBOOTD' % (len(names) - 1))
    open(os.path.join(a.out, 'flash_firmware.bat'), 'w', newline='').write(bat)
    shutil.copy2(os.path.join(KIT, 'assets', 'firmware', 'README.txt'), a.out)
    shutil.copytree(os.path.join(KIT, 'assets', 'fastboot_driver'), os.path.join(a.out, 'fastboot_driver'),
                    dirs_exist_ok=True)
    print('%d firmware images -> %s' % (len(names), a.out))
    print('flash: phone in Android (USB debugging) or bootloader, then run flash_firmware.bat on Windows')


if __name__ == '__main__':
    main()
