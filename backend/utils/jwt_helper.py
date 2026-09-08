import os
import jwt
from datetime import datetime, timedelta

SECRET = os.environ.get("IBVAP_JWT_SECRET", "ibvap-jwt-secret-key-2026-secure-auth")
ALGORITHM = "HS256"
EXPIRY_HOURS = 8

def create_token(user_id: str, role: str = "operator", name: str = "") -> str:
    """Generates a signed JWT authentication token."""
    payload = {
        "sub": user_id,
        "name": name,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=EXPIRY_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    """Decodes and validates a signed JWT token. Raises PyJWT exceptions on invalid/expired token."""
    return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
