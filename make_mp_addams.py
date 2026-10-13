#!/usr/bin/env python3
"""Build the MAME set mp_addams.zip (The Addams Family ARCADE, Sega Mega Play).

usage: python3 make_mp_addams.py <original ROM> <mp_sor2.zip> [out_dir]

  <original ROM>  The Addams Family (USA, Europe), Mega Drive / Genesis,
                  1 MB headerless, CRC32 71F58614
  <mp_sor2.zip>   your MAME set of Streets of Rage II (Mega Play)
  out_dir         default: current directory

Needs only Python 3 (standard library). The two IPS patches are looked for in
patches/ next to this script, or next to the script itself. No Sega code is distributed: the BIOS link routines and the
instruction-ROM base are taken from your own mp_sor2.zip.
"""
import hashlib, os, struct, sys, zipfile, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ORIG_CRC = 0x71F58614
SOR2_GAME_CRC = 0xCD6376AF   # mpr-15425.ic1
SOR2_INFO_CRC = 0x1DF5347C   # epr-15175-05.ic2
GAME_IPS = 'mp_addams_game.ips'
INFO_IPS = 'mp_addams_info.ips'
GAME_NAME, GAME_CRC = 'epr-26013.ic1', 0x87ECACE1
INFO_NAME, INFO_CRC = 'epr-15175-20.ic2', 0xDCFDE4E7

def die(msg): sys.exit('ERROR: ' + msg)

def swap16(b):
    b = bytearray(b); b[0::2], b[1::2] = b[1::2], b[0::2]; return bytes(b)

def ips_path(name):
    for d in (os.path.join(HERE, 'patches'), HERE):
        if os.path.isfile(os.path.join(d, name)): return os.path.join(d, name)
    die('%s not found (expected in patches/)' % name)

def apply_ips(data, path):
    p = open(path, 'rb').read()
    if p[:5] != b'PATCH': die('%s is not an IPS file' % path)
    out, i = bytearray(data), 5
    while p[i:i + 3] != b'EOF':
        off = int.from_bytes(p[i:i + 3], 'big'); n = int.from_bytes(p[i + 3:i + 5], 'big'); i += 5
        if n: chunk = p[i:i + n]; i += n
        else: chunk = p[i + 2:i + 3] * int.from_bytes(p[i:i + 2], 'big'); i += 3
        if off + len(chunk) > len(out): out.extend(bytes(off + len(chunk) - len(out)))
        out[off:off + len(chunk)] = chunk
    if len(p) == i + 6: del out[int.from_bytes(p[i + 3:i + 6], 'big'):]   # truncate extension
    return out

# BIOS link routines: Streets of Rage II 0x3AB28-0x3B0C0, relocated to 0x110000.
# Must match build_mp.py exactly. The 7 dispatcher-table entries that point to
# our own handlers are in the IPS and are left alone here.
S0, S1, G = 0x3AB28, 0x3B0C0, 0x110000
TABLE, OURS = 0x3AFE8, (4, 6, 8, 9, 10, 11, 12)
def glue_from(sor2):
    glue = bytearray(sor2[S0:S1])
    def gp(a, new, old):
        o = a - S0
        if glue[o:o + len(old)] != old: die('mp_sor2 game ROM: unexpected bytes at %06X' % a)
        glue[o:o + len(new)] = new
    for a in (0x3AB40, 0x3AB86, 0x3B094):
        gp(a + 2, struct.pack('>H', 0xF2E4), struct.pack('>H', 0xFD3A))
    gp(0x3B0B6 + 2, struct.pack('>H', 0xF2E8), struct.pack('>H', 0xFD3E))
    gp(0x3AF2E + 2, struct.pack('>I', 0x3AF48 - S0 + G), struct.pack('>I', 0x3AF48))
    gp(0x3AFCE + 2, struct.pack('>I', 0x3B01C - S0 + G), struct.pack('>I', 0x3B01C))
    gp(0x3AFC6, bytes.fromhex('4e714e71'), bytes.fromhex('610000b6'))
    keep = [True] * len(glue)
    for k in OURS:
        for j in range(4): keep[TABLE - S0 + 4 * k + j] = False
    return glue, keep

def main():
    a = sys.argv[1:]
    if len(a) not in (2, 3): sys.exit(__doc__)
    out_dir = a[2] if len(a) == 3 else '.'
    orig = open(a[0], 'rb').read()
    if len(orig) == 1048576 + 512: orig = orig[512:]          # copier header
    if zlib.crc32(orig) != ORIG_CRC:
        die('%s: CRC32 %08X, expected %08X (The Addams Family (USA, Europe), headerless .md/.bin)'
            % (a[0], zlib.crc32(orig), ORIG_CRC))
    with zipfile.ZipFile(a[1]) as z:
        files = {i.CRC: z.read(i) for i in z.infolist()}
    if SOR2_GAME_CRC not in files or SOR2_INFO_CRC not in files:
        die('%s does not hold the mp_sor2 ROMs (mpr-15425.ic1 / epr-15175-05.ic2)' % a[1])

    game = apply_ips(orig, ips_path(GAME_IPS))
    glue, keep = glue_from(swap16(files[SOR2_GAME_CRC]))
    for i, k in enumerate(keep):
        if k: game[G + i] = glue[i]
    game = swap16(game)                                         # MAME dumps are word-swapped
    info = bytes(apply_ips(files[SOR2_INFO_CRC], ips_path(INFO_IPS)))
    for name, data, crc in ((GAME_NAME, game, GAME_CRC), (INFO_NAME, info, INFO_CRC)):
        if zlib.crc32(data) != crc: die('%s came out wrong (CRC32 %08X)' % (name, zlib.crc32(data)))
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, 'mp_addams.zip')
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(GAME_NAME, game); z.writestr(INFO_NAME, info)
    print('%s written:' % dst)
    for name, data in ((GAME_NAME, game), (INFO_NAME, info)):
        print('  %-17s CRC32 %08x  SHA1 %s' % (name, zlib.crc32(data), hashlib.sha1(data).hexdigest()))

if __name__ == '__main__':
    main()
