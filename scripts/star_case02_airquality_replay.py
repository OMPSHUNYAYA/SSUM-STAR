#!/usr/bin/env python3

import argparse
import csv
import datetime
import os
import zlib
from dataclasses import dataclass
from typing import List, Tuple, Optional


STAR_MAGIC = b"STAR2A"


def zigzag_encode(x: int) -> int:
    return (x << 1) ^ (x >> 63)


def zigzag_decode(u: int) -> int:
    return (u >> 1) ^ (-(u & 1))


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
    while True:
        if i >= len(buf):
            raise ValueError("truncated varint")
        b = buf[i]
        i += 1
        u |= (b & 0x7F) << shift
        if not (b & 0x80):
            return u, i
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


def clean_token(s: str) -> str:
    return s.strip().strip('"').strip()


def parse_decimal_maybe_comma(s: str) -> Optional[float]:
    s = clean_token(s)
    if not s:
        return None
    if s == "-200":
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def parse_int_or_none(s: str) -> Optional[int]:
    s = clean_token(s)
    if not s:
        return None
    if s == "-200":
        return None
    try:
        return int(float(s.replace(",", ".")))
    except Exception:
        return None


def parse_datetime_to_minutes(date_s: str, time_s: str) -> Optional[int]:
    date_s = clean_token(date_s)
    time_s = clean_token(time_s)
    if not date_s or not time_s:
        return None
    try:
        dt = datetime.datetime.strptime(date_s + " " + time_s, "%d/%m/%Y %H.%M.%S")
    except Exception:
        return None
    epoch = datetime.datetime(1970, 1, 1)
    return int((dt - epoch).total_seconds() // 60)


@dataclass(frozen=True)
class AirTick:
    t_min: int
    co_x10: int
    c6h6_x10: int
    nox: int
    no2: int
    t_x10: int
    rh_x10: int
    ah_x1000: int


def read_airquality_csv(path: str, scale: int = 10, max_rows: int = -1) -> List[AirTick]:
    if max_rows is not None and max_rows < -1:
        raise ValueError("--max_rows must be -1 (all) or >= 0")

    ticks: List[AirTick] = []
    with open(path, "r", newline="", encoding="latin-1") as f:
        rdr = csv.reader(f, delimiter=";")
        header = next(rdr, None)
        if not header:
            return ticks

        cols = [clean_token(c) for c in header]

        def find_col(name: str) -> int:
            for i, c in enumerate(cols):
                if c == name:
                    return i
            return -1

        i_date = find_col("Date")
        i_time = find_col("Time")
        i_co = find_col("CO(GT)")
        i_c6 = find_col("C6H6(GT)")
        i_nox = find_col("NOx(GT)")
        i_no2 = find_col("NO2(GT)")
        i_t = find_col("T")
        i_rh = find_col("RH")
        i_ah = find_col("AH")

        if min(i_date, i_time, i_co, i_c6, i_nox, i_no2, i_t, i_rh, i_ah) < 0:
            raise ValueError("AirQualityUCI.csv header missing expected columns")

        for row in rdr:
            if max_rows >= 0 and len(ticks) >= max_rows:
                break
            if not row or len(row) <= max(i_date, i_time, i_co, i_c6, i_nox, i_no2, i_t, i_rh, i_ah):
                continue

            t_min = parse_datetime_to_minutes(row[i_date], row[i_time])
            if t_min is None:
                continue

            co = parse_decimal_maybe_comma(row[i_co])
            c6 = parse_decimal_maybe_comma(row[i_c6])
            nox = parse_int_or_none(row[i_nox])
            no2 = parse_int_or_none(row[i_no2])
            tt = parse_decimal_maybe_comma(row[i_t])
            rh = parse_decimal_maybe_comma(row[i_rh])
            ah = parse_decimal_maybe_comma(row[i_ah])

            if None in (co, c6, nox, no2, tt, rh, ah):
                continue

            ticks.append(
                AirTick(
                    t_min=t_min,
                    co_x10=int(round(co * 10)),
                    c6h6_x10=int(round(c6 * 10)),
                    nox=int(nox),
                    no2=int(no2),
                    t_x10=int(round(tt * 10)),
                    rh_x10=int(round(rh * 10)),
                    ah_x1000=int(round(ah * 1000)),
                )
            )

    return ticks


def encode_star(ticks: List[AirTick]) -> bytes:
    if not ticks:
        return STAR_MAGIC + varint_encode(0)

    out = bytearray()
    out += STAR_MAGIC
    out += varint_encode(len(ticks))

    base = ticks[0]
    base_vals = [
        base.t_min,
        base.co_x10,
        base.c6h6_x10,
        base.nox,
        base.no2,
        base.t_x10,
        base.rh_x10,
        base.ah_x1000,
    ]
    for v in base_vals:
        out += varint_encode(zigzag_encode(int(v)))

    def deltas(prev: AirTick, cur: AirTick) -> Tuple[int, int, int, int, int, int, int, int]:
        return (
            cur.t_min - prev.t_min,
            cur.co_x10 - prev.co_x10,
            cur.c6h6_x10 - prev.c6h6_x10,
            cur.nox - prev.nox,
            cur.no2 - prev.no2,
            cur.t_x10 - prev.t_x10,
            cur.rh_x10 - prev.rh_x10,
            cur.ah_x1000 - prev.ah_x1000,
        )

    def write_tuple(t: Tuple[int, int, int, int, int, int, int, int]) -> None:
        for x in t:
            out.extend(varint_encode(zigzag_encode(int(x))))

    i = 1
    while i < len(ticks):
        prev = ticks[i - 1]
        cur = ticks[i]
        dtup = deltas(prev, cur)

        run = 1
        j = i + 1
        while j < len(ticks):
            nxt = ticks[j]
            if deltas(cur, nxt) == dtup:
                run += 1
                cur = nxt
                j += 1
            else:
                break

        if run >= 3:
            out.append(0)
            out += varint_encode(run)
            write_tuple(dtup)
            i += run
        else:
            out.append(1)
            write_tuple(dtup)
            i += 1

    return bytes(out)


def decode_star(buf: bytes) -> List[AirTick]:
    if buf[:6] != STAR_MAGIC:
        raise ValueError("bad STAR2A magic")
    i = 6
    n, i = varint_decode(buf, i)
    if n == 0:
        return []

    base_vals = []
    for _ in range(8):
        u, i = varint_decode(buf, i)
        base_vals.append(zigzag_decode(u))

    t_min, co_x10, c6h6_x10, nox, no2, t_x10, rh_x10, ah_x1000 = base_vals
    ticks: List[AirTick] = [AirTick(t_min, co_x10, c6h6_x10, nox, no2, t_x10, rh_x10, ah_x1000)]

    def read_int(ii: int) -> Tuple[int, int]:
        u, jj = varint_decode(buf, ii)
        return zigzag_decode(u), jj

    while len(ticks) < n:
        if i >= len(buf):
            raise ValueError("truncated body")
        tag = buf[i]
        i += 1

        if tag == 0:
            run_len_u, i = varint_decode(buf, i)
            run_len = int(run_len_u)

            tup = []
            for _ in range(8):
                x, i = read_int(i)
                tup.append(x)
            dt, dco, dc6, dnox, dno2, dtx, drh, dah = tup

            for _ in range(run_len):
                prev = ticks[-1]
                ticks.append(
                    AirTick(
                        prev.t_min + dt,
                        prev.co_x10 + dco,
                        prev.c6h6_x10 + dc6,
                        prev.nox + dnox,
                        prev.no2 + dno2,
                        prev.t_x10 + dtx,
                        prev.rh_x10 + drh,
                        prev.ah_x1000 + dah,
                    )
                )
                if len(ticks) >= n:
                    break

        elif tag == 1:
            tup = []
            for _ in range(8):
                x, i = read_int(i)
                tup.append(x)
            dt, dco, dc6, dnox, dno2, dtx, drh, dah = tup
            prev = ticks[-1]
            ticks.append(
                AirTick(
                    prev.t_min + dt,
                    prev.co_x10 + dco,
                    prev.c6h6_x10 + dc6,
                    prev.nox + dnox,
                    prev.no2 + dno2,
                    prev.t_x10 + dtx,
                    prev.rh_x10 + drh,
                    prev.ah_x1000 + dah,
                )
            )
        else:
            raise ValueError("unknown tag in STAR2A body")

    return ticks


def structural_time_stats(ticks: List[AirTick]) -> Tuple[int, float, int, int]:
    if len(ticks) < 2:
        return 0, 0.0, 0, 0
    dts = [ticks[i].t_min - ticks[i - 1].t_min for i in range(1, len(ticks))]
    dts_sorted = sorted(dts)
    mid = len(dts_sorted) // 2
    if len(dts_sorted) % 2 == 1:
        med = float(dts_sorted[mid])
    else:
        med = 0.5 * (dts_sorted[mid - 1] + dts_sorted[mid])
    return min(dts), med, max(dts), sum(1 for x in dts if x <= 0)


def fmt_tick(t: AirTick) -> str:
    epoch = datetime.datetime(1970, 1, 1)
    dt = epoch + datetime.timedelta(minutes=t.t_min)
    return (
        f"{dt.strftime('%Y-%m-%d %H:%M:%S')}  "
        f"CO={t.co_x10/10:.1f}  "
        f"C6H6={t.c6h6_x10/10:.1f}  "
        f"NOx={t.nox}  "
        f"NO2={t.no2}  "
        f"T={t.t_x10/10:.1f}  "
        f"RH={t.rh_x10/10:.1f}  "
        f"AH={t.ah_x1000/1000:.3f}"
    )


def human_bytes(n: int) -> str:
    x = float(n)
    for u in ["B", "KB", "MB", "GB"]:
        if x < 1024.0:
            return f"{x:.0f} {u}" if u == "B" else f"{x:.1f} {u}"
        x /= 1024.0
    return f"{x:.1f} TB"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=int, default=10)
    ap.add_argument("--max_rows", type=int, default=-1)
    args = ap.parse_args(argv)

    rows = read_airquality_csv(args.csv, scale=args.scale, max_rows=args.max_rows)
    blob = encode_star(rows)

    out_star = args.out if args.out.endswith(".star") else (args.out + ".star")
    out_z = out_star + ".zlib"

    with open(out_star, "wb") as f:
        f.write(blob)

    with open(out_z, "wb") as f:
        f.write(zlib.compress(blob, level=9))

    raw_bytes = os.path.getsize(args.csv)
    z_raw_bytes = len(zlib.compress(open(args.csv, "rb").read(), level=9))

    print("SSUM-STAR — Case-02 (Air Quality UCI)")
    print(f"rows parsed: n={len(rows)}\n")
    print("Baseline:")
    print(f"  raw file bytes:        {raw_bytes:,}")
    print(f"  zlib(raw) bytes:       {z_raw_bytes:,}\n")
    print("Structural (STAR):")
    print(f"  packed bytes:          {len(blob):,}")
    print(f"  zlib(packed) bytes:    {os.path.getsize(out_z):,}\n")
    print("Ratios (smaller is better):")
    print(f"  packed / raw:          {len(blob)/raw_bytes:.4f}")
    print(f"  zlib(packed)/zlib(raw):{os.path.getsize(out_z)/z_raw_bytes:.4f}\n")

    dec = decode_star(blob)
    ok = (dec == rows)
    print("Proof:")
    print(f"  decode(encode(parsed)) == parsed  [{'OK' if ok else 'FAIL'}]\n")
    print("Artifacts written:")
    print(f"  {out_star}")
    print(f"  {out_z}")


if __name__ == "__main__":
    main()
