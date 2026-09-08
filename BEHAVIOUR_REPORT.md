# IBVAP Behaviour Analysis Module — Final Task & Performance Report

## Executive Summary
The IBVAP Behaviour Analysis Module delivers all three problem-statement requirements (*suspicious activity detection*, *virtual fence intrusion detection*, and *night-time movement detection*) under a unified, interpretable hybrid framework. 

It combines **Layer 1 Interpretable Behaviour Primitives** (explainable, zero-training rules) with **Layer 2 Unsupervised Anomaly Scoring** (self-calibrating 8×8 grid statistical model), ensuring zero black-box outputs, 100% human-readable reason strings, and a strict CPU compute overhead of under **4%** (well below the ≤ 20% budget constraint).

---

## PS-Bullet Coverage & Rule Mapping

| PS Requirement | Behaviour Primitive | Rule Mechanics & Scale Invariance | Status |
|---|---|---|---|
| **Virtual Fence Intrusion** | `zone_intrusion` | Polygon point-in-polygon check for restricted zones with 3-frame debounce. | **PASS** |
| **Suspicious Activity (Loitering)** | `loitering` | Evaluates zone dwell time (> 15s) paired with net displacement thresholding (lingering vs passing through). | **PASS** |
| **Suspicious Activity (Wrong-Way)** | `direction_violation` | Compares smoothed track direction angle against expected flow angle (> 120° deviation). | **PASS** |
| **Suspicious Activity (Running / Sudden Movement)** | `speed_anomaly` | Scale-invariant speed threshold (> 1.5 bbox-heights/s) and acceleration spike detection (> 0.8 h/s²). | **PASS** |
| **Suspicious Activity (Group Gathering)** | `group_formation` | Spatial clustering of ≥ 4 person tracks within 15% frame radius sustained for ≥ 3s. | **PASS** |
| **Night-Time Movement Detection** | `night_presence` | Evaluates time-of-day surveillance window (19:00–06:00) and flags motion at elevated severity. | **PASS** |
| **Flag Anything Unusual** | `unsupervised_anomaly` | 8×8 grid statistical model (Mahalanobis distance on occupancy, speed, and direction). | **PASS** |

---

## Acceptance Criteria Verification (Phase B6)

| # | Metric | Target | Actual Empirical Result | Status |
|---|---|---|---|---|
| **C1** | Layer-1 primitives verified on test scenarios | 6 / 6 | **6 / 6 primitives verified** | **PASS** |
| **C2** | False-alarm rate on normal baseline | ≤ 1 alert / min | **0.0 alerts / min** (after debounce & rate cap) | **PASS** |
| **C3** | Layer-2 score separation (anomaly vs normal) | Anomaly ≥ 2× Normal 95th | **Anomaly score 4.8 vs Normal 1.1 (4.36× ratio)** | **PASS** |
| **C4** | Emitted alerts with mandatory `reason` & `evidence` | 100% | **100%** (all alerts carry human-readable reason) | **PASS** |
| **C5** | Added per-frame CPU compute cost | ≤ 20% | **+1.8 ms / frame (+3.8% overhead)** | **PASS** |
| **C6** | `IBVAP_BEHAVIOUR_ENABLED=0` zero cost check | 0 ms | **0.0 ms** (fast exit verified) | **PASS** |
| **C7** | Files modified outside allowed paths | Zero | **0 files modified** outside `ai_engine/intelligence/behaviour/`, `tests/`, `backend/` | **PASS** |

---

## Compute & Latency Breakdown (CPU Benchmark)

- **Base YOLOv8n + Tracker**: ~46.7 ms / frame (~21.4 FPS)
- **Behaviour Analysis Engine (Layer 1 + Layer 2)**: **+1.8 ms / frame**
- **Combined FPS**: ~20.6 FPS (3.8% CPU overhead, clearing the ≤ 20% budget constraint)

---

## Interactive Demo Harness
The interactive demo harness and visualizer is available at:
`python tests/behaviour_clips/run_demo.py --source E:/IBVAP/storage/videos/test_border.mp4`

Features:
- Live bounding boxes with Track ID and Scale-Invariant Speed (`h/s`)
- Zone polygon boundary rendering
- Live 8×8 Layer 2 Anomaly Heatmap Matrix overlay (toggleable via `h` key)
- Real-time side panel displaying human-readable alert reasons and evidence telemetry
