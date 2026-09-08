from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

class MockAuthMiddleware(BaseHTTPMiddleware):
    """
    Phase 5.3: Token-based auth middleware (mock implementation).
    Assigns role based on x-api-key header:
    - 'admin-key' -> admin
    - 'operator-key' -> operator
    - anything else or missing -> viewer (read-only)
    """
    async def dispatch(self, request: Request, call_next):
        # Allow open access to frontend static and non-API routes
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
            
        api_key = request.headers.get("x-api-key")
        
        # Determine role
        if api_key == "admin-key":
            role = "admin"
            user = "Admin User"
        elif api_key == "operator-key":
            role = "operator"
            user = "Operator 1"
        else:
            role = "viewer"
            user = "Anonymous Viewer"
            
        request.state.user = {"name": user, "role": role}
        
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
