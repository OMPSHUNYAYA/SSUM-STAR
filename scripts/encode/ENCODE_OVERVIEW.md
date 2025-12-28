# Encode Scripts (SSUM-STAR)

This folder documents the **encoding stage** of SSUM-STAR.

Encoding is the process that transforms a raw dataset into a `.star` structural timeline.

Conceptually, encoding performs:
- deterministic parsing
- initial state capture
- invariant-preserving delta encoding
- structural time derivation

Core invariant:
`decode(encode(structure)) == structure`

---

## Why are there no files here?

All executable scripts are intentionally placed in the `scripts/` root directory.

This keeps execution simple:
- no package structure
- no imports
- no environment setup
- direct command-line usage

This folder exists for **conceptual clarity**, not execution.

---

## Conceptual Encode Flow

Raw dataset  
→ structural parsing  
→ delta transitions  
→ `.star` artifact (authoritative timeline)

The `.star` file is not storage.  
The `.star` file **is the timeline**.

---

## Where to run encode commands

Run all encode commands from the `scripts/` root:

`python star_run.py encode --case CASE --csv dataset.csv --out DATASET_STAR`
