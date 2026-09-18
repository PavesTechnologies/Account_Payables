from contextvars import ContextVar
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from Backend.config.env_loader import get_env_var

DATABASE_URL = get_env_var("DATABASE_URL")

# Enforce strict pool limits and pre-ping checks for low connection limits
engine = create_engine(
    DATABASE_URL,
    pool_size=3,             # Maximum persistent connections kept open
    max_overflow=2,          # Additional temporary connections allowed during spikes (Total max = 5)
    pool_timeout=10,         # Seconds to wait for an available connection before raising an error
    pool_recycle=1800,       # Recycle connections older than 30 minutes
    pool_pre_ping=True,      # Test connections before checkout to handle dropped sockets
)

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