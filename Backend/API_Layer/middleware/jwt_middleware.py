from fastapi import status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from Backend.API_Layer.utils.jwt_validator import decode_access_token

PUBLIC_PATHS = {
    "/",
    "/apm/docs",
    "/apm/redoc",
    "/apm/openapi.json",
    "/apm/health",
}


class JWTMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"success": False, "message": "Missing or invalid Authorization header"},
            )

        token = auth_header.split(" ", 1)[1]
        payload = await decode_access_token(token)
        if payload is None:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"success": False, "message": "Invalid or expired token"},
            )

        request.state.user = payload
        return await call_next(request)
