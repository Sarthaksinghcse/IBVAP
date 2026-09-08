import os
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

ADMIN_KEY = os.getenv("IBVAP_API_KEY", "admin-key")
OPERATOR_KEY = os.getenv("IBVAP_OPERATOR_KEY", "operator-key")

class MockAuthMiddleware(BaseHTTPMiddleware):
    """
    Token-based auth middleware.
    Assigns role based on x-api-key header or api_key query param:
    - ADMIN_KEY (from IBVAP_API_KEY env var, default: 'admin-key') -> admin
    - OPERATOR_KEY -> operator
    - anything else or missing -> viewer (read-only)
    """
    async def dispatch(self, request: Request, call_next):
        # Allow open access to frontend static and non-API routes
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        api_key = request.headers.get("x-api-key") or request.query_params.get("api_key")

        # Determine role (S5)
        if api_key == ADMIN_KEY:
            role = "admin"
            user = "Admin User"
        elif api_key == OPERATOR_KEY:
            role = "operator"
            user = "Operator 1"
        else:
            role = "viewer"
            user = "Anonymous Viewer"

        request.state.user = {"name": user, "role": role}

        # Stage 4 S1: Restrict biometric templates export to admin only
        if request.url.path == "/api/watchlist/embeddings" and role != "admin":
            return JSONResponse(
                status_code=403,
                content={"detail": "Admin privileges required to access biometric templates."}
            )

        # Restrict registry writes (POST/PUT/PATCH/DELETE to /api/watchlist) to admin only
        if request.url.path.startswith("/api/watchlist") and request.method in ["POST", "PUT", "PATCH", "DELETE"]:
            # Test-match and photo requests might be allowed by operator, but for strictness:
            if role != "admin":
                # Except test-match which is safe
                if not request.url.path.endswith("/test-match"):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Admin privileges required to modify the biometric registry."}
                    )

        return await call_next(request)
