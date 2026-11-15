# KernelSU Next helper for flash_all.bat - everything runs on this PC, the phone is not needed.
#   -Action download : fetch the latest KernelSU Next release into .\ksu: the kernel module for the
#                      kernel in boot.img, ksuinit (taken out of the official ksud) and the manager apk
#   -Action patch    : patch .\init_boot.img with them and save it as .\init_boot_ksu.img
#                      (same result as "ksud boot-patch": init -> init.real, ksuinit as init,
#                      kernelsu.ko, ksu_config; AVB footer kept)
#   -Action install  : install the downloaded manager apk over adb (phone booted, USB debugging on)
# Exit code 0 = success, anything else = failure (message printed).
param([Parameter(Mandatory = $true)][ValidateSet('download', 'patch', 'install')][string]$Action)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$here = $PSScriptRoot
$ksuDir = Join-Path $here 'ksu'
$ksuinit = Join-Path $ksuDir 'ksuinit'
$apk = Join-Path $ksuDir 'KernelSU_Next.apk'
$verFile = Join-Path $ksuDir 'version.txt'
$adb = if (Test-Path (Join-Path $here 'adb.exe')) { Join-Path $here 'adb.exe' } else { 'adb' }

function Fail($msg) { Write-Host "ERROR: $msg"; exit 1 }

# message of an exception thrown inside the C# patcher (PowerShell wraps it)
function Inner($err) { $e = $err.Exception; if ($e.InnerException) { $e = $e.InnerException }; return $e.Message }

# KMI of the kernel the phone will run: the port's boot.img, else the Nord 6 stock kernel
function Get-Kmi {
    $bootImg = Join-Path $here 'boot.img'
    if (Test-Path $bootImg) {
        $txt = [Text.Encoding]::GetEncoding(28591).GetString([IO.File]::ReadAllBytes($bootImg))
        $m = [regex]::Match($txt, 'Linux version (\d+)\.(\d+)\.\d+-(android\d+)-')
        if ($m.Success) { return "$($m.Groups[3].Value)-$($m.Groups[1].Value).$($m.Groups[2].Value)" }
        Fail 'could not read the kernel version from boot.img'
    }
    Write-Host 'boot.img is not in this folder, assuming the Nord 6 stock kernel (KMI android15-6.6).'
    return 'android15-6.6'
}

function Get-Asset($rel, $re) {
    $a = @($rel.assets | Where-Object { $_.name -match $re })
    if ($a.Count -ne 1) { Fail "release $($rel.tag_name): expected one asset matching $re, found $($a.Count)" }
    return $a[0]
}

function Save-Asset($asset, $dest) {
    $tmp = "$dest.part"
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tmp -UseBasicParsing -Headers @{ 'User-Agent' = 'nord6-port-flasher' }
    if ((Get-Item $tmp).Length -ne $asset.size) { Remove-Item $tmp; Fail "$($asset.name): size mismatch, download broken" }
    if ($asset.digest -and $asset.digest -like 'sha256:*') {
        $h = (Get-FileHash -Algorithm SHA256 $tmp).Hash.ToLower()
        if ($h -ne $asset.digest.Substring(7).ToLower()) { Remove-Item $tmp; Fail "$($asset.name): sha256 mismatch" }
    }
    Move-Item -Force $tmp $dest
}

# ---------------------------------------------------------------- C# patcher
$patcherSrc = @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

public static class KsuPatcher
{
    // ---- raw deflate (RFC 1951) decoder that reports where a stream ends; ksud keeps its
    // embedded files as raw deflate streams laid back to back
    sealed class Inflater
    {
        byte[] src; int pos, end, bitbuf, bitcnt; bool err;
        public byte[] Out = new byte[1 << 16]; public int OutLen; int outMax; bool scan;
        short[] lenCount = new short[16], lenSym = new short[288], distCount = new short[16], distSym = new short[30];
        short[] lengths = new short[320], offs = new short[16];
        static short[] fixLenCount = new short[16], fixLenSym = new short[288], fixDistCount = new short[16], fixDistSym = new short[30];
        static readonly short[] LBase = { 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258 };
        static readonly short[] LExt = { 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0 };
        static readonly short[] DBase = { 1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577 };
        static readonly short[] DExt = { 0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13 };
        static readonly byte[] Order = { 16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15 };
        static readonly byte[] ElfMagic = { 0x7f, 0x45, 0x4c, 0x46 };

        static Inflater()
        {
            short[] l = new short[288]; short[] o = new short[16];
            for (int i = 0; i < 288; i++) l[i] = (short)(i < 144 ? 8 : i < 256 ? 9 : i < 280 ? 7 : 8);
            Construct(fixLenCount, fixLenSym, l, 288, o);
            for (int i = 0; i < 30; i++) l[i] = 5;
            Construct(fixDistCount, fixDistSym, l, 30, o);
        }

        public Inflater(byte[] data) { src = data; end = data.Length; }

        int Bits(int need)
        {
            long val = bitbuf;
            while (bitcnt < need)
            {
                if (pos >= end) { err = true; return 0; }
                val |= (long)src[pos++] << bitcnt; bitcnt += 8;
            }
            bitbuf = (int)(val >> need); bitcnt -= need;
            return (int)(val & ((1L << need) - 1));
        }

        bool Put(byte b)
        {
            if (OutLen >= outMax) return false;
            if (scan && OutLen < 4 && b != ElfMagic[OutLen]) return false;
            if (OutLen == Out.Length) Array.Resize(ref Out, Out.Length * 2);
            Out[OutLen++] = b;
            return true;
        }

        static int Construct(short[] count, short[] symbol, short[] length, int n, short[] offs)
        {
            for (int i = 0; i < 16; i++) count[i] = 0;
            for (int s = 0; s < n; s++) count[length[s]]++;
            if (count[0] == n) return 0;
            int left = 1;
            for (int len = 1; len < 16; len++) { left <<= 1; left -= count[len]; if (left < 0) return left; }
            offs[1] = 0;
            for (int len = 1; len < 15; len++) offs[len + 1] = (short)(offs[len] + count[len]);
            for (int s = 0; s < n; s++) if (length[s] != 0) symbol[offs[length[s]]++] = (short)s;
            return left;
        }

        int Decode(short[] count, short[] symbol)
        {
            int code = 0, first = 0, index = 0;
            for (int len = 1; len < 16; len++)
            {
                code |= Bits(1);
                if (err) return -1;
                int c = count[len];
                if (code - c < first) return symbol[index + (code - first)];
                index += c; first += c; first <<= 1; code <<= 1;
            }
            return -10;
        }

        int Stored()
        {
            bitbuf = 0; bitcnt = 0;
            if (pos + 4 > end) return -1;
            int len = src[pos] | src[pos + 1] << 8, nlen = src[pos + 2] | src[pos + 3] << 8;
            pos += 4;
            if (len != (~nlen & 0xffff)) return -2;
            if (pos + len > end) return -1;
            for (int i = 0; i < len; i++) if (!Put(src[pos++])) return 1;
            return 0;
        }

        int Codes(short[] lc, short[] ls, short[] dc, short[] ds)
        {
            int sym;
            do
            {
                sym = Decode(lc, ls);
                if (sym < 0) return sym;
                if (sym < 256) { if (!Put((byte)sym)) return 1; }
                else if (sym > 256)
                {
                    int s = sym - 257;
                    if (s >= 29) return -10;
                    int len = LBase[s] + Bits(LExt[s]);
                    int ds_ = Decode(dc, ds);
                    if (ds_ < 0) return ds_;
                    if (ds_ >= 30) return -10;
                    int dist = DBase[ds_] + Bits(DExt[ds_]);
                    if (err) return -1;
                    if (dist > OutLen) return -11;
                    for (int i = 0; i < len; i++) if (!Put(Out[OutLen - dist])) return 1;
                }
            } while (sym != 256);
            return 0;
        }

        int Dynamic()
        {
            int nlen = Bits(5) + 257, ndist = Bits(5) + 1, ncode = Bits(4) + 4;
            if (err) return -1;
            if (nlen > 286 || ndist > 30) return -3;
            int index;
            for (index = 0; index < ncode; index++) lengths[Order[index]] = (short)Bits(3);
            for (; index < 19; index++) lengths[Order[index]] = 0;
            if (err) return -1;
            if (Construct(lenCount, lenSym, lengths, 19, offs) != 0) return -4;
            index = 0;
            while (index < nlen + ndist)
            {
                int sym = Decode(lenCount, lenSym), len;
                if (sym < 0) return sym;
                if (sym < 16) { lengths[index++] = (short)sym; continue; }
                len = 0;
                if (sym == 16) { if (index == 0) return -5; len = lengths[index - 1]; sym = 3 + Bits(2); }
                else if (sym == 17) sym = 3 + Bits(3);
                else sym = 11 + Bits(7);
                if (err) return -1;
                if (index + sym > nlen + ndist) return -6;
                while (sym-- > 0) lengths[index++] = (short)len;
            }
            if (lengths[256] == 0) return -9;
            int e = Construct(lenCount, lenSym, lengths, nlen, offs);
            if (e < 0 || (e > 0 && nlen - lenCount[0] != 1)) return -7;
            short[] dl = new short[30];
            Array.Copy(lengths, nlen, dl, 0, ndist);
            e = Construct(distCount, distSym, dl, ndist, offs);
            if (e < 0 || (e > 0 && ndist - distCount[0] != 1)) return -8;
            return Codes(lenCount, lenSym, distCount, distSym);
        }

        // 0 = whole stream decoded (Pos = first byte after it), 1 = stopped by maxOut / scan check, <0 = not deflate
        public int Run(int start, int maxOut, bool scanMode)
        {
            pos = start; bitbuf = 0; bitcnt = 0; err = false; OutLen = 0; outMax = maxOut; scan = scanMode;
            int last, r;
            do
            {
                last = Bits(1);
                int type = Bits(2);
                if (err) return -1;
                if (type == 0) r = Stored();
                else if (type == 1) r = Codes(fixLenCount, fixLenSym, fixDistCount, fixDistSym);
                else if (type == 2) r = Dynamic();
                else r = -12;
                if (err) return -1;
                if (r != 0) return r;
            } while (last == 0);
            return 0;
        }

        public int Pos { get { return pos; } }
    }

    static bool Has(byte[] hay, int len, string needle)
    {
        byte[] n = Encoding.ASCII.GetBytes(needle);
        for (int i = 0; i + n.Length <= len; i++)
        {
            int j = 0;
            while (j < n.Length && hay[i + j] == n[j]) j++;
            if (j == n.Length) return true;
        }
        return false;
    }

    // ksuinit = the aarch64 executable among ksud's embedded files that loads kernelsu.ko and execs init.real
    public static byte[] ExtractKsuInit(byte[] ksud)
    {
        Inflater inf = new Inflater(ksud);
        byte[] found = null;
        for (int o = 0; o < ksud.Length - 64; o++)
        {
            if (((ksud[o] >> 1) & 3) == 3) continue;
            int r;
            try { r = inf.Run(o, 64, true); } catch (IndexOutOfRangeException) { continue; }
            if (r != 1 || inf.OutLen < 64) continue;
            byte[] h = inf.Out;
            if (h[4] != 2 || h[5] != 1 || (h[16] != 2 && h[16] != 3) || h[17] != 0 || h[18] != 0xb7 || h[19] != 0) continue;
            try { r = inf.Run(o, 64 << 20, false); } catch (IndexOutOfRangeException) { continue; }
            if (r != 0) continue;
            int n = inf.OutLen;
            long shoff = BitConverter.ToInt64(inf.Out, 40);
            int shentsize = BitConverter.ToUInt16(inf.Out, 58), shnum = BitConverter.ToUInt16(inf.Out, 60);
            if (shoff + (long)shentsize * shnum != n) continue;
            if (Has(inf.Out, n, "init.real") && Has(inf.Out, n, "kernelsu.ko"))
            {
                byte[] x = new byte[n];
                Array.Copy(inf.Out, x, n);
                if (found != null && !Equal(found, x)) throw new Exception("ksud contains more than one ksuinit candidate");
                found = x;
            }
            o = inf.Pos - 1;
        }
        if (found == null) throw new Exception("ksuinit not found inside ksud");
        return found;
    }

    static bool Equal(byte[] a, byte[] b)
    {
        if (a.Length != b.Length) return false;
        for (int i = 0; i < a.Length; i++) if (a[i] != b[i]) return false;
        return true;
    }

    // ---- LZ4 legacy frame (what the kernel unpacks for the init_boot ramdisk)
    const uint Lz4LegacyMagic = 0x184C2102;
    const int Lz4LegacyBlock = 8 << 20;

    static byte[] Lz4LegacyDecompress(byte[] src)
    {
        MemoryStream ms = new MemoryStream();
        byte[] blk = new byte[Lz4LegacyBlock];
        int p = 4;
        while (p + 4 <= src.Length)
        {
            uint c = BitConverter.ToUInt32(src, p); p += 4;
            if (c == Lz4LegacyMagic) continue;
            if (c > src.Length - p) throw new Exception("lz4: truncated block");
            int n = Lz4DecodeBlock(src, p, p + (int)c, blk);
            ms.Write(blk, 0, n);
            p += (int)c;
        }
        return ms.ToArray();
    }

    static int Lz4DecodeBlock(byte[] s, int sp, int send, byte[] d)
    {
        int dp = 0;
        while (sp < send)
        {
            int token = s[sp++], b;
            int lit = token >> 4;
            if (lit == 15) do { b = s[sp++]; lit += b; } while (b == 255);
            if (sp + lit > send || dp + lit > d.Length) throw new Exception("lz4: bad literal run");
            Buffer.BlockCopy(s, sp, d, dp, lit); sp += lit; dp += lit;
            if (sp >= send) break;
            int off = s[sp] | s[sp + 1] << 8; sp += 2;
            if (off == 0 || off > dp) throw new Exception("lz4: bad match offset");
            int ml = token & 15;
            if (ml == 15) do { b = s[sp++]; ml += b; } while (b == 255);
            ml += 4;
            if (dp + ml > d.Length) throw new Exception("lz4: block too large");
            for (int i = 0; i < ml; i++, dp++) d[dp] = d[dp - off];
        }
        return dp;
    }

    static byte[] Lz4LegacyCompress(byte[] src)
    {
        MemoryStream ms = new MemoryStream();
        ms.Write(BitConverter.GetBytes(Lz4LegacyMagic), 0, 4);
        byte[] dst = new byte[Lz4LegacyBlock + Lz4LegacyBlock / 255 + 64];
        for (int p = 0; p < src.Length; p += Lz4LegacyBlock)
        {
            int n = Lz4EncodeBlock(src, p, Math.Min(Lz4LegacyBlock, src.Length - p), dst);
            ms.Write(BitConverter.GetBytes(n), 0, 4);
            ms.Write(dst, 0, n);
        }
        return ms.ToArray();
    }

    static void WriteLen(byte[] d, ref int op, int v)
    {
        while (v >= 255) { d[op++] = 255; v -= 255; }
        d[op++] = (byte)v;
    }

    // greedy LZ4 block encoder; keeps the format rules (last 5 bytes literal, no match in the last 12)
    static int Lz4EncodeBlock(byte[] s, int start, int len, byte[] d)
    {
        int[] table = new int[1 << 16];
        int ip = start, anchor = start, iend = start + len, mflimit = iend - 12, matchlimit = iend - 5, op = 0;
        while (ip < mflimit)
        {
            uint seq = BitConverter.ToUInt32(s, ip);
            int h = (int)(unchecked(seq * 2654435761u) >> 16);
            int r = table[h] - 1;
            table[h] = ip + 1;
            if (r < start || ip - r > 65535 || BitConverter.ToUInt32(s, r) != seq) { ip++; continue; }
            int ml = 4;
            while (ip + ml < matchlimit && s[ip + ml] == s[r + ml]) ml++;
            int lit = ip - anchor, tok = op++;
            if (lit >= 15) WriteLen(d, ref op, lit - 15);
            Buffer.BlockCopy(s, anchor, d, op, lit); op += lit;
            int off = ip - r;
            d[op++] = (byte)off; d[op++] = (byte)(off >> 8);
            if (ml - 4 >= 15) WriteLen(d, ref op, ml - 4 - 15);
            d[tok] = (byte)((Math.Min(lit, 15) << 4) | Math.Min(ml - 4, 15));
            ip += ml; anchor = ip;
        }
        int last = iend - anchor, t = op++;
        if (last >= 15) WriteLen(d, ref op, last - 15);
        Buffer.BlockCopy(s, anchor, d, op, last); op += last;
        d[t] = (byte)(Math.Min(last, 15) << 4);
        return op;
    }

    // ---- cpio newc, written the way magiskboot/ksud do (sorted, inodes from 300000, mtime 0)
    sealed class Entry { public uint Mode, Uid, Gid, RdevMajor, RdevMinor; public byte[] Data; }

    static uint Hex(byte[] b, int p) { return Convert.ToUInt32(Encoding.ASCII.GetString(b, p, 8), 16); }
    static int Align4(int v) { return (v + 3) & ~3; }

    static SortedDictionary<string, Entry> CpioParse(byte[] c)
    {
        SortedDictionary<string, Entry> m = new SortedDictionary<string, Entry>(StringComparer.Ordinal);
        int p = 0;
        while (true)
        {
            if (p + 110 > c.Length) throw new Exception("cpio: truncated");
            string magic = Encoding.ASCII.GetString(c, p, 6);
            if (magic != "070701" && magic != "070702") throw new Exception("ramdisk is not a newc cpio archive");
            int nsize = (int)Hex(c, p + 94), fsize = (int)Hex(c, p + 54);
            string name = Encoding.UTF8.GetString(c, p + 110, nsize - 1);
            int dp = Align4(p + 110 + nsize);
            if (name == "TRAILER!!!") break;
            Entry e = new Entry();
            e.Mode = Hex(c, p + 14); e.Uid = Hex(c, p + 22); e.Gid = Hex(c, p + 30);
            e.RdevMajor = Hex(c, p + 78); e.RdevMinor = Hex(c, p + 86);
            e.Data = new byte[fsize];
            Array.Copy(c, dp, e.Data, 0, fsize);
            if (name != "." && name != "..") m[name] = e;
            p = Align4(dp + fsize);
        }
        return m;
    }

    static void CpioHeader(MemoryStream ms, uint ino, uint mode, uint uid, uint gid, int size, uint rmaj, uint rmin, string name)
    {
        byte[] nb = Encoding.UTF8.GetBytes(name);
        string h = string.Format("070701{0:x8}{1:x8}{2:x8}{3:x8}{4:x8}{5:x8}{6:x8}{7:x8}{8:x8}{9:x8}{10:x8}{11:x8}{12:x8}",
            ino, mode, uid, gid, 1, 0, size, 0, 0, rmaj, rmin, nb.Length + 1, 0);
        byte[] hb = Encoding.ASCII.GetBytes(h);
        ms.Write(hb, 0, hb.Length);
        ms.Write(nb, 0, nb.Length);
        ms.WriteByte(0);
        while (ms.Length % 4 != 0) ms.WriteByte(0);
    }

    static byte[] CpioDump(SortedDictionary<string, Entry> m)
    {
        MemoryStream ms = new MemoryStream();
        uint ino = 300000;
        foreach (KeyValuePair<string, Entry> kv in m)
        {
            Entry e = kv.Value;
            CpioHeader(ms, ino++, e.Mode, e.Uid, e.Gid, e.Data.Length, e.RdevMajor, e.RdevMinor, kv.Key);
            ms.Write(e.Data, 0, e.Data.Length);
            while (ms.Length % 4 != 0) ms.WriteByte(0);
        }
        CpioHeader(ms, ino, 0x1ed, 0, 0, 0, 0, 0, "TRAILER!!!");
        return ms.ToArray();
    }

    static Entry Regular(uint perm, byte[] data)
    {
        Entry e = new Entry();
        e.Mode = 0x8000 | perm; e.Data = data;
        return e;
    }

    // ---- boot image v3/v4 (init_boot): header page, kernel (none), ramdisk, boot signature, AVB footer
    static uint U32(byte[] b, int p) { return BitConverter.ToUInt32(b, p); }
    static int AlignPage(long v) { return (int)((v + 4095) & ~4095L); }
    static ulong BE64(byte[] b, int p) { ulong v = 0; for (int i = 0; i < 8; i++) v = v << 8 | b[p + i]; return v; }
    static void PutBE64(byte[] b, int p, ulong v) { for (int i = 7; i >= 0; i--) { b[p + i] = (byte)v; v >>= 8; } }

    public static byte[] PatchInitBoot(byte[] img, byte[] ksuinit, byte[] ko, out string report)
    {
        StringBuilder log = new StringBuilder();
        if (img.Length < 4096 || Encoding.ASCII.GetString(img, 0, 8) != "ANDROID!") throw new Exception("init_boot.img is not an Android boot image");
        uint ver = U32(img, 40);
        if (ver != 3 && ver != 4) throw new Exception("boot image header v" + ver + " is not supported (v3/v4 expected)");
        int ksize = (int)U32(img, 8), rsize = (int)U32(img, 12), sigsize = ver == 4 ? (int)U32(img, 1580) : 0;
        int roff = 4096 + AlignPage(ksize), sigoff = roff + AlignPage(rsize);
        int dataEnd = sigoff + AlignPage(sigsize);
        if (rsize == 0 || dataEnd > img.Length) throw new Exception("init_boot.img has no ramdisk or is truncated");

        bool avb = Encoding.ASCII.GetString(img, img.Length - 64, 4) == "AVBf";
        int vboff = 0, vbsize = 0;
        if (avb)
        {
            ulong orig = BE64(img, img.Length - 52), vo = BE64(img, img.Length - 44), vs = BE64(img, img.Length - 36);
            if (orig != (ulong)dataEnd || vo + vs > (ulong)img.Length - 64) throw new Exception("unexpected AVB footer layout");
            vboff = (int)vo; vbsize = (int)vs;
        }

        byte[] rd = new byte[rsize];
        Array.Copy(img, roff, rd, 0, rsize);
        bool lz4 = U32(rd, 0) == Lz4LegacyMagic;
        if (!lz4 && Encoding.ASCII.GetString(rd, 0, 6) != "070701") throw new Exception("ramdisk compression is not lz4 legacy");
        SortedDictionary<string, Entry> cpio = CpioParse(lz4 ? Lz4LegacyDecompress(rd) : rd);

        foreach (string m in new string[] { ".backup/.magisk", "init.magisk.rc", "overlay/init.magisk.rc" })
            if (cpio.ContainsKey(m)) throw new Exception("init_boot.img is Magisk patched, use the port's stock init_boot.img");

        if (cpio.ContainsKey("kernelsu.ko")) log.AppendLine("- init_boot already has KernelSU, updating it");
        else
        {
            if (!cpio.ContainsKey("init")) throw new Exception("ramdisk has no /init");
            cpio["init.real"] = cpio["init"];
            cpio.Remove("init");
        }
        cpio["init"] = Regular(0x1ed, ksuinit);
        cpio["kernelsu.ko"] = Regular(0x1ed, ko);

        List<string> cfg = new List<string>();
        Entry old;
        if (cpio.TryGetValue("ksu_config", out old))
            foreach (string t in Encoding.UTF8.GetString(old.Data).Split(new char[] { ' ', '\n', '\t', '\r' }, StringSplitOptions.RemoveEmptyEntries))
                if (!t.StartsWith("bundled=")) cfg.Add(t);
        cfg.Add("bundled=1");
        cpio["ksu_config"] = Regular(0x1a4, Encoding.UTF8.GetBytes(string.Join(" ", cfg.ToArray())));
        cpio.Remove("allow_shell");

        byte[] newCpio = CpioDump(cpio);
        byte[] newRd = lz4 ? Lz4LegacyCompress(newCpio) : newCpio;
        log.AppendLine(string.Format("- ramdisk {0} -> {1} bytes ({2} uncompressed)", rsize, newRd.Length, newCpio.Length));

        int newSigoff = roff + AlignPage(newRd.Length), newEnd = newSigoff + AlignPage(sigsize);
        int outLen = avb ? img.Length : newEnd;
        if (avb && newEnd + vbsize > img.Length - 64) throw new Exception("patched init_boot does not fit in the partition");
        byte[] o = new byte[outLen];
        Array.Copy(img, 0, o, 0, roff);
        Array.Copy(BitConverter.GetBytes(newRd.Length), 0, o, 12, 4);
        Array.Copy(newRd, 0, o, roff, newRd.Length);
        Array.Copy(img, sigoff, o, newSigoff, sigsize);
        if (avb)
        {
            Array.Copy(img, vboff, o, newEnd, vbsize);
            Array.Copy(img, img.Length - 64, o, o.Length - 64, 64);
            PutBE64(o, o.Length - 52, (ulong)newEnd);
            PutBE64(o, o.Length - 44, (ulong)newEnd);
        }

        // read the result back the way the bootloader/kernel will
        SortedDictionary<string, Entry> check = CpioParse(lz4 ? Lz4LegacyDecompress(newRd) : newRd);
        if (!Equal(check["init"].Data, ksuinit) || !Equal(check["kernelsu.ko"].Data, ko) || !check.ContainsKey("init.real") || check.Count != cpio.Count)
            throw new Exception("self-check of the patched ramdisk failed");
        report = log.ToString();
        return o;
    }
}
'@

if ($Action -eq 'download') {
    New-Item -ItemType Directory -Force $ksuDir | Out-Null
    $kmi = Get-Kmi
    $koName = "aarch64_$($kmi)_kernelsu.ko"
    $ko = Join-Path $ksuDir $koName
    $have = (Test-Path $ksuinit) -and (Test-Path $ko) -and (Test-Path $apk)
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $rel = Invoke-RestMethod -Uri 'https://api.github.com/repos/KernelSU-Next/KernelSU-Next/releases/latest' `
            -Headers @{ 'User-Agent' = 'nord6-port-flasher' } -UseBasicParsing
    } catch {
        if ($have) {
            Write-Host "Could not reach GitHub ($($_.Exception.Message))."
            Write-Host "Using the copy downloaded earlier: KernelSU Next $(Get-Content $verFile -ErrorAction SilentlyContinue)"
            exit 0
        }
        Fail "could not reach GitHub to get KernelSU Next: $($_.Exception.Message)"
    }
    $tag = $rel.tag_name
    if ($have -and (Test-Path $verFile) -and ((Get-Content $verFile) -eq $tag)) {
        Write-Host "KernelSU Next $tag already downloaded."
        exit 0
    }
    Write-Host "Downloading KernelSU Next $tag (kernel module for KMI $kmi) ..."
    Remove-Item -Force -ErrorAction SilentlyContinue $verFile
    Save-Asset (Get-Asset $rel "^$([regex]::Escape($koName))$") $ko
    # the plain manager, not the "-spoofed" build
    Save-Asset (Get-Asset $rel '^KernelSU_Next_v[0-9.]+_[0-9]+-release\.apk$') $apk
    # ksuinit (the /init that loads kernelsu.ko) is only shipped inside ksud
    $ksud = Join-Path $ksuDir 'ksud-aarch64-linux-android'
    Save-Asset (Get-Asset $rel '^ksud-aarch64-linux-android$') $ksud
    Add-Type -TypeDefinition $patcherSrc -Language CSharp
    try { $init = [KsuPatcher]::ExtractKsuInit([IO.File]::ReadAllBytes($ksud)) } catch { Fail (Inner $_) }
    [IO.File]::WriteAllBytes($ksuinit, $init)
    Remove-Item -Force $ksud
    Set-Content -Path $verFile -Value $tag
    Write-Host "KernelSU Next $tag saved in the ksu folder."
    exit 0
}

if ($Action -eq 'install') {
    if (-not (Test-Path $apk)) { Fail 'ksu\KernelSU_Next.apk is missing, run the download step first' }
    Write-Host 'Installing the KernelSU Next manager app ...'
    $ErrorActionPreference = 'Continue'
    $out = & $adb install -r $apk 2>&1 | ForEach-Object { "$_" } | Out-String
    Write-Host $out.Trim()
    if ($LASTEXITCODE -ne 0) { exit 1 }
    exit 0
}

# ---- patch
$ib = Join-Path $here 'init_boot.img'
$outImg = Join-Path $here 'init_boot_ksu.img'
if (-not (Test-Path $ib)) { Fail 'init_boot.img is missing from this folder' }
$kmi = Get-Kmi
$ko = Join-Path $ksuDir "aarch64_$($kmi)_kernelsu.ko"
if (-not (Test-Path $ksuinit) -or -not (Test-Path $ko)) { Fail 'KernelSU Next files are missing from the ksu folder, run the download step first' }
Write-Host "Patching init_boot.img with KernelSU Next $(Get-Content $verFile -ErrorAction SilentlyContinue) (KMI $kmi) ..."
Add-Type -TypeDefinition $patcherSrc -Language CSharp
$report = ''
try {
    $img = [KsuPatcher]::PatchInitBoot([IO.File]::ReadAllBytes($ib), [IO.File]::ReadAllBytes($ksuinit), [IO.File]::ReadAllBytes($ko), [ref]$report)
} catch { Fail (Inner $_) }
Write-Host $report.TrimEnd()
[IO.File]::WriteAllBytes($outImg, $img)
Write-Host "Patched image saved as init_boot_ksu.img."
exit 0
