#!/usr/bin/env python3
# SSUM-STAR — Case-01 Index Builder (STAR1)
# Builds an index with anchor snapshots so we can seek+replay efficiently.
# Index anchors are stored at BLOCK BOUNDARIES (safe with RLE blocks).

import argparse
import struct
import sys
from dataclasses import dataclass
from typing import List, Tuple

def die(msg: str):
    print(f"[STAR-INDEX-01 ERROR] {msg}", file=sys.stderr)
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

# --------------------------
# STAR1 header parse
# --------------------------
def parse_star1_header(buf: bytes) -> Tuple[int, int, Bar, int]:
    # magic (5 bytes) "STAR1"
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
    return n, price_scale, base, i  # i is start of body

# --------------------------
# Decode one block (tag=0 RLE or tag=1 literal)
# Returns: (dd,do,dh,dl,dc,dv, run, new_i)
# run=1 for literal; run>=3 for RLE (per encoder design)
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
# Index format (binary, deterministic)
# --------------------------
# magic: b"SIDX1"
# case : b"CASE01\0" (7 bytes)
# anchor_every: uint32
# n_rows: uint32
# n_anchors: uint32
# anchors: repeated:
#   row_index: uint32
#   byte_offset: uint32
#   d_days: int32
#   o,h,l,c,v: int64 each
def write_index(path_out: str, anchor_every: int, n_rows: int, anchors: List[Tuple[int,int,Bar]]):
    with open(path_out, "wb") as f:
        f.write(b"SIDX1")
        f.write(b"CASE01\0")
        f.write(struct.pack("<III", anchor_every, n_rows, len(anchors)))
        for row_i, off, b in anchors:
            f.write(struct.pack("<IIiqqqqq",
                                int(row_i),
                                int(off),
                                int(b.d_days),
                                int(b.o), int(b.h), int(b.l), int(b.c), int(b.v)))
    print(f"Index written: {path_out}")
    print(f"Anchors: {len(anchors)} (target every {anchor_every} rows, block-boundary safe)")

def build_index(star_path: str, anchor_every: int) -> Tuple[int, List[Tuple[int,int,Bar]]]:
    buf = open(star_path, "rb").read()
    n_rows, price_scale, base, body_i = parse_star1_header(buf)

    if n_rows == 0:
        return 0, [(0, body_i, base)]

    anchors: List[Tuple[int,int,Bar]] = []

    # Anchor at row 0 (base), positioned at start of body (next block)
    row = 0
    pos = body_i
    cur = base
    anchors.append((row, pos, cur))

    # Decode blocks; anchors captured at BLOCK BOUNDARIES:
    # before reading the next tag, if row is at a multiple of anchor_every.
    # This avoids the "mid-run" problem.
    while row < n_rows - 1:
        # block boundary anchor
        if row % anchor_every == 0:
            # avoid duplicate of row=0 (already appended)
            if not (row == 0 and anchors and anchors[-1][0] == 0):
                anchors.append((row, pos, cur))

        # decode one block at pos
        block_start = pos
        dd, do, dh, dl, dc, dv, run, pos2 = decode_block(buf, pos)

        # apply run times
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
            if row >= n_rows:
                break

        pos = pos2

        if pos > len(buf):
            raise ValueError("internal: pos out of bounds")

    # Ensure last anchor exists near end (optional but nice)
    if anchors[-1][0] != row:
        anchors.append((row, pos, cur))

    return n_rows, anchors

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--star", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--anchor_every", type=int, default=256)
    args = ap.parse_args()

    try:
        n_rows, anchors = build_index(args.star, args.anchor_every)
        write_index(args.out, args.anchor_every, n_rows, anchors)
    except Exception as e:
        die(str(e))

if __name__ == "__main__":
    main()
