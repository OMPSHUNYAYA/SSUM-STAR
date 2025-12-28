#!/usr/bin/env python3

import argparse
import struct
from typing import List, Tuple

from star_case02_airquality_replay import (
    STAR_MAGIC,
    AirTick,
    varint_decode,
    zigzag_decode,
)

INDEX_MAGIC = b"STARIDX2"
INDEX_VERSION = 1


def _read_zigzag_int(buf: bytes, i: int) -> Tuple[int, int]:
    u, j = varint_decode(buf, i)
    return zigzag_decode(u), j


def build_index(star_path: str, out_path: str, anchor_every: int) -> None:
    if anchor_every <= 0:
        raise ValueError("--anchor_every must be > 0")

    with open(star_path, "rb") as f:
        buf = f.read()

    if buf[:6] != STAR_MAGIC:
        raise ValueError("bad STAR2A magic")

    i = 6
    n_u, i = varint_decode(buf, i)
    n = int(n_u)
    if n == 0:
        anchors = [(0, i, AirTick(0, 0, 0, 0, 0, 0, 0, 0))]
    else:
        base_vals = []
        for _ in range(8):
            v, i = _read_zigzag_int(buf, i)
            base_vals.append(v)

        cur = AirTick(
            base_vals[0], base_vals[1], base_vals[2], base_vals[3],
            base_vals[4], base_vals[5], base_vals[6], base_vals[7]
        )

        body_start = i
        anchors: List[Tuple[int, int, AirTick]] = []
        cur_row = 0
        pos = body_start

        def record_anchor():
            anchors.append((cur_row, pos, cur))

        record_anchor()

        def read_tuple(p: int) -> Tuple[Tuple[int, int, int, int, int, int, int, int], int]:
            vals = []
            q = p
            for _ in range(8):
                x, q = _read_zigzag_int(buf, q)
                vals.append(int(x))
            return (vals[0], vals[1], vals[2], vals[3], vals[4], vals[5], vals[6], vals[7]), q

        while cur_row < n - 1:
            if pos >= len(buf):
                raise ValueError("truncated STAR2A body")
            tag = buf[pos]
            pos += 1

            if tag == 0:
                run_u, pos = varint_decode(buf, pos)
                run_len = int(run_u)
                (dt, dco, dc6, dnox, dno2, dtx, drh, dah), pos = read_tuple(pos)

                for _ in range(run_len):
                    if cur_row >= n - 1:
                        break
                    cur = AirTick(
                        cur.t_min + dt,
                        cur.co_x10 + dco,
                        cur.c6h6_x10 + dc6,
                        cur.nox + dnox,
                        cur.no2 + dno2,
                        cur.t_x10 + dtx,
                        cur.rh_x10 + drh,
                        cur.ah_x1000 + dah,
                    )
                    cur_row += 1

                if cur_row % anchor_every == 0:
                    record_anchor()

            elif tag == 1:
                (dt, dco, dc6, dnox, dno2, dtx, drh, dah), pos = read_tuple(pos)
                cur = AirTick(
                    cur.t_min + dt,
                    cur.co_x10 + dco,
                    cur.c6h6_x10 + dc6,
                    cur.nox + dnox,
                    cur.no2 + dno2,
                    cur.t_x10 + dtx,
                    cur.rh_x10 + drh,
                    cur.ah_x1000 + dah,
                )
                cur_row += 1
                if cur_row % anchor_every == 0:
                    record_anchor()
            else:
                raise ValueError("unknown tag in STAR2A body")

    with open(out_path, "wb") as f:
        f.write(INDEX_MAGIC)
        f.write(struct.pack("<B", INDEX_VERSION))
        f.write(struct.pack("<I", int(anchor_every)))
        f.write(struct.pack("<Q", int(n)))
        f.write(struct.pack("<I", int(len(anchors))))
        for row, off, tk in anchors:
            f.write(struct.pack("<Q", int(row)))
            f.write(struct.pack("<Q", int(off)))
            f.write(struct.pack("<q", int(tk.t_min)))
            f.write(struct.pack("<q", int(tk.co_x10)))
            f.write(struct.pack("<q", int(tk.c6h6_x10)))
            f.write(struct.pack("<q", int(tk.nox)))
            f.write(struct.pack("<q", int(tk.no2)))
            f.write(struct.pack("<q", int(tk.t_x10)))
            f.write(struct.pack("<q", int(tk.rh_x10)))
            f.write(struct.pack("<q", int(tk.ah_x1000)))

    print(f"Index written: {out_path}")
    print(f"Anchors: {len(anchors)} (target every {anchor_every} rows, block-boundary safe)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--star", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--anchor_every", type=int, default=1024)
    args = ap.parse_args()
    build_index(args.star, args.out, args.anchor_every)


if __name__ == "__main__":
    main()
