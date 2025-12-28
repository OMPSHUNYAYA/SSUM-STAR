# ⭐ SSUM-STAR — Quickstart Guide

**Deterministic • Offline • Lossless • Indexed Seek • Exact Replay**

*(Structural Time And Replay — SSUM compliant)*

---

## **1. Purpose of This Quickstart**

This guide helps you:
- run SSUM-STAR without modifying any scripts
- understand the encode → index → replay cycle
- verify determinism and replay correctness on your machine

This is a **hands-on execution guide**, not a theoretical document.

For conceptual background, see the PDFs in the `docs/` folder.

---

## **2. Requirements**

SSUM-STAR is fully offline and deterministic.

**Required**
- Python 3.8 or newer

**Not required**
- external libraries
- databases
- internet access
- randomness
- background services

If Python runs, SSUM-STAR runs.

---

## **3. One-Minute Mental Model**

SSUM-STAR performs **structural compression**, not byte compression.

Core invariant:

```
decode(encode(structure)) == structure
```

Key ideas:
- order is intrinsic
- time is derived
- replay is exact
- truth is preserved

The `.star` file is not storage.  
The `.star` file **is the timeline**.

Indexes accelerate seek.  
Indexes never define correctness.

---

## **4. STAR Execution Cycle**

### **Step 1 — Encode**

Conceptual form:

```
python star_run.py encode --case CASE --csv dataset.csv --out DATASET_STAR
```

What happens:
- dataset parsed deterministically
- initial state recorded
- structural deltas encoded
- structural time derived
- `.star` artifact produced

Guarantee:

```
decode(encode(parsed)) == parsed
```

---

### **Step 2 — Index (Optional)**

Conceptual form:

```
python star_run.py index --star DATASET_STAR.star --out DATASET_STAR.star.idx --anchor_every N
```

Notes:
- index is optional
- index is disposable
- replay correctness never depends on the index

---

### **Step 3 — Replay**

Replay by row:

```
python star_run.py replay --star DATASET_STAR.star --idx DATASET_STAR.star.idx --seek_row R --rows K
```

Replay by structural time:

```
python star_run.py replay --star DATASET_STAR.star --idx DATASET_STAR.star.idx --seek_time T --rows K
```

Replay is:
- deterministic
- exact
- bounded
- reproducible indefinitely

---

## **5. Structural Time**

Time is not stored.

Time is derived as:

```
T_structural = sequence_index + invariant_continuity
```

Properties:
- clock-independent
- timezone-independent
- metadata-independent

Missing data remains missing.  
Faults remain faults.  
Nothing is fabricated.

---

## **6. Determinism Checks (Recommended)**

To confirm correctness:
- encode the same dataset twice → identical `.star`
- replay from multiple seek positions → identical output
- delete index → replay still works
- rebuild index → anchors identical
- seek out of bounds → safe termination

Each confirms a structural invariant.

---

## **7. What SSUM-STAR Is Not**

SSUM-STAR is not:
- a probabilistic compressor
- a machine learning model
- a predictor
- a repair or smoothing tool
- a time-series database

STAR preserves structure.  
STAR preserves truth.

---

## **8. Safety Notice**

Intended for:
- research
- education
- archival
- audit and reproducibility

Not intended for:
- real-time control
- safety-critical systems
- live decision-making

Failures are explicit.  
Silent corruption is not allowed.

---

## **9. One-Line Summary**

SSUM-STAR compresses time itself — producing deterministic artifacts that can be replayed exactly as history.

---

**END OF QUICKSTART**
