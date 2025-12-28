# Replay Scripts (SSUM-STAR)

This folder documents the **replay stage** of SSUM-STAR.

Replay reconstructs history deterministically from a `.star` artifact.

Replay is:
- exact
- deterministic
- bounded
- reproducible indefinitely

---

## Why are there no files here?

Replay scripts are intentionally located in the `scripts/` root directory.

This keeps usage:
- explicit
- flat
- reproducible
- audit-friendly

This folder exists to explain **replay guarantees**, not execution structure.

---

## How replay works

Replay is deterministic unfolding:

`state_0 + delta_1 + delta_2 + ... + delta_n`

Guarantees:
- no approximation
- no reordering
- no drift
- no fabrication

Replay correctness does not depend on indexes.

---

## Where to run replay commands

Run all replay commands from the `scripts/` root:

Replay by row:
`python star_run.py replay --star DATASET.star --idx DATASET.star.idx --seek_row R --rows K`

Replay by structural time:
`python star_run.py replay --star DATASET.star --idx DATASET.star.idx --seek_time T --rows K`
