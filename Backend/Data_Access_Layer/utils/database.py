from contextvars import ContextVar
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from Backend.config.env_loader import get_env_var

DATABASE_URL = get_env_var("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

_db_session_ctx: ContextVar[Optional[Session]] = ContextVar("_db_session_ctx", default=None)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_db_session() -> Session:
    """Open a new session for the current request and store it in a ContextVar."""
    db = SessionLocal()
    _db_session_ctx.set(db)
    return db


def get_current_db_session() -> Optional[Session]:
    """Fetch the session opened by set_db_session for the current request, if any."""
    return _db_session_ctx.get()


def remove_db_session() -> None:
    """Close the current request's session and clear it from the ContextVar."""
    db = _db_session_ctx.get()
    if db is not None:
        db.close()
    _db_session_ctx.set(None)
