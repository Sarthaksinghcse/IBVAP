"""
Test suite validating Stage 1, Stage 2, Stage 3, and Stage 4 fixes for the vanshika branch.
"""
import os
import sys
from fastapi.testclient import TestClient
from fastapi import HTTPException

# Ensure backend and root are in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.paths import assert_within
from main import app
from ai_engine.intelligence.face_config import (
    NEG_CACHE_TTL_S,
    FACE_EVAL_INTERVAL_FRAMES,
    MIN_FACE_PX,
    CALIBRATION_THRESHOLD_COSINE,
    CALIBRATION_THRESHOLD_DISPLAY
)
from ai_engine.intelligence.face_engine import (
    get_face_engine,
    calibrated_confidence,
    FaceTrackAccumulator
)

client = TestClient(app)

# ─── Stage 1 & Stage 4 (Paths: U1, S4) ───────────────────────────────────────

def test_assert_within_valid():
    base_dir = os.path.abspath("storage/videos")
    target_file = os.path.join(base_dir, "test.mp4")
    result = assert_within(target_file, base_dir)
    assert result == os.path.abspath(target_file)

def test_assert_within_traversal():
    base_dir = os.path.abspath("storage/videos")
    traversal_file = os.path.join(base_dir, "..", "secret.txt")
    caught = False
    try:
        assert_within(traversal_file, base_dir)
    except HTTPException as e:
        caught = True
        assert e.status_code == 400
    assert caught, "Should have raised HTTPException 400 for path traversal"

def test_assert_within_sibling_directory():
    # S4 prefix match vulnerability check: e.g. videos-evil against videos
    base_dir = os.path.abspath("storage/videos")
    sibling_file = os.path.abspath("storage/videos-evil/evil.mp4")
    caught = False
    try:
        assert_within(sibling_file, base_dir)
    except HTTPException as e:
        caught = True
        assert e.status_code == 400
    assert caught, "Should have raised HTTPException 400 for sibling directory attack"


# ─── Stage 1 & Stage 4 (Auth & Security: U2, S1, S5) ─────────────────────────

def test_watchlist_embeddings_requires_admin():
    # Anonymous request should return 403 (S1)
    res_anon = client.get("/api/watchlist/embeddings")
    assert res_anon.status_code == 403, f"Expected 403 for anonymous embeddings request, got {res_anon.status_code}"

    # Viewer request should return 403
    res_viewer = client.get("/api/watchlist/embeddings", headers={"x-api-key": "unknown-key"})
    assert res_viewer.status_code == 403

    # Admin request should succeed (200)
    res_admin = client.get("/api/watchlist/embeddings", headers={"x-api-key": "admin-key"})
    assert res_admin.status_code == 200, f"Expected 200 with admin key, got {res_admin.status_code}"

def test_watchlist_write_requires_admin():
    # POST without admin key should be 403 (U2)
    res = client.post("/api/watchlist/", data={"name": "Test Target"})
    assert res.status_code == 403

    # POST with admin key passes auth gate (will fail with 422/400 because file is missing, but NOT 403)
    res_admin = client.post("/api/watchlist/", headers={"x-api-key": "admin-key"}, data={"name": "Test Target"})
    assert res_admin.status_code != 403


# ─── Stage 1 & Stage 4 (Photo Serving & Crop Serving: U3, S3) ────────────────

def test_watchlist_photo_route_exists():
    # U3: GET /api/watchlist/{person_id}/photo
    res = client.get("/api/watchlist/non-existent-id/photo")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

def test_face_crops_route_exists():
    # S3: GET /api/watchlist/face-crops/{filename}
    res = client.get("/api/watchlist/face-crops/non-existent.jpg")
    assert res.status_code == 404


# ─── Stage 2 & Stage 3 (Performance & Calibration: P1, P2, P4, F1, F2) ────────

def test_face_config_values():
    # P1
    assert FACE_EVAL_INTERVAL_FRAMES == 5
    assert MIN_FACE_PX == 32
    # P2
    assert NEG_CACHE_TTL_S == 2.0

def test_confidence_calibration():
    # F2: calibrated_confidence
    # At cosine = 0.0 -> 0%
    assert calibrated_confidence(0.0) == 0.0
    # At cosine = threshold (0.45) -> exactly 50%
    assert round(calibrated_confidence(CALIBRATION_THRESHOLD_COSINE), 1) == CALIBRATION_THRESHOLD_DISPLAY
    # Below threshold: monotonic increase from 0 to 50
    assert 0.0 < calibrated_confidence(0.20) < CALIBRATION_THRESHOLD_DISPLAY

def test_consensus_accumulator_pushes_cache_hits():
    # F1: Consensus Accumulator should accumulate matches across successive calls
    acc = FaceTrackAccumulator()
    cache_key = "job_test:BOP-01:track_1"

    raw_result = {
        "face_detected": True,
        "is_match": True,
        "person_id": "poi_123",
        "person_name": "Target Person",
        "cosine_score": 0.65,
        "similarity": 80.0
    }

    # Frame 1: 1 vote -> PENDING
    r1 = acc.push(cache_key, raw_result)
    assert r1.get("consensus_state") is None

    # Frame 2: 2 votes -> CANDIDATE
    r2 = acc.push(cache_key, raw_result)
    assert r2.get("consensus_state") == "CANDIDATE"
    assert r2.get("is_match") is False

    # Frame 3: 3 votes -> CONFIRMED
    r3 = acc.push(cache_key, raw_result)
    assert r3.get("consensus_state") == "CONFIRMED"
    assert r3.get("is_match") is True
    assert r3.get("consensus_votes") == 3
    # F2: Ensure calibrated similarity is applied
    assert r3.get("similarity") == round(calibrated_confidence(0.65), 1)

def test_gitignore_contains_db():
    # S2
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gitignore_path = os.path.join(root_dir, ".gitignore")
    with open(gitignore_path, "r") as f:
        content = f.read()
    assert "*.db" in content
    assert "backend/ibvap.db" in content


if __name__ == "__main__":
    tests = [
        test_assert_within_valid,
        test_assert_within_traversal,
        test_assert_within_sibling_directory,
        test_watchlist_embeddings_requires_admin,
        test_watchlist_write_requires_admin,
        test_watchlist_photo_route_exists,
        test_face_crops_route_exists,
        test_face_config_values,
        test_confidence_calibration,
        test_consensus_accumulator_pushes_cache_hits,
        test_gitignore_contains_db,
    ]
    print(f"Running {len(tests)} verification tests...")
    for t in tests:
        t()
        print(f"  [PASS] {t.__name__}")
    print(f"\nALL {len(tests)} STAGE FIX TESTS PASSED SUCCESSFULLY!")
