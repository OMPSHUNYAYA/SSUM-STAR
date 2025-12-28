#!/usr/bin/env python3
# SSUM-STAR — Case-01 Seek & Replay (STAR1 + SIDX1/CASE01 index)

import argparse
import bisect
import datetime
import struct
import sys
from dataclasses import dataclass
from typing import List, Tuple, Optional

def die(msg: str):
    print(f"[STAR-REPLAY-01 ERROR] {msg}", file=sys.stderr)
    raise SystemExit(2)

# --------------------------
# Varint + ZigZag
# --------------------------
def zigzag_decode(u: int) -> int:
    return (u >> 1) ^ -(u & 1)

def varint_decode(buf: bytes, i: int) -> Tuple[int, int]:
    shift = 0
    u = 0
    n = len(buf)
    while True:
        if i >= n:
            raise ValueError("truncated varint")
        b = buf[i]
        i += 1
        u |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            break
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")
    return u, i

@dataclass
class Bar:
    d_days: int
    o: int
    h: int
    l: int
    c: int
    v: int

EPOCH = datetime.date(1970, 1, 1)

def date_to_days(s: str) -> int:
    # Accept "YYYY-MM-DD"
    y, m, d = map(int, s.strip().split("-"))
    return (datetime.date(y, m, d) - EPOCH).days

def days_to_date(days: int) -> str:
    return (EPOCH + datetime.timedelta(days=days)).isoformat()

# --------------------------
# STAR1 header parse
# --------------------------
def parse_star1_header(buf: bytes) -> Tuple[int, int, Bar, int]:
    if not buf.startswith(b"STAR1"):
        raise ValueError("bad magic (expected STAR1)")
    i = 5

    n, i = varint_decode(buf, i)
    if n == 0:
        return 0, 0, Bar(0,0,0,0,0,0), i

    price_scale, i = varint_decode(buf, i)

    vals = []
    for _ in range(6):
        u, i = varint_decode(buf, i)
        vals.append(zigzag_decode(u))

    base = Bar(*vals)
    return n, price_scale, base, i

# --------------------------
# Decode one block
# --------------------------
def decode_block(buf: bytes, i: int) -> Tuple[int,int,int,int,int,int,int,int]:
    n = len(buf)
    if i >= n:
        raise ValueError("truncated: missing tag")
    tag = buf[i]
    i += 1

    if tag == 0:
        run, i = varint_decode(buf, i)
        vals = []
        for _ in range(6):
            u, i = varint_decode(buf, i)
            vals.append(zigzag_decode(u))
        dd, do, dh, dl, dc, dv = vals
        return dd, do, dh, dl, dc, dv, int(run), i

    if tag == 1:
        vals = []
        for _ in range(6):
            u, i = varint_decode(buf, i)
            vals.append(zigzag_decode(u))
        dd, do, dh, dl, dc, dv = vals
        return dd, do, dh, dl, dc, dv, 1, i

    raise ValueError(f"bad tag {tag}")

# --------------------------
# Load SIDX1/CASE01 index
# --------------------------
def load_index(idx_path: str):
    b = open(idx_path, "rb").read()
    if not b.startswith(b"SIDX1"):
        raise ValueError("bad index magic")
    if b[5:12] != b"CASE01\0":
        raise ValueError("index is not CASE01")

    anchor_every, n_rows, n_anchors = struct.unpack_from("<III", b, 12)
    off = 12 + 12

    anchors = []
    row_keys = []
    day_keys = []

    for _ in range(n_anchors):
        row_i, byte_off, d_days, o, h, l, c, v = struct.unpack_from("<IIiqqqqq", b, off)
        off += struct.calcsize("<IIiqqqqq")
        bar = Bar(d_days, o, h, l, c, v)
        anchors.append((row_i, byte_off, bar))
        row_keys.append(row_i)
        day_keys.append(d_days)

    return anchor_every, n_rows, anchors, row_keys, day_keys

# --------------------------
# Replay engine
# --------------------------
def replay_from(star_buf: bytes, start_row: int, start_pos: int, start_bar: Bar, n_rows: int,
                seek_row: Optional[int], seek_days: Optional[int], out_rows: int) -> List[Tuple[int, Bar]]:
    # walk forward until condition reached, then emit out_rows
    row = start_row
    pos = start_pos
    cur = start_bar

    results: List[Tuple[int, Bar]] = []

    def want_now(row_i: int, bar: Bar) -> bool:
        if seek_row is not None:
            return row_i >= seek_row
        if seek_days is not None:
            return bar.d_days >= seek_days
        return True

    # If starting point already matches, start collecting
    if want_now(row, cur):
        results.append((row, cur))

    while row < n_rows - 1 and len(results) < out_rows:
        dd, do, dh, dl, dc, dv, run, pos2 = decode_block(star_buf, pos)
        pos = pos2

        for _ in range(run):
            cur = Bar(
                cur.d_days + dd,
                cur.o + do,
                cur.h + dh,
                cur.l + dl,
                cur.c + dc,
                cur.v + dv
            )
            row += 1

            if want_now(row, cur):
                results.append((row, cur))
                if len(results) >= out_rows:
                    break

            if row >= n_rows - 1:
                break

    return results

def fmt_bar(b: Bar, price_scale: int) -> str:
    return (
        f"{days_to_date(b.d_days)}  "
        f"O={b.o/price_scale:.2f} H={b.h/price_scale:.2f} "
        f"L={b.l/price_scale:.2f} C={b.c/price_scale:.2f}  V={b.v}"
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--star", required=True)
    ap.add_argument("--idx", required=True)
    ap.add_argument("--seek_row", type=int)
    ap.add_argument("--seek_time")  # YYYY-MM-DD
    ap.add_argument("--rows", type=int, default=10)
    args = ap.parse_args()

    if (args.seek_row is None) and (args.seek_time is None):
        die("Provide --seek_row or --seek_time")

    star_buf = open(args.star, "rb").read()
    n_rows, price_scale, base, body_i = parse_star1_header(star_buf)

    anchor_every, n_rows_idx, anchors, row_keys, day_keys = load_index(args.idx)
    if n_rows_idx != n_rows:
        die("Index n_rows does not match STAR file (wrong pair?)")

    seek_row = args.seek_row
    seek_days = date_to_days(args.seek_time) if args.seek_time else None

    # choose anchor
    if seek_row is not None:
        j = bisect.bisect_right(row_keys, seek_row) - 1
    else:
        j = bisect.bisect_right(day_keys, seek_days) - 1

    if j < 0:
        j = 0

    a_row, a_off, a_bar = anchors[j]

    # Replay
    rows_out = replay_from(
        star_buf=star_buf,
        start_row=a_row,
        start_pos=a_off,
        start_bar=a_bar,
        n_rows=n_rows,
        seek_row=seek_row,
        seek_days=seek_days,
        out_rows=args.rows
    )

    if seek_row is not None:
        print(f"Replay from row {seek_row} ({len(rows_out)} rows):")
    else:
        print(f"Replay from time {args.seek_time} ({len(rows_out)} rows):")

    for _, b in rows_out:
        print(" ", fmt_bar(b, price_scale))

if __name__ == "__main__":
    main()
