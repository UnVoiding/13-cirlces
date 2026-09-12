#!/usr/bin/env python3
"""Parses src/BaseMonster.cpp and generates a CSV listing every monster type
with empty columns for the corpse-leftover flags (bones/flesh/spirit/blood).

Usage: python tools/generate_corpse_data_csv.py
Output: doc/monster_corpse_data.csv
"""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "BaseMonster.cpp"
OUT = ROOT / "doc" / "monster_corpse_data.csv"

# Matches "..." strings, allowing escaped chars (e.g. \\) inside.
STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
ENTRY_START_RE = re.compile(r'^\{\s*(BM_\w+)\s*,\s*(\d+)\s*,')


def parse_entries(text: str):
    entries = []
    for line in text.splitlines():
        line = line.strip()
        m = ENTRY_START_RE.match(line)
        if not m:
            continue
        monster_id, valid = m.group(1), m.group(2)

        # Strip block comments so commented-out fields (e.g. old TRN paths)
        # don't get picked up as the display name.
        clean_line = re.sub(r"/\*.*?\*/", "", line)

        # File-path strings always contain a backslash; the display name
        # and IceAgeNamePtr never do, so filtering on that isolates them.
        candidates = [s for s in STRING_RE.findall(clean_line) if "\\" not in s]
        if not candidates:
            continue
        name = candidates[0]

        entries.append({
            "id": monster_id,
            "valid": valid,
            "name": name,
        })
    return entries


def main():
    text = SRC.read_text(encoding="utf-8-sig")
    entries = parse_entries(text)

    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Name", "UsedAsRandomSpawn", "Bones", "Flesh", "Spirit", "Blood"])
        for e in entries:
            writer.writerow([
                e["id"],
                e["name"],
                "yes" if e["valid"] == "1" else "no (unique-only base)",
                "", "", "", "",
            ])

    print(f"Parsed {len(entries)} monster entries -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
