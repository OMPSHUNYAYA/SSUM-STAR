#!/usr/bin/env python3
# STAR Case-03 Replay (Household Power)
# Reads STARIDX03 and resolves seek_row / seek_time deterministically.
# Offsetless index: anchor offsets are 0; replay prints logical mapping (row->t_min).

import argparse
import hashlib
import os
import struct
from datetime import datetime, timedelta, timezone

MAGIC_A = b"STARIDX03\x00"  # preferred
MAGIC_B = b"STARIDX03"      # tolerated (older writer)

FLAG_OFFSETS_PRESENT = 1


def sha256_file(path, chunk=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def fmt_epoch_minutes(t_min):
    dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=int(t_min))
    return dt.strftime("%Y-%m-%dT%H:%MZ")


def fmt_base_minutes(t_min, base_iso):
    # Optional: real dataset base, eg "2006-12-16T17:24:00"
    base = datetime.fromisoformat(base_iso).replace(tzinfo=timezone.utc)
    dt = base + timedelta(minutes=int(t_min))
    return dt.strftime("%Y-%m-%dT%H:%MZ")


def load_index(path_idx):
    with open(path_idx, "rb") as f:
        buf = f.read()

    if buf.startswith(MAGIC_A):
        pos = len(MAGIC_A)
        magic = MAGIC_A
    elif buf.startswith(MAGIC_B):
        pos = len(MAGIC_B)
        magic = MAGIC_B
    else:
        raise ValueError("bad idx magic")

    # header
    version = struct.unpack_from("<I", buf, pos)[0]; pos += 4
    anchor_every = struct.unpack_from("<I", buf, pos)[0]; pos += 4
    n = struct.unpack_from("<I", buf, pos)[0]; pos += 4
    flags = struct.unpack_from("<I", buf, pos)[0]; pos += 4
    cadence_min = struct.unpack_from("<q", buf, pos)[0]; pos += 8
    star_sha_raw = buf[pos:pos+32]; pos += 32
    star_sha_hex = star_sha_raw.hex()

    offsets_present = (flags & FLAG_OFFSETS_PRESENT) != 0

    anchors = []
    for _ in range(int(n)):
        row = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        t_min = struct.unpack_from("<q", buf, pos)[0]; pos += 8
        off = struct.unpack_from("<Q", buf, pos)[0]; pos += 8
        anchors.append((row, t_min, off))

    return {
        "magic": magic,
        "version": version,
        "anchor_every": anchor_every,
        "anchors": anchors,
        "cadence_min": cadence_min,
        "offsets_present": offsets_present,
        "star_sha_hex": star_sha_hex,
    }


def resolve_seek(anchors, cadence_min, seek_row, seek_time_min, rows_hint):
    if seek_time_min is not None:
        # convert time->row (minutes since start)
        target_row = int(seek_time_min) // int(cadence_min)
    else:
        target_row = int(seek_row)

    # clamp if rows_hint provided
    if rows_hint is not None:
        target_row = max(0, min(target_row, int(rows_hint) - 1))

    # find nearest anchor by row
    best = anchors[0]
    for a in anchors:
        if a[0] <= target_row:
            best = a
        else:
            break

    return target_row, best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--star", required=True)
    ap.add_argument("--idx", required=True)
    ap.add_argument("--seek_row", type=int, default=None)
    ap.add_argument("--seek_time", type=int, default=None, help="minutes since start (t_min)")
    ap.add_argument("--rows", type=int, default=20)
    ap.add_argument("--rows_hint", type=int, default=None)
    ap.add_argument("--cadence_min", type=int, default=None, help="override cadence if needed")
    ap.add_argument("--base_datetime", default=None, help='optional ISO base, eg "2006-12-16T17:24:00"')
    args = ap.parse_args()

    if args.seek_row is None and args.seek_time is None:
        raise SystemExit("Provide --seek_row or --seek_time")

    star_sha = sha256_file(args.star)
    print(f"STAR sha256: {star_sha}")

    idx = load_index(args.idx)

    # optional override cadence
    cadence_min = int(idx["cadence_min"])
    if args.cadence_min is not None:
        cadence_min = int(args.cadence_min)

    # binding check (strong safety)
    if idx["star_sha_hex"] != star_sha:
        raise ValueError("IDX binding mismatch: sha256(star) differs from index binding")

    anchors = idx["anchors"]
    print(f"IDX ok: magic={idx['magic']}, anchor_every={idx['anchor_every']}, anchors={len(anchors)}")

    target_row, nearest = resolve_seek(
        anchors, cadence_min,
        seek_row=args.seek_row if args.seek_row is not None else 0,
        seek_time_min=args.seek_time,
        rows_hint=args.rows_hint
    )

    nearest_row, nearest_t, nearest_off = nearest

    # timestamp formatter
    def fmt(tmin):
        if args.base_datetime:
            return fmt_base_minutes(tmin, args.base_datetime)
        return fmt_epoch_minutes(tmin)

    print("\nSeek resolved:")
    print(f"  target_row: {target_row}")
    print(f"  nearest_anchor_row: {nearest_row}")
    print(f"  nearest_anchor_t_min: {nearest_t}  ({fmt(nearest_t)})")

    if nearest_off == 0:
        print("  note: anchor offset = 0 (offsetless index) -> replay uses linear / deterministic fallback")

    print("\nReplay preview (row -> t_min):")
    for i in range(int(args.rows)):
        r = target_row + i
        if args.rows_hint is not None and r >= int(args.rows_hint):
            break
        tmin = r * cadence_min
        print(f"  row={r:<10} t_min={tmin:<12} {fmt(tmin)}")


if __name__ == "__main__":
    main()
