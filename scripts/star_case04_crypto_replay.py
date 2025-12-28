#!/usr/bin/env python3
import argparse
import csv
import hashlib
import struct
import zlib

MAGIC8 = b"STAR4\x04OF"

DICT_COLS = ("Mining_Pool", "Currency", "Transaction_Type", "Transaction_Status")

def _die(msg: str) -> None:
    raise SystemExit(msg)

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def sha256_file(path, chunk=1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def write_uvarint(out, n: int) -> None:
    if n < 0:
        _die("uvarint requires non-negative")
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break

def read_uvarint(buf: bytes, pos: int):
    shift = 0
    n = 0
    while True:
        if pos >= len(buf):
            _die("unexpected EOF in uvarint")
        b = buf[pos]
        pos += 1
        n |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            return n, pos
        shift += 7
        if shift > 63:
            _die("uvarint too large")

def write_str(out, s: str) -> None:
    b = s.encode("utf-8")
    write_uvarint(out, len(b))
    out.extend(b)

def read_str(buf: bytes, pos: int):
    ln, pos = read_uvarint(buf, pos)
    ln = int(ln)
    if pos + ln > len(buf):
        _die("unexpected EOF in string")
    s = buf[pos:pos+ln].decode("utf-8")
    return s, pos + ln

def sniff_dialect(path: str):
    with open(path, "r", newline="", encoding="utf-8") as f:
        sample = f.read(4096)
    try:
        return csv.Sniffer().sniff(sample, delimiters=[",", "\t", ";", "|"])
    except Exception:
        d = csv.excel
        d.delimiter = ","
        return d

def read_rows(path: str, max_rows: int | None):
    dialect = sniff_dialect(path)
    with open(path, "r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f, dialect=dialect)
        fieldnames = r.fieldnames or []
        need = [
            "Transaction_ID","Sender_Address","Receiver_Address","Amount","Transaction_Fee",
            "Timestamp","Block_ID","Mining_Pool","Currency","Transaction_Type","Transaction_Status","Gas_Price_Gwei"
        ]
        missing = [c for c in need if c not in fieldnames]
        if missing:
            _die("missing required columns: " + ", ".join(missing))

        rows = []
        for i, row in enumerate(r):
            if max_rows is not None and i >= max_rows:
                break
            rows.append({k: (row.get(k, "") or "") for k in need})
        return rows

def build_dict(rows, col: str):
    uniq = {}
    arr = []
    for row in rows:
        v = row[col]
        if v not in uniq:
            uniq[v] = len(arr)
            arr.append(v)
    return uniq, arr

def encode_case04(rows):
    dmaps = {}
    dvals = {}
    for col in DICT_COLS:
        mp, arr = build_dict(rows, col)
        dmaps[col] = mp
        dvals[col] = arr

    out = bytearray()
    out.extend(MAGIC8)

    out.extend(struct.pack("<I", int(len(rows))))
    out.extend(struct.pack("<I", 12))

    for col in DICT_COLS:
        arr = dvals[col]
        out.extend(struct.pack("<I", int(len(arr))))
        for s in arr:
            b = s.encode("utf-8")
            out.extend(struct.pack("<I", int(len(b))))
            out.extend(b)

    for row in rows:
        write_str(out, row["Transaction_ID"])
        write_str(out, row["Sender_Address"])
        write_str(out, row["Receiver_Address"])
        write_str(out, row["Amount"])
        write_str(out, row["Transaction_Fee"])
        write_str(out, row["Timestamp"])
        write_str(out, row["Block_ID"])

        for col in DICT_COLS:
            code = dmaps[col][row[col]]
            write_uvarint(out, int(code))

        write_str(out, row["Gas_Price_Gwei"])

    return bytes(out)

def decode_case04(blob: bytes):
    if len(blob) < 16:
        _die("star blob too small")
    if blob[:8] != MAGIC8:
        _die("bad STAR4 header")

    pos = 8
    nrows = struct.unpack_from("<I", blob, pos)[0]; pos += 4
    ncols = struct.unpack_from("<I", blob, pos)[0]; pos += 4
    if ncols != 12:
        _die("unexpected cols in STAR4")

    dicts = {}
    for col in DICT_COLS:
        n = struct.unpack_from("<I", blob, pos)[0]; pos += 4
        arr = []
        for _ in range(int(n)):
            ln = struct.unpack_from("<I", blob, pos)[0]; pos += 4
            s = blob[pos:pos+ln].decode("utf-8"); pos += ln
            arr.append(s)
        dicts[col] = arr

    rows = []
    for _ in range(int(nrows)):
        txid, pos = read_str(blob, pos)
        sender, pos = read_str(blob, pos)
        recv, pos = read_str(blob, pos)
        amt, pos = read_str(blob, pos)
        fee, pos = read_str(blob, pos)
        ts, pos = read_str(blob, pos)
        bid, pos = read_str(blob, pos)

        mp_code, pos = read_uvarint(blob, pos)
        cur_code, pos = read_uvarint(blob, pos)
        ty_code, pos = read_uvarint(blob, pos)
        st_code, pos = read_uvarint(blob, pos)

        gas, pos = read_str(blob, pos)

        row = {
            "Transaction_ID": txid,
            "Sender_Address": sender,
            "Receiver_Address": recv,
            "Amount": amt,
            "Transaction_Fee": fee,
            "Timestamp": ts,
            "Block_ID": bid,
            "Mining_Pool": dicts["Mining_Pool"][int(mp_code)],
            "Currency": dicts["Currency"][int(cur_code)],
            "Transaction_Type": dicts["Transaction_Type"][int(ty_code)],
            "Transaction_Status": dicts["Transaction_Status"][int(st_code)],
            "Gas_Price_Gwei": gas,
        }
        rows.append(row)

    return rows

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max_rows", type=int, default=None)
    ap.add_argument("--cadence", type=int, default=None)
    args = ap.parse_args(argv)

    rows = read_rows(args.csv, args.max_rows)
    n = len(rows)

    raw_bytes = 0
    with open(args.csv, "rb") as f:
        raw_bytes = len(f.read())

    raw_z = len(zlib.compress(open(args.csv, "rb").read(), 9))

    packed = encode_case04(rows)
    packed_bytes = len(packed)
    packed_z = len(zlib.compress(packed, 9))

    decoded = decode_case04(packed)
    ok = (decoded == rows)

    out_star = args.out + ".star"
    out_z = args.out + ".star.zlib"

    with open(out_star, "wb") as f:
        f.write(packed)
    with open(out_z, "wb") as f:
        f.write(zlib.compress(packed, 9))

    print("[STAR] Encoding (case04)")
    print("SSUM-STAR — Case-04 (Crypto Transactions)")
    print(f"rows parsed: n={n}")
    print("")
    print("Baseline:")
    print(f"  raw file bytes:        {raw_bytes:,}")
    print(f"  zlib(raw) bytes:       {raw_z:,}")
    print("")
    print("Structural (STAR):")
    print(f"  packed bytes:          {packed_bytes:,}")
    print(f"  zlib(packed) bytes:    {packed_z:,}")
    print("")
    print("Ratios (smaller is better):")
    if raw_bytes > 0:
        print(f"  packed / raw:          {packed_bytes / raw_bytes:.4f}")
    if raw_z > 0:
        print(f"  zlib(packed)/zlib(raw):{packed_z / raw_z:.4f}")
    print("")
    print("Proof:")
    print(f"  decode(encode(parsed)) == parsed  [{'OK' if ok else 'FAIL'}]")
    if not ok:
        _die("FAIL: decode(encode(parsed)) did not match parsed")

    print("")
    print("Artifacts written:")
    print(f"  {out_star}")
    print(f"  {out_z}")

if __name__ == "__main__":
    main()
