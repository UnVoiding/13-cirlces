"""Builds a small MPQ archive out of a directory tree.

Used to pack the mod's own interface assets (see res\\13cirlces) into an archive the game
opens next to DIABDAT.MPQ.  Files are stored uncompressed - exactly the way the existing
thehell2.mpq stores its entries - so the game's own Storm implementation reads them back
without needing any compression support.

usage: python tools/make_mpq.py <source-dir> <out.mpq>
       every file under <source-dir> is added under its relative path (backslashes)
"""
import os
import struct
import sys

MPQ_FILE_EXISTS = 0x80000000
SECTOR_SHIFT = 3   # 512 << 3 = 4096 byte sectors
HASH_TABLE_SIZE = 16


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


def encrypt(data, key):
    out = bytearray()
    seed = 0xEEEEEEEE
    for i in range(0, len(data), 4):
        seed = (seed + CRYPT[0x400 + (key & 0xFF)]) & 0xFFFFFFFF
        plain = struct.unpack_from('<I', data, i)[0]
        cipher = plain ^ ((key + seed) & 0xFFFFFFFF)
        key = ((((~key & 0xFFFFFFFF) << 0x15) + 0x11111111) | (key >> 0x0B)) & 0xFFFFFFFF
        seed = (plain + seed + (seed << 5) + 3) & 0xFFFFFFFF
        out += struct.pack('<I', cipher)
    return bytes(out)


def collect(source_dir):
    entries = []
    for root, _dirs, files in os.walk(source_dir):
        for name in sorted(files):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, source_dir).replace('/', '\\')
            entries.append((rel, open(full, 'rb').read()))
    return entries


def listfile(entries):
    """The archive's own table of contents, under the conventional name '(listfile)'.

    An MPQ stores only the *hash* of each file name, so without this an archive cannot be
    enumerated at all - a tool can check whether a name it already knows is present, but it can
    never recover the names.  One path per line, backslash separated, CRLF terminated, which is
    what every MPQ tool expects.  The listfile does not name itself; readers know to look for it.
    """
    return ('\r\n'.join(name for name, _data in entries) + '\r\n').encode('ascii')


def build(entries):
    if len(entries) > HASH_TABLE_SIZE:
        raise SystemExit('too many files for a %d entry hash table' % HASH_TABLE_SIZE)

    body = bytearray()
    blocks = []
    for _name, data in entries:
        blocks.append((32 + len(body), len(data), len(data), MPQ_FILE_EXISTS))
        body += data

    hash_table = bytearray()
    for _ in range(HASH_TABLE_SIZE):
        hash_table += struct.pack('<IIHHI', 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFF, 0xFFFF, 0xFFFFFFFF)
    for block_index, (name, _data) in enumerate(entries):
        slot = hash_string(name, 0) % HASH_TABLE_SIZE
        while struct.unpack_from('<I', hash_table, slot * 16 + 12)[0] != 0xFFFFFFFF:
            slot = (slot + 1) % HASH_TABLE_SIZE
        struct.pack_into('<IIHHI', hash_table, slot * 16,
                         hash_string(name, 1), hash_string(name, 2), 0, 0, block_index)

    block_table = bytearray()
    for pos, csize, fsize, flags in blocks:
        block_table += struct.pack('<IIII', pos, csize, fsize, flags)

    hash_pos = 32 + len(body)
    block_pos = hash_pos + len(hash_table)
    archive_size = block_pos + len(block_table)
    header = struct.pack('<4sIIHHIIII', b'MPQ\x1a', 32, archive_size, 0, SECTOR_SHIFT,
                         hash_pos, block_pos, HASH_TABLE_SIZE, len(blocks))
    return (header + bytes(body)
            + encrypt(bytes(hash_table), hash_string('(hash table)', 3))
            + encrypt(bytes(block_table), hash_string('(block table)', 3)))


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    entries = collect(sys.argv[1])
    if not entries:
        print('no files found under %s' % sys.argv[1])
        return 1
    entries.append(('(listfile)', listfile(entries)))
    open(sys.argv[2], 'wb').write(build(entries))
    print('wrote %s' % sys.argv[2])
    for name, data in entries:
        print('  %s (%d bytes)' % (name, len(data)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
