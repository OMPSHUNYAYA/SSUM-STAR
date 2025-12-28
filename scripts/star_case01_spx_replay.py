#!/usr/bin/env python3

import argparse
import csv
import datetime
import math
import os
import struct
import sys
import zlib
from dataclasses import dataclass
from typing import List, Tuple, Optional


def zigzag_encode(x: int) -> int:
    return (x << 1) ^ (x >> 63)


def zigzag_decode(u: int) -> int:
    return (u >> 1) ^ -(u & 1)


def varint_encode(u: int) -> bytes:
    out = bytearray()
    while True:
        b = u & 0x7F
        u >>= 7
        if u:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


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


@dataclass(frozen=True)
class Bar:
    d_days: int
    o: int
    h: int
    l: int
    c: int
    v: int


EPOCH = datetime.date(1970, 1, 1)


def date_to_days(s: str) -> int:
    y, m, d = map(int, s.strip().split("-"))
    return (datetime.date(y, m, d) - EPOCH).days


def days_to_date(days: int) -> str:
    return (EPOCH + datetime.timedelta(days=days)).isoformat()


def parse_float_or_none(x: str) -> Optional[float]:
    if x is None:
        return None
    t = x.strip()
    if not t:
        return None
    lo = t.lower()
    if lo == "nan" or lo == "null":
        return None
    try:
        return float(t)
    except Exception:
        return None


def read_spx_csv(path: str, price_scale: int, max_rows: Optional[int]) -> List[Bar]:
    bars: List[Bar] = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        for row in r:
            if not row:
                continue
            if row[0].strip().lower() in ("date", "timestamp"):
                continue
            if len(row) < 6:
                continue

            d = row[0].strip()
            o = parse_float_or_none(row[1])
            h = parse_float_or_none(row[2])
            l = parse_float_or_none(row[3])
            c = parse_float_or_none(row[4])
            v = row[5].strip()

            if o is None or h is None or l is None or c is None:
                continue

            try:
                d_days = date_to_days(d)
            except Exception:
                continue

            so = int(round(o * price_scale))
            sh = int(round(h * price_scale))
            sl = int(round(l * price_scale))
            sc = int(round(c * price_scale))

            vs = v.replace(",", "").strip()
            if vs == "":
                sv = 0
            else:
                sv = int(float(vs)) if ("." in vs or "e" in vs.lower()) else int(vs)

            bars.append(Bar(d_days, so, sh, sl, sc, sv))
            if max_rows is not None and len(bars) >= max_rows:
                break
    return bars


def encode_star(bars: List[Bar], price_scale: int) -> Tuple[bytes, dict]:
    if not bars:
        out = b"STAR1" + varint_encode(0)
        return out, {"n": 0, "price_scale": price_scale}

    out = bytearray()
    out += b"STAR1"
    out += varint_encode(len(bars))
    out += varint_encode(price_scale)

    b0 = bars[0]
    for val in (b0.d_days, b0.o, b0.h, b0.l, b0.c, b0.v):
        out += varint_encode(zigzag_encode(int(val)))

    deltas: List[Tuple[int, int, int, int, int, int]] = []
    prev = b0
    for b in bars[1:]:
        deltas.append(
            (
                b.d_days - prev.d_days,
                b.o - prev.o,
                b.h - prev.h,
                b.l - prev.l,
                b.c - prev.c,
                b.v - prev.v,
            )
        )
        prev = b

    i = 0
    while i < len(deltas):
        tup = deltas[i]
        run = 1
        j = i + 1
        while j < len(deltas) and deltas[j] == tup and run < 10_000_000:
            run += 1
            j += 1

        if run >= 3:
            out += b"\x00"
            out += varint_encode(run)
            for x in tup:
                out += varint_encode(zigzag_encode(int(x)))
        else:
            for _ in range(run):
                out += b"\x01"
                for x in tup:
                    out += varint_encode(zigzag_encode(int(x)))

        i = j

    meta = {"n": len(bars), "price_scale": price_scale}
    return bytes(out), meta


def iter_record_offsets(buf: bytes) -> List[int]:
    if buf.startswith(b"STAR1"):
        pos = 5
    elif buf.startswith(b"STAR01"):
        pos = 6
    else:
        raise ValueError("bad magic")

    n = len(buf)
    offsets: List[int] = []
    if pos >= n:
        return offsets

    _, pos = varint_decode(buf, pos)

    if pos >= n:
        return offsets

    _, pos = varint_decode(buf, pos)

    for _ in range(6):
        _, pos = varint_decode(buf, pos)

    while pos < n:
        offsets.append(pos)
        tag = buf[pos]
        pos += 1

        if tag == 0:
            run, pos = varint_decode(buf, pos)
            for _ in range(6):
                _, pos = varint_decode(buf, pos)
        elif tag == 1:
            for _ in range(6):
                _, pos = varint_decode(buf, pos)
        else:
            raise ValueError("bad tag")

    return offsets


def decode_star(buf: bytes) -> Tuple[List[Bar], dict]:
    i = 0
    if buf[i : i + 5] != b"STAR1":
        raise ValueError("bad magic")
    i += 5

    n, i = varint_decode(buf, i)
    if n == 0:
        return [], {"n": 0}

    price_scale, i = varint_decode(buf, i)

    base = []
    for _ in range(6):
        u, i = varint_decode(buf, i)
        base.append(zigzag_decode(u))

    d, o, h, l, c, v = base
    bars = [Bar(d, o, h, l, c, v)]

    while len(bars) < n:
        if i >= len(buf):
            raise ValueError("truncated body")
        tag = buf[i]
        i += 1

        if tag == 0:
            run, i = varint_decode(buf, i)
            tup = []
            for _ in range(6):
                u, i = varint_decode(buf, i)
                tup.append(zigzag_decode(u))
            dd, do, dh, dl, dc, dv = tup
            for _ in range(int(run)):
                prev = bars[-1]
                bars.append(
                    Bar(
                        prev.d_days + dd,
                        prev.o + do,
                        prev.h + dh,
                        prev.l + dl,
                        prev.c + dc,
                        prev.v + dv,
                    )
                )
        elif tag == 1:
            tup = []
            for _ in range(6):
                u, i = varint_decode(buf, i)
                tup.append(zigzag_decode(u))
            dd, do, dh, dl, dc, dv = tup
            prev = bars[-1]
            bars.append(
                Bar(
                    prev.d_days + dd,
                    prev.o + do,
                    prev.h + dh,
                    prev.l + dl,
                    prev.c + dc,
                    prev.v + dv,
                )
            )
        else:
            raise ValueError("bad tag")

    meta = {"n": n, "price_scale": price_scale}
    return bars, meta


def replay_preview(bars: List[Bar], price_scale: int, n: int = 10) -> List[str]:
    out = []
    for b in bars[:n]:
        out.append(
            f"{days_to_date(b.d_days)}  O={b.o/price_scale:.2f} H={b.h/price_scale:.2f} L={b.l/price_scale:.2f} C={b.c/price_scale:.2f} V={b.v}"
        )
    return out


def structural_time_stats(bars: List[Bar]) -> dict:
    if len(bars) <= 1:
        return {"dt_min": 0, "dt_median": 0, "dt_max": 0, "dt_nonpos": 0, "dt_gt_31": 0}

    dts = []
    dt_nonpos = 0
    dt_gt_31 = 0
    for i in range(1, len(bars)):
        dt = bars[i].d_days - bars[i - 1].d_days
        dts.append(dt)
        if dt <= 0:
            dt_nonpos += 1
        if dt > 31:
            dt_gt_31 += 1

    dts_sorted = sorted(dts)
    mid = len(dts_sorted) // 2
    if len(dts_sorted) % 2 == 1:
        med = dts_sorted[mid]
    else:
        med = (dts_sorted[mid - 1] + dts_sorted[mid]) / 2

    return {
        "dt_min": min(dts),
        "dt_median": med,
        "dt_max": max(dts),
        "dt_nonpos": dt_nonpos,
        "dt_gt_31": dt_gt_31,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(prog="star_case01_spx_replay.py")
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out_prefix", required=True)
    ap.add_argument("--price_scale", type=int, default=100)
    ap.add_argument("--max_rows", type=int, default=None)
    args = ap.parse_args(argv)

    if args.max_rows is not None and args.max_rows < 0:
        print("[STAR-ENCODE-01 ERROR] --max_rows must be >= 0", file=sys.stderr)
        raise SystemExit(2)

    bars = read_spx_csv(args.csv, price_scale=args.price_scale, max_rows=args.max_rows)

    raw = open(args.csv, "rb").read()

    packed, meta = encode_star(bars, args.price_scale)
    packed_z = zlib.compress(packed, 9)

    decoded, dmeta = decode_star(packed)
    ok = decoded == bars

    tstats = structural_time_stats(decoded)

    out_star = args.out_prefix + ".star"
    out_star_z = args.out_prefix + ".star.zlib"
    with open(out_star, "wb") as f:
        f.write(packed)
    with open(out_star_z, "wb") as f:
        f.write(packed_z)

    print("SSUM-STAR — Case-01 (S&P 500 OHLCV)")
    print(f"rows parsed: n={len(bars)}" + (f" (max_rows={args.max_rows})" if args.max_rows else ""))
    print(f"price_scale={args.price_scale}")
    print()

    print("Baseline:")
    print(f"  raw file bytes:        {len(raw):,}")
    print(f"  zlib(raw) bytes:       {len(zlib.compress(raw, 9)):,}")
    print()

    print("Structural (STAR):")
    print(f"  packed bytes:          {len(packed):,}")
    print(f"  zlib(packed) bytes:    {len(packed_z):,}")
    print()

    print("Ratios (smaller is better):")
    print(f"  packed / raw:          {len(packed)/len(raw):.4f}")
    print(f"  zlib(packed)/zlib(raw):{len(packed_z)/len(zlib.compress(raw,9)):.4f}")
    print()

    print("Structural Time (derived from transitions):")
    print(f"  dt_min={tstats['dt_min']}  dt_median={tstats['dt_median']}  dt_max={tstats['dt_max']}")
    print(f"  dt_nonpos={tstats['dt_nonpos']}  dt_gt_31={tstats['dt_gt_31']}")
    print()

    print("Replay preview (first 10):")
    for line in replay_preview(decoded, args.price_scale, n=10):
        print(" ", line)
    print()

    print("Proof:")
    print("  decode(encode(parsed)) == parsed  [" + ("OK" if ok else "FAIL") + "]")
    if not ok:
        raise SystemExit("Lossless proof failed (should never happen).")

    print()
    print("Artifacts written:")
    print(f"  {out_star}")
    print(f"  {out_star_z}")


if __name__ == "__main__":
    main()
