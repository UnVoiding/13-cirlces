"""Lists the contents of a Diablo-era MPQ archive by reading its "(listfile)".

tools\\mpq_extract.exe can only pull files stored raw or PKWARE-imploded, which is all the
game's own Storm needs.  The "(listfile)" inside TH4data.mor is encrypted and zlib-deflated
instead, so it needs a reader that handles the general case - hence this script.  It only
reads; use tools\\make_mpq.py to build an archive and mpq_extract.exe to pull files out.

usage: python tools/mpq_list.py <archive.mpq> [name-filter ...]
       name-filter is a case-insensitive substring; with none given every name is printed
"""
import fnmatch
import os
import struct
import sys
import zlib

MPQ_FILE_IMPLODE     = 0x00000100
MPQ_FILE_COMPRESS    = 0x00000200
MPQ_FILE_ENCRYPTED   = 0x00010000
MPQ_FILE_FIX_KEY     = 0x00020000
MPQ_FILE_SINGLE_UNIT = 0x01000000
MPQ_FILE_EXISTS      = 0x80000000


def make_crypt_table():
    table = [0] * 0x500
    seed = 0x00100001
    for index1 in range(0x100):
        index2 = index1
        for _ in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            temp1 = (seed & 0xFFFF) << 16
            seed = (seed * 125 + 3) % 0x2AAAAB
            temp2 = seed & 0xFFFF
            table[index2] = temp1 | temp2
            index2 += 0x100
    return table


CRYPT = make_crypt_table()


def hash_string(text, hash_type):
    seed1, seed2 = 0x7FED7FED, 0xEEEEEEEE
    for ch in text.upper().replace('/', '\\'):
        c = ord(ch)
        seed1 = CRYPT[hash_type * 0x100 + c] ^ ((seed1 + seed2) & 0xFFFFFFFF)
        seed2 = (c + seed1 + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return seed1


def decrypt(data, key):
    out = bytearray(data)
    seed = 0xEEEEEEEE
    for i in range(0, len(out) & ~3, 4):
        seed = (seed + CRYPT[0x400 + (key & 0xFF)]) & 0xFFFFFFFF
        cipher = struct.unpack_from('<I', out, i)[0]
        plain = cipher ^ ((key + seed) & 0xFFFFFFFF)
        key = ((((~key & 0xFFFFFFFF) << 0x15) + 0x11111111) | (key >> 0x0B)) & 0xFFFFFFFF
        seed = (plain + seed + (seed << 5) + 3) & 0xFFFFFFFF
        struct.pack_into('<I', out, i, plain)
    return bytes(out)


def decompress(data):
    """Multi-compression sector: a mask byte says what was applied."""
    mask, body = data[0], data[1:]
    if mask & 0x02:
        return zlib.decompress(body)
    raise SystemExit('unsupported compression mask 0x%02X (only zlib is implemented here - '
                     'use tools\\mpq_extract.exe for PKWARE-imploded files)' % mask)


class Archive:
    def __init__(self, path):
        self.f = open(path, 'rb')
        blob = self.f.read(0x200)
        self.base = blob.find(b'MPQ\x1a')       # some archives carry a header before the MPQ
        if self.base < 0:
            raise SystemExit('%s: no MPQ header found' % path)
        (_magic, _hdr, _size, _ver, self.sector_shift, hash_pos, block_pos,
         hash_count, block_count) = struct.unpack_from('<4sIIHHIIII', blob, self.base)
        self.hash_table = self._table(self.base + hash_pos, hash_count * 16, '(hash table)')
        self.block_table = self._table(self.base + block_pos, block_count * 16, '(block table)')
        self.hash_count = hash_count

    def _table(self, pos, size, key_name):
        self.f.seek(pos)
        return decrypt(self.f.read(size), hash_string(key_name, 3))

    def find(self, name):
        start = hash_string(name, 0) % self.hash_count
        a, b = hash_string(name, 1), hash_string(name, 2)
        for i in range(self.hash_count):
            slot = (start + i) % self.hash_count
            n1, n2, _loc, _plat, block = struct.unpack_from('<IIHHI', self.hash_table, slot * 16)
            if block == 0xFFFFFFFF:
                return None
            if n1 == a and n2 == b and block != 0xFFFFFFFE:
                return block
        return None

    def read(self, name):
        block = self.find(name)
        if block is None:
            return None
        pos, csize, fsize, flags = struct.unpack_from('<IIII', self.block_table, block * 16)
        if not flags & MPQ_FILE_EXISTS:
            return None
        pos += self.base
        key = hash_string(name.split('\\')[-1], 3)
        if flags & MPQ_FILE_FIX_KEY:
            key = ((key + (pos - self.base)) ^ fsize) & 0xFFFFFFFF
        compressed = flags & (MPQ_FILE_COMPRESS | MPQ_FILE_IMPLODE)
        self.f.seek(pos)
        if flags & MPQ_FILE_SINGLE_UNIT:
            raw = self.f.read(csize)
            if flags & MPQ_FILE_ENCRYPTED:
                raw = decrypt(raw, key)
            return decompress(raw) if compressed and csize < fsize else raw[:fsize]

        sector_size = 512 << self.sector_shift
        count = (fsize + sector_size - 1) // sector_size
        if not compressed:
            raw = self.f.read(csize)
            if flags & MPQ_FILE_ENCRYPTED:
                raw = decrypt(raw, key)
            return raw[:fsize]

        table = self.f.read((count + 1) * 4)
        if flags & MPQ_FILE_ENCRYPTED:
            table = decrypt(table, (key - 1) & 0xFFFFFFFF)
        offsets = struct.unpack_from('<%dI' % (count + 1), table, 0)
        out = bytearray()
        for i in range(count):
            self.f.seek(pos + offsets[i])
            chunk = self.f.read(offsets[i + 1] - offsets[i])
            if flags & MPQ_FILE_ENCRYPTED:
                chunk = decrypt(chunk, (key + i) & 0xFFFFFFFF)
            plain_size = min(sector_size, fsize - len(out))
            out += chunk[:plain_size] if len(chunk) >= plain_size else decompress(chunk)
        return bytes(out[:fsize])


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    mpq = Archive(sys.argv[1])
    data = mpq.read('(listfile)')
    if data is None:
        print('%s has no (listfile) - names cannot be recovered from an MPQ without one'
              % sys.argv[1])
        return 2
    names = sorted(set(n.strip() for n in data.decode('latin-1').replace('\r', '\n').split('\n') if n.strip()))
    filters = [f.lower() for f in sys.argv[2:]]
    shown = [n for n in names if not filters or any(f in n.lower() or fnmatch.fnmatch(n.lower(), f) for f in filters)]
    for n in shown:
        print(n)
    print('# %d of %d entries' % (len(shown), len(names)), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
