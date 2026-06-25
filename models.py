"""
ESGrow SQLAlchemy Models
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Sector(Base):
    __tablename__ = "sectors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)
    weight_e = Column(Float, nullable=False)
    weight_s = Column(Float, nullable=False)
    weight_g = Column(Float, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    companies = relationship("Company", back_populates="sector")


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    display_name = Column(String(100), nullable=True)
    sector_id = Column(Integer, ForeignKey("sectors.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

    sector = relationship("Sector", back_populates="companies")
    indicator_scores = relationship("IndicatorScore", back_populates="company")
    score = relationship("Score", back_populates="company", uselist=False)
    score_history = relationship("ScoreHistory", back_populates="company")


class IndicatorDefinition(Base):
    __tablename__ = "indicator_definitions"

    id = Column(String(3), primary_key=True)  # "E01", "G08"
    pillar = Column(String(1), nullable=False)  # "E", "S", "G"
    name = Column(String(200), nullable=False)
    weight = Column(Float, nullable=False)
    sort_order = Column(Integer, nullable=False)

    scores = relationship("IndicatorScore", back_populates="indicator")


class IndicatorScore(Base):
    __tablename__ = "indicator_scores"
    __table_args__ = (
        UniqueConstraint("company_id", "indicator_id", name="uq_company_indicator"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    indicator_id = Column(String(3), ForeignKey("indicator_definitions.id"), nullable=False)
    score = Column(Float, nullable=False)
    raw_value = Column(Text, nullable=True)
    unit = Column(String(50), nullable=True)
    source = Column(String(200), nullable=True)
    report_year = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=utcnow)

    company = relationship("Company", back_populates="indicator_scores")
    indicator = relationship("IndicatorDefinition", back_populates="scores")


class Score(Base):
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), unique=True, nullable=False)
    e_score = Column(Float, nullable=False)
    s_score = Column(Float, nullable=False)
    g_score = Column(Float, nullable=False)
    final_score = Column(Float, nullable=False)
    band = Column(String(20), nullable=False)
    calculated_at = Column(DateTime, default=utcnow)

    company = relationship("Company", back_populates="score")


class ScoreHistory(Base):
    __tablename__ = "score_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    e_score = Column(Float, nullable=False)
    s_score = Column(Float, nullable=False)
    g_score = Column(Float, nullable=False)
    final_score = Column(Float, nullable=False)
    band = Column(String(20), nullable=False)
    calculated_at = Column(DateTime, nullable=False)
    report_year = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    company = relationship("Company", back_populates="score_history")


class FetchLog(Base):
    """Tracks which reports have been scraped and processed."""
    __tablename__ = "fetch_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    report_year = Column(Integer, nullable=True)
    source_url = Column(Text, nullable=True)
    file_hash = Column(String(64), nullable=True)
    status = Column(String(20), nullable=False, default="scraped")
    fetched_at = Column(DateTime, default=utcnow)
    notes = Column(Text, nullable=True)

    company = relationship("Company")
