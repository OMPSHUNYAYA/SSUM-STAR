import argparse
import importlib
import sys

def _die(msg: str) -> None:
    print(f"[STAR-RUN ERROR] {msg}", file=sys.stderr)
    raise SystemExit(2)

def _import_first(mod_names, purpose: str):
    last_err = None
    for name in mod_names:
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as e:
            last_err = e
            continue
    _die(f"{purpose}: could not import any of: {', '.join(mod_names)}")

def detect_case_from_star(path: str) -> str:
    with open(path, "rb") as f:
        m = f.read(8)

    if len(m) < 5:
        _die("STAR file too small to contain a valid header")

    if m[:4] != b"STAR":
        _die("Unknown STAR magic (missing 'STAR' prefix)")

    v = m[4:5]

    if v == b"1" or v == b"\x01":
        return "case01"
    if v == b"2" or v == b"\x02":
        return "case02"
    if v == b"3" or v == b"\x03":
        return "case03"
    if v == b"4" or v == b"\x04":
        return "case04"

    if m.startswith(b"STAR1"):
        return "case01"
    if m.startswith(b"STAR2"):
        return "case02"
    if m.startswith(b"STAR3") or m.startswith(b"STAR03"):
        return "case03"
    if m.startswith(b"STAR4") or m.startswith(b"STAR04"):
        return "case04"

    _die("Unknown STAR magic (expected one of: case01/case02/case03/case04)")
    return "case01"

def call_main(module, argv):
    if not hasattr(module, "main"):
        _die("Target module has no main()")

    old_argv = sys.argv
    try:
        sys.argv = [getattr(module, "__file__", "module")] + list(argv)
        try:
            return module.main(argv)
        except TypeError:
            return module.main()
    finally:
        sys.argv = old_argv

def _mod_for_encode(case: str):
    candidates = {
        "case01": ["star_case01_spx_replay", "star_case01_spx_encode", "star_case01_spx"],
        "case02": ["star_case02_airquality_replay", "star_case02_airquality_encode", "star_case02_airquality"],
        "case03": ["star_case03_power_replay", "star_case03_power_encode", "star_case03_power", "star_encode_case03"],
        "case04": ["star_case04_crypto_replay", "star_case04_crypto_encode", "star_case04_crypto"],
    }.get(case)
    if not candidates:
        _die("encode requires --case in {case01, case02, case03, case04}")
    return _import_first(candidates, "encode")

def _mod_for_index(case: str):
    m = {
        "case01": "star_index_case01",
        "case02": "star_index_case02",
        "case03": "star_index_case03",
        "case04": "star_index_case04",
    }.get(case)
    if not m:
        _die("no index module for detected case")
    return importlib.import_module(m)

def _mod_for_replay(case: str):
    m = {
        "case01": "star_replay_case01",
        "case02": "star_replay_case02",
        "case03": "star_replay_case03",
        "case04": "star_replay_case04",
    }.get(case)
    if not m:
        _die("no replay module for detected case")
    return importlib.import_module(m)

def cmd_encode(args):
    mod = _mod_for_encode(args.case)
    argv = []
    argv += ["--csv", args.csv]
    argv += ["--out", args.out]
    if args.max_rows is not None:
        if args.max_rows < 0:
            _die("--max_rows must be >= 0")
        argv += ["--max_rows", str(args.max_rows)]
    if args.case == "case01":
        if args.price_scale is not None:
            argv += ["--price_scale", str(args.price_scale)]
    if args.case in ("case03", "case04"):
        if args.cadence is not None:
            argv += ["--cadence", str(args.cadence)]
    call_main(mod, argv)

def cmd_index(args):
    case = detect_case_from_star(args.star)
    mod = _mod_for_index(case)
    argv = ["--star", args.star, "--out", args.out]
    if args.anchor_every is not None:
        if args.anchor_every <= 0:
            _die("--anchor_every must be > 0")
        argv += ["--anchor_every", str(args.anchor_every)]
    if hasattr(args, "rows") and args.rows is not None:
        if args.rows < 0:
            _die("--rows must be >= 0")
        argv += ["--rows", str(args.rows)]
    if hasattr(args, "cadence") and args.cadence is not None:
        argv += ["--cad", str(args.cadence)]
    call_main(mod, argv)

def cmd_replay(args):
    case = detect_case_from_star(args.star)
    mod = _mod_for_replay(case)
    argv = ["--star", args.star, "--idx", args.idx, "--rows", str(args.rows)]
    if args.seek_row is not None:
        if args.seek_row < 0:
            _die("--seek_row must be >= 0")
        argv += ["--seek_row", str(args.seek_row)]
    if args.seek_time is not None:
        argv += ["--seek_time", str(args.seek_time)]
    if getattr(args, "rows_hint", None) is not None:
        argv += ["--rows_hint", str(args.rows_hint)]
    call_main(mod, argv)

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("encode")
    pe.add_argument("--case", required=True, choices=["case01", "case02", "case03", "case04"])
    pe.add_argument("--csv", required=True)
    pe.add_argument("--out", required=True)
    pe.add_argument("--max_rows", type=int, default=None)
    pe.add_argument("--price_scale", type=int, default=None)
    pe.add_argument("--cadence", type=int, default=None)
    pe.set_defaults(func=cmd_encode)

    pi = sub.add_parser("index")
    pi.add_argument("--star", required=True)
    pi.add_argument("--out", required=True)
    pi.add_argument("--anchor_every", type=int, default=None)
    pi.add_argument("--rows", type=int, default=None)
    pi.add_argument("--cadence", type=int, default=None)
    pi.set_defaults(func=cmd_index)

    pr = sub.add_parser("replay")
    pr.add_argument("--star", required=True)
    pr.add_argument("--idx", required=True)
    pr.add_argument("--seek_time", default=None)
    pr.add_argument("--seek_row", type=int, default=None)
    pr.add_argument("--rows", type=int, default=10)
    pr.add_argument("--rows_hint", type=int, default=None)
    pr.set_defaults(func=cmd_replay)

    args = ap.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
