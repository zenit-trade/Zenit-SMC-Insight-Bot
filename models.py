import os
import datetime as dt
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, Enum
)
from sqlalchemy.orm import declarative_base, sessionmaker
import enum

# Railway auto-injects DATABASE_URL when you attach a Postgres plugin.
# Falls back to a local SQLite file for development.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./zenit_trades.db")

# Railway's Postgres URL sometimes starts with postgres:// — SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Direction(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class Status(str, enum.Enum):
    OPEN = "OPEN"
    TP_HIT = "TP_HIT"
    SL_HIT = "SL_HIT"


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    signal_id = Column(String, unique=True, index=True, nullable=False)
    symbol = Column(String, default="XAUUSD")
    direction = Column(Enum(Direction), nullable=False)
    entry_price = Column(Float, nullable=False)
    sl_price = Column(Float, nullable=False)
    tp_price = Column(Float, nullable=False)
    status = Column(Enum(Status), default=Status.OPEN, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    exit_price = Column(Float, nullable=True)


def init_db():
    Base.metadata.create_all(bind=engine)
