"""
ESGrow Database Configuration
SQLite for local dev, PostgreSQL on Render.
"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()


def get_database_url():
    url = os.environ.get("DATABASE_URL")
    if url:
        # Render provides postgres:// but SQLAlchemy 2.x requires postgresql://
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    # Local development: SQLite in data/
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "data", "esgrow.db")
    return f"sqlite:///{db_path}"


engine = create_engine(get_database_url(), echo=False)

# Enable foreign keys for SQLite
if engine.url.drivername == "sqlite":
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Create all tables. Safe to call multiple times."""
    import models  # noqa: F401 — ensure models are registered
    Base.metadata.create_all(engine)


def get_session():
    """Convenience for scripts."""
    return SessionLocal()
