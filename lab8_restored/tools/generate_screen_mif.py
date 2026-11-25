#!/usr/bin/env python3
"""Convert an 80-by-30 printable ASCII screen into a Quartus MIF."""

import argparse
from pathlib import Path

COLUMNS = 80
ROWS = 30
PROJECT = Path(__file__).resolve().parent.parent


def encode_screen(source: Path) -> str:
    raw = source.read_bytes().replace(b"\r\n", b"\n")
    rows = raw.removesuffix(b"\n").split(b"\n")
    if len(rows) != ROWS:
        raise ValueError(f"{source}: expected {ROWS} rows, found {len(rows)}")
    for number, row in enumerate(rows, start=1):
        if len(row) != COLUMNS:
            raise ValueError(f"{source}:{number}: expected {COLUMNS} bytes, found {len(row)}")
        if any(byte < 0x20 or byte > 0x7E for byte in row):
            raise ValueError(f"{source}:{number}: characters must be printable ASCII")

    lines = [
        f"DEPTH = {COLUMNS * ROWS};",
        "WIDTH = 8;",
        "ADDRESS_RADIX = HEX;",
        "DATA_RADIX = HEX;",
        "CONTENT BEGIN",
    ]
    for row_number, row in enumerate(rows):
        lines.append(f"    -- Screen row {row_number}")
        for col, byte in enumerate(row):
            address = row_number * COLUMNS + col
            lines.append(f"    {address:03X} : {byte:02X};")
    lines.append("END;")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=PROJECT / "superface_screen.txt")
    parser.add_argument("target", nargs="?", type=Path, default=PROJECT / "superface_screen.mif")
    args = parser.parse_args()
    try:
        args.target.write_text(encode_screen(args.source), encoding="ascii")
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
