# Index Scripts (SSUM-STAR)

This folder documents the **indexing stage** of SSUM-STAR.

Indexing creates a `.star.idx` file that accelerates seek operations.

Indexes are:
- optional
- disposable
- rebuildable
- never authoritative

Design rule:
`truth -> .star`
`navigation -> .star.idx`

---

## Why are there no files here?

Index scripts are intentionally located in the `scripts/` root directory.

This avoids:
- duplicated logic
- path confusion
- environment coupling

This folder exists to explain **index semantics**, not to hold executables.

---

## What indexing does

Indexing:
- records anchor points
- enables bounded replay
- accelerates deterministic seek

Indexing never:
- defines truth
- alters data
- affects replay correctness

If the index is deleted or corrupted, replay remains correct.

---

## Where to run index commands

Run all index commands from the `scripts/` root:

`python star_run.py index --star DATASET.star --out DATASET.star.idx --anchor_every N`
