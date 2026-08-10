import logging

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import httpx

from Backend.API_Layer.utils.jwt_validator import decode_access_token

logger = logging.getLogger(__name__)

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
                content={
                    "success": False,
                    "message": "Missing or invalid Authorization header",
                },
            )

        token = auth_header.split(" ", 1)[1]

        try:
            payload = await decode_access_token(token)

        except httpx.TimeoutException:
            logger.exception(
                "JWT validation failed because UMS/OpenID provider timed out"
            )

            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "success": False,
                    "message": "Authentication service is temporarily unavailable",
                },
            )

        except httpx.HTTPError:
            logger.exception(
                "JWT validation failed because UMS/OpenID provider is unreachable"
            )

            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "success": False,
                    "message": "Authentication service is temporarily unavailable",
                },
            )

        except Exception:
            logger.exception("Unexpected error during JWT validation")

            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "success": False,
                    "message": "Authentication service error",
                },
            )

        if payload is None:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "success": False,
                    "message": "Invalid or expired token",
                },
            )

        request.state.user = payload

        return await call_next(request)