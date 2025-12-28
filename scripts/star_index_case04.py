#!/usr/bin/env python3
import argparse
import hashlib
import struct
from datetime import datetime, timezone

MAGIC = b"STARIDX04\x00"
VERSION_U32 = 4
FLAG_OFFSETS_PRESENT = 1

def sha256_file(path, chunk_size=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def fmt_epoch_minutes(t_min):
    try:
        sec = int(t_min) * 60
        dt = datetime.fromtimestamp(sec, tz=timezone.utc)
        return dt.isoformat()
    except Exception:
        return str(t_min)

def build_anchors(rows, cadence_min, anchor_every):
    anchors = []
    for r in range(0, rows, anchor_every):
        anchors.append((r, r * cadence_min))
    last_row = rows - 1
    if anchors and anchors[-1][0] != last_row:
        anchors.append((last_row, last_row * cadence_min))
    if not anchors and rows > 0:
        anchors.append((0, 0))
    return anchors

def write_index(path_out, anchor_every, anchors, star_sha256_hex, cadence_min):
    star_sha_raw = bytes.fromhex(star_sha256_hex)
    flags = 0

    with open(path_out, "wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<I", int(VERSION_U32)))
        f.write(struct.pack("<I", int(anchor_every)))
        f.write(struct.pack("<I", int(len(anchors))))
        f.write(struct.pack("<I", int(flags)))
        f.write(struct.pack("<q", int(cadence_min)))
        f.write(star_sha_raw)

        for (row, t_min) in anchors:
            f.write(struct.pack("<I", int(row)))
            f.write(struct.pack("<q", int(t_min)))
            f.write(struct.pack("<Q", 0))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--star", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--anchor_every", type=int, default=256)
    ap.add_argument("--rows", type=int, required=True)
    ap.add_argument("--cad", type=int, default=1)
    args = ap.parse_args()

    if args.rows <= 0:
        raise SystemExit("ERROR: --rows must be > 0")
    if args.anchor_every <= 0:
        raise SystemExit("ERROR: --anchor_every must be > 0")
    if args.cad <= 0:
        raise SystemExit("ERROR: --cad must be > 0")

    star_sha = sha256_file(args.star)
    anchors = build_anchors(args.rows, args.cad, args.anchor_every)
    write_index(args.out, args.anchor_every, anchors, star_sha, args.cad)

    print(f"STAR: {args.star}")
    print(f"Rows: {args.rows}")
    print(f"Cadence: {args.cad} minute(s) per row")
    print(f"Index written: {args.out}")
    print(f"Anchors: {len(anchors)} (every {args.anchor_every} rows, plus last-row anchor)")
    print("Index binding:")
    print(f"  sha256(star): {star_sha}")
    print("Preview (first 5 anchors):")
    for (row, t_min) in anchors[:5]:
        print(f"  row={row:<10} t_min={t_min:<12} {fmt_epoch_minutes(t_min)}")

if __name__ == "__main__":
    main()
