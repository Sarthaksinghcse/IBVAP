import os
import sys
import base64
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from fastapi.testclient import TestClient
from main import app
from database.database import get_db, Base, engine
from models.models import User, UserFaceEmbedding

client = TestClient(app)

def test_full_face_authentication_lifecycle():
    # Ensure fresh DB tables
    Base.metadata.create_all(bind=engine)

    # Clean up test users from DB
    db = next(get_db())
    try:
        db.query(UserFaceEmbedding).delete()
        db.query(User).filter(User.email == "commander.adams@shield.gov").delete()
        db.commit()
    finally:
        db.close()

    # Load test operator face image
    test_img_path = PROJECT_ROOT / "tests" / "test_operator_face.jpg"
    assert test_img_path.exists(), f"Test image not found at {test_img_path}"
    
    with open(test_img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    # 1. Register new operator via webcam base64 payload
    reg_payload = {
        "name": "Commander Adams",
        "email": "commander.adams@shield.gov",
        "role": "admin",
        "image_base64": f"data:image/jpeg;base64,{img_b64}"
    }

    reg_resp = client.post("/api/auth/register-webcam", json=reg_payload)
    assert reg_resp.status_code == 200, f"Registration failed: {reg_resp.text}"
    reg_data = reg_resp.json()
    assert "token" in reg_data
    assert reg_data["name"] == "Commander Adams"
    assert reg_data["role"] == "admin"
    user_id = reg_data["user_id"]
    jwt_token = reg_data["token"]
    print(f"[*] Registered user {user_id} with JWT token.")

    # 2. Duplicate registration test (must return 409 Conflict)
    dup_payload = {
        "name": "Imposter Adams",
        "email": "imposter@shield.gov",
        "role": "operator",
        "image_base64": f"data:image/jpeg;base64,{img_b64}"
    }
    dup_resp = client.post("/api/auth/register-webcam", json=dup_payload)
    assert dup_resp.status_code == 409, f"Expected 409 Conflict, got {dup_resp.status_code}: {dup_resp.text}"
    print("[*] Duplicate face rejected with 409 Conflict.")

    # 3. Biometric Login with face
    login_payload = {
        "image_base64": f"data:image/jpeg;base64,{img_b64}"
    }
    login_resp = client.post("/api/auth/login-webcam", json=login_payload)
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    login_data = login_resp.json()
    assert login_data["user_id"] == user_id
    assert login_data["name"] == "Commander Adams"
    assert "token" in login_data
    auth_token = login_data["token"]
    print(f"[*] Biometric face login successful, similarity confidence: {login_data.get('confidence')}%")

    # 4. Verify /me endpoint with Bearer token
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
    assert me_resp.status_code == 200, f"/me failed: {me_resp.text}"
    me_data = me_resp.json()
    assert me_data["user_id"] == user_id
    assert me_data["name"] == "Commander Adams"
    assert me_data["role"] == "admin"
    print("[*] /me authenticated successfully with Bearer token.")

    # 5. Verify /me rejected with missing or invalid token
    unauth_resp = client.get("/api/auth/me")
    assert unauth_resp.status_code == 401, f"Expected 401, got {unauth_resp.status_code}"
    print("[*] Unauthorized access correctly returned 401.")

    # 6. Verify user photo retrieval endpoint
    photo_resp = client.get(f"/api/auth/users/{user_id}/photo")
    assert photo_resp.status_code == 200, f"Photo retrieval failed: {photo_resp.status_code}"
    assert photo_resp.headers["content-type"] in ["image/jpeg", "image/jpg"]
    print("[*] User photo retrieved successfully.")

if __name__ == "__main__":
    test_full_face_authentication_lifecycle()
    print("\nALL FACE AUTHENTICATION INTEGRATION TESTS PASSED SUCCESSFULLY!")
