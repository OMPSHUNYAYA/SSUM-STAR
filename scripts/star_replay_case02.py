#!/usr/bin/env python3

import argparse
import struct
import datetime
from typing import List, Tuple, Optional

from star_case02_airquality_replay import (
    STAR_MAGIC,
    AirTick,
    varint_decode,
    zigzag_decode,
    fmt_tick,
)

INDEX_MAGIC = b"STARIDX2"
INDEX_VERSION = 1


def _read_zigzag_int(buf: bytes, i: int) -> Tuple[int, int]:
    u, j = varint_decode(buf, i)
    return zigzag_decode(u), j


def load_index(idx_path: str):
    with open(idx_path, "rb") as f:
        b = f.read()

    if b[:8] != INDEX_MAGIC:
        raise ValueError("bad index magic")
    p = 8
    ver = struct.unpack_from("<B", b, p)[0]
    p += 1
    if ver != INDEX_VERSION:
        raise ValueError("unsupported index version")

    anchor_every = struct.unpack_from("<I", b, p)[0]
    p += 4
    nrows = struct.unpack_from("<Q", b, p)[0]
    p += 8
    nanchors = struct.unpack_from("<I", b, p)[0]
    p += 4

    anchors = []
    for _ in range(nanchors):
        row = struct.unpack_from("<Q", b, p)[0]; p += 8
        off = struct.unpack_from("<Q", b, p)[0]; p += 8
        vals = struct.unpack_from("<qqqqqqqq", b, p); p += 8 * 8
        tk = AirTick(vals[0], vals[1], vals[2], vals[3], vals[4], vals[5], vals[6], vals[7])
        anchors.append((int(row), int(off), tk))

    return int(anchor_every), int(nrows), anchors


def replay_seek(star_path: str, idx_path: str, seek_row: Optional[int], rows: int) -> List[AirTick]:
    with open(star_path, "rb") as f:
        buf = f.read()
    if buf[:6] != STAR_MAGIC:
        raise ValueError("bad STAR2A magic")

    anchor_every, nrows, anchors = load_index(idx_path)
    if nrows == 0:
        return []

    if seek_row is None:
        seek_row = 0
    if seek_row < 0:
        seek_row = 0
    if seek_row >= nrows:
        return []

    best = 0
    for k in range(len(anchors)):
        if anchors[k][0] <= seek_row:
            best = k
        else:
            break

    a_row, a_off, a_tick = anchors[best]
    cur_row = a_row
    cur = a_tick
    pos = a_off

    def read_tuple(p: int) -> Tuple[Tuple[int, int, int, int, int, int, int, int], int]:
        vals = []
        q = p
        for _ in range(8):
            x, q = _read_zigzag_int(buf, q)
            vals.append(int(x))
        return (vals[0], vals[1], vals[2], vals[3], vals[4], vals[5], vals[6], vals[7]), q

    while cur_row < seek_row:
        if pos >= len(buf):
            raise ValueError("truncated STAR2A body")
        tag = buf[pos]
        pos += 1

        if tag == 0:
            run_u, pos = varint_decode(buf, pos)
            run_len = int(run_u)
            (dt, dco, dc6, dnox, dno2, dtx, drh, dah), pos = read_tuple(pos)
            for _ in range(run_len):
                if cur_row >= seek_row:
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
        else:
            raise ValueError("unknown tag in STAR2A body")

    out: List[AirTick] = [cur]
    target_end = min(nrows, seek_row + rows)
    while cur_row < target_end - 1:
        if pos >= len(buf):
            break
        tag = buf[pos]
        pos += 1

        if tag == 0:
            run_u, pos = varint_decode(buf, pos)
            run_len = int(run_u)
            (dt, dco, dc6, dnox, dno2, dtx, drh, dah), pos = read_tuple(pos)
            for _ in range(run_len):
                if cur_row >= target_end - 1:
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
                out.append(cur)
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
            out.append(cur)
        else:
            raise ValueError("unknown tag in STAR2A body")

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--star", required=True)
    ap.add_argument("--idx", required=True)
    ap.add_argument("--seek_row", type=int)
    ap.add_argument("--rows", type=int, default=10)
    args = ap.parse_args()

    ticks = replay_seek(args.star, args.idx, args.seek_row, args.rows)

    if args.seek_row is None:
        sr = 0
    else:
        sr = args.seek_row

    print(f"Replay from row {sr} ({len(ticks)} rows):")
    for tk in ticks:
        print("  " + fmt_tick(tk))


if __name__ == "__main__":
    main()
