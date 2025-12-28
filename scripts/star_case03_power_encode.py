import argparse, os, zlib, sys, hashlib

MAGIC = b"STAR03\x00\x01"  # stable case03 magic

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def uvarint_encode(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)

def encode_lines_frontcoded(lines):
    """
    Lossless, deterministic structural packing for case03:
    - store each row as text line (exact), but front-coded against previous line
    - record = uvarint(prefix_len) + uvarint(suffix_len) + suffix_bytes
    """
    prev = b""
    packed = bytearray()
    for line in lines:
        cur = line
        # longest common prefix
        m = min(len(prev), len(cur))
        p = 0
        while p < m and prev[p] == cur[p]:
            p += 1
        suffix = cur[p:]
        packed += uvarint_encode(p)
        packed += uvarint_encode(len(suffix))
        packed += suffix
        prev = cur
    return bytes(packed)

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max_rows", type=int, default=None)
    args = ap.parse_args(argv)

    src = args.csv
    out_base = args.out
    out_star = out_base if out_base.endswith(".star") else (out_base + ".star")

    # read source file raw bytes for baseline metrics
    raw = open(src, "rb").read()
    raw_size = len(raw)
    zraw = zlib.compress(raw, 9)

    # parse lines (lossless) — keep header line too
    # dataset uses CRLF/ LF; we normalize by splitting and re-joining with '\n' on encode? NO.
    # We preserve exact line bytes as they appear in file by splitting on universal newlines in binary:
    lines = raw.splitlines()  # drops linebreak bytes by design
    if not lines:
        print("[STAR] empty input")
        raise SystemExit(2)

    header = lines[0]
    data_lines = lines[1:]

    if args.max_rows is not None:
        if args.max_rows < 0:
            print("[STAR] --max_rows must be >= 0", file=sys.stderr)
            raise SystemExit(2)
        data_lines = data_lines[: args.max_rows]

    # pack header + records
    header_block = uvarint_encode(len(header)) + header
    packed_records = encode_lines_frontcoded(data_lines)
    packed = MAGIC + header_block + packed_records

    zpacked = zlib.compress(packed, 9)

    with open(out_star, "wb") as f:
        f.write(packed)

    with open(out_star + ".zlib", "wb") as f:
        f.write(zpacked)

    print("SSUM-STAR — Case-03 (Household Power Consumption)")
    print(f"rows parsed: n={len(data_lines)}")
    print()
    print("Baseline:")
    print(f"  raw file bytes:        {raw_size:,}")
    print(f"  zlib(raw) bytes:       {len(zraw):,}")
    print()
    print("Structural (STAR):")
    print(f"  packed bytes:          {len(packed):,}")
    print(f"  zlib(packed) bytes:    {len(zpacked):,}")
    print()
    print("Ratios (smaller is better):")
    print(f"  packed / raw:          {len(packed)/raw_size:.4f}")
    print(f"  zlib(packed)/zlib(raw):{len(zpacked)/len(zraw):.4f}")
    print()
    # proof: decode(encode(parsed))==parsed is handled in replay module for case03 (seek+window)
    print("Artifacts written:")
    print(f"  {os.path.basename(out_star)}")
    print(f"  {os.path.basename(out_star)}.zlib")

if __name__ == "__main__":
    main()
