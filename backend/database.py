from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import config

_is_sqlite = config.DATABASE_URL.startswith("sqlite")

engine = create_engine(
    config.DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    # pool_pre_ping matters for hosted/serverless Postgres (Neon, Supabase,
    # etc.) - those close idle connections behind the scenes, and without
    # this SQLAlchemy would hand out a dead connection and the very next
    # request would fail with "server closed the connection unexpectedly."
    # It's a no-op for SQLite, so safe to leave on unconditionally.
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
