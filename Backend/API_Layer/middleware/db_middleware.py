import logging
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.Data_Access_Layer.utils.database import (
    remove_db_session,
    set_db_session,
)

logger = logging.getLogger(__name__)


class DBSessionMiddleware(BaseHTTPMiddleware):
    """
    Middleware to manage database session lifecycle per request.
    Ensures session creation before processing and cleanup after.
    """

    async def dispatch(self, request: Request, call_next):
        t_start = time.time()
        logger.info(
            "DB Middleware - ENTERING %s %s",
            request.method,
            request.url.path,
        )

        db = None

        try:
            db = set_db_session()
            request.state.db = db

            logger.info("DB Middleware - DB session initialized")

            response = await call_next(request)

            return response

        except SQLAlchemyError:
            logger.exception(
                "DB Middleware - SQLAlchemyError for %s %s",
                request.method,
                request.url.path,
            )

            if db is not None:
                try:
                    db.rollback()
                except Exception:
                    logger.exception(
                        "DB Middleware - Rollback failed"
                    )

            return JSONResponse(
                {"detail": "A database error occurred."},
                status_code=500,
            )

        except Exception:
            logger.exception(
                "DB Middleware - Unexpected Error for %s %s",
                request.method,
                request.url.path,
            )

            if db is not None:
                try:
                    db.rollback()
                except Exception:
                    logger.exception(
                        "DB Middleware - Rollback failed"
                    )

            return JSONResponse(
                {"detail": "Internal server error."},
                status_code=500,
            )

        finally:
            try:
                remove_db_session()
            except Exception:
                logger.exception(
                    "DB Middleware - Failed to remove DB session"
                )

            elapsed = (time.time() - t_start) * 1000

            logger.info(
                "DB Middleware: %.2fms - Session removed and EXITING",
                elapsed,
            )