import logging
import time

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from Backend.API_Layer.middleware.jwt_middleware import JWTMiddleware
from Backend.API_Layer.routes import health_routes
from Backend.Data_Access_Layer.models import Base
from Backend.Data_Access_Layer.utils.database import engine
from Backend.config.env_loader import get_env_var

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Accounts Payable Module",
    description="Accounts Payable API secured with JWT (validated via UMS OpenID/JWKS)",
    version="1.0.0",
    docs_url="/apm/docs",
    redoc_url="/apm/redoc",
    openapi_url="/apm/openapi.json",
)

FRONTEND_URL = get_env_var("FRONTEND_URL", "http://localhost:5173")

app.add_middleware(JWTMiddleware)

# Add CORS last so it wraps *all* responses
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
    max_age=3600,
)


@app.middleware("http")
async def add_timing_middleware(request: Request, call_next):
    t_start = time.time()
    path = request.url.path
    method = request.method

    logger.info(f"REQUEST START: {method} {path}")

    response = await call_next(request)

    elapsed = (time.time() - t_start) * 1000
    response.headers["X-Response-Time"] = f"{elapsed:.2f}ms"

    logger.info(
        f"REQUEST END: {method} {path} - {elapsed:.2f}ms - Status: {response.status_code}"
    )

    if elapsed > 1000:
        logger.error(f"VERY SLOW REQUEST: {method} {path} took {elapsed:.2f}ms")
    elif elapsed > 500:
        logger.warning(f"SLOW REQUEST: {method} {path} took {elapsed:.2f}ms")

    return response


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Accounts Payable Module",
        version="1.0.0",
        description="Accounts Payable API secured with JWT (validated via UMS OpenID/JWKS)",
        routes=app.routes,
    )
    openapi_schema.setdefault("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    }
    for path in openapi_schema["paths"]:
        for method in openapi_schema["paths"][path]:
            if method in ["get", "post", "put", "delete", "patch"]:
                openapi_schema["paths"][path][method]["security"] = [{"BearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]

api_router = APIRouter(prefix="/apm")

api_router.include_router(health_routes.router, tags=["Health"])

app.include_router(api_router)


@app.get("/")
def read_root():
    return {"status": "Accounts Payable Module API is running"}


# if __name__ == "__main__":
#     import uvicorn

#     uvicorn.run(
#         "main:app",
#         host=get_env_var("HOST", "0.0.0.0"),
#         port=int(get_env_var("PORT", "8000")),
#         reload=True,
#     )
