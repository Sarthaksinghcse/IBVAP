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
    - IBVAP_API_KEY (default: 'admin-key') -> admin
    - IBVAP_OPERATOR_KEY (default: 'operator-key') -> operator
    - anything else or missing -> viewer (read-only)
    """
    async def dispatch(self, request: Request, call_next):
        # Allow open access to frontend static and non-API routes
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        admin_key = os.getenv("IBVAP_API_KEY", "admin-key")
        operator_key = os.getenv("IBVAP_OPERATOR_KEY", "operator-key")

        api_key = request.headers.get("x-api-key") or request.query_params.get("api_key")

        # Determine role
        if api_key == admin_key:
            role = "admin"
            user = "Admin User"
        elif api_key == operator_key:
            role = "operator"
            user = "Operator 1"
        else:
            role = "viewer"
            user = "Anonymous Viewer"

        request.state.user = {"name": user, "role": role}

        # S1: Restrict biometric template downloads to admin only
        if request.url.path == "/api/watchlist/embeddings" and role != "admin":
            return JSONResponse(
                status_code=403,
                content={"detail": "Admin privileges required to access biometric templates."}
            )

        # Restrict registry writes (POST/PUT/PATCH/DELETE to /api/watchlist) to admin only
        if request.url.path.startswith("/api/watchlist") and request.method in ["POST", "PUT", "PATCH", "DELETE"]:
            # Test-match is safe for non-admins if needed, but registry mutations require admin
            if role != "admin":
                if not request.url.path.endswith("/test-match"):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Admin privileges required to modify the biometric registry."}
                    )

        return await call_next(request)
