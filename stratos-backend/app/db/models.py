from sqlalchemy import (
    Column,
    String,
    Integer,
    ForeignKey,
    Text,
    DateTime,
    func,
    Boolean,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.db.database import Base
import uuid


def generate_uuid():
    return str(uuid.uuid4())


# -----------------------------
# USERS
# -----------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String)
    picture_url = Column(String)
    created_at = Column(DateTime, server_default=func.now())

    sessions = relationship("Session", back_populates="user")


# -----------------------------
# SESSIONS
# -----------------------------
class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"))
    status = Column(String, default="active")
    idea_description = Column(Text)
    clarified_summary = Column(Text)
    # 🔥 NEW (single field)
    clarification_schema = Column(JSONB, default=dict)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="sessions")
    reports = relationship("Report", back_populates="session")
    chats = relationship("ChatMessage", back_populates="session")


# -----------------------------
# REPORTS
# -----------------------------
class Report(Base):
    __tablename__ = "reports"

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("sessions.id"))
    topic = Column(String)
    status = Column(String, default="initializing")
    created_at = Column(DateTime, server_default=func.now())

    session = relationship("Session", back_populates="reports")
    sections = relationship("Section", back_populates="report")
    sources = relationship("Source", back_populates="report")
    competitors = relationship("Competitor", back_populates="report")
    trends = relationship("Trend", back_populates="report")
    exports = relationship("ExportRecord", back_populates="report")


# -----------------------------
# SECTIONS
# -----------------------------
class Section(Base):
    __tablename__ = "sections"

    id = Column(String, primary_key=True, default=generate_uuid)
    report_id = Column(String, ForeignKey("reports.id"))
    title = Column(String)
    order_index = Column(Integer)

    report = relationship("Report", back_populates="sections")
    chunks = relationship("Chunk", back_populates="section")


# -----------------------------
# CHUNKS
# -----------------------------
class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(String, primary_key=True, default=generate_uuid)
    section_id = Column(String, ForeignKey("sections.id"))
    chunk_text = Column(Text)
    chunk_index = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())

    section = relationship("Section", back_populates="chunks")
    citations = relationship("Citation", back_populates="chunk")


# -----------------------------
# CITATIONS
# -----------------------------
class Citation(Base):
    __tablename__ = "citations"

    id = Column(String, primary_key=True, default=generate_uuid)
    chunk_id = Column(String, ForeignKey("chunks.id"))
    source_id = Column(String, ForeignKey("sources.id"))
    citation_marker = Column(String)
    quote = Column(Text)

    chunk = relationship("Chunk", back_populates="citations")
    source = relationship("Source", back_populates="citations")


# -----------------------------
# SOURCES (Postgres metadata only)
# -----------------------------
class Source(Base):
    __tablename__ = "sources"

    id = Column(String, primary_key=True, default=generate_uuid)
    report_id = Column(String, ForeignKey("reports.id"))
    url = Column(String)
    domain = Column(String)
    type = Column(String)
    created_at = Column(DateTime, server_default=func.now())

    report = relationship("Report", back_populates="sources")
    citations = relationship("Citation", back_populates="source")
    evidence = relationship("SourceEvidence", back_populates="source")


# -----------------------------
# SOURCE EVIDENCE (metadata only)
# -----------------------------
class SourceEvidence(Base):
    __tablename__ = "source_evidence"

    id = Column(String, primary_key=True, default=generate_uuid)
    source_id = Column(String, ForeignKey("sources.id"))
    snippet = Column(Text)

    source = relationship("Source", back_populates="evidence")


# -----------------------------
# COMPETITORS
# -----------------------------
class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(String, primary_key=True, default=generate_uuid)
    report_id = Column(String, ForeignKey("reports.id"))
    name = Column(String)
    website = Column(String)
    summary = Column(Text)

    report = relationship("Report", back_populates="competitors")
    features = relationship("CompetitorFeature", back_populates="competitor")


class CompetitorFeature(Base):
    __tablename__ = "competitor_features"

    id = Column(String, primary_key=True, default=generate_uuid)
    competitor_id = Column(String, ForeignKey("competitors.id"))
    feature = Column(String)
    strength = Column(Text)
    weakness = Column(Text)

    competitor = relationship("Competitor", back_populates="features")


# -----------------------------
# TRENDS
# -----------------------------
class Trend(Base):
    __tablename__ = "trends"

    id = Column(String, primary_key=True, default=generate_uuid)
    report_id = Column(String, ForeignKey("reports.id"))
    category = Column(String)

    report = relationship("Report", back_populates="trends")
    items = relationship("TrendItem", back_populates="trend")


class TrendItem(Base):
    __tablename__ = "trend_items"

    id = Column(String, primary_key=True, default=generate_uuid)
    trend_id = Column(String, ForeignKey("trends.id"))
    title = Column(String)
    url = Column(String)
    summary = Column(Text)
    published_at = Column(DateTime)


    trend = relationship("Trend", back_populates="items")


# -----------------------------
# CHAT MESSAGES
# -----------------------------
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("sessions.id"))
    role = Column(String)  # user | assistant
    message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    session = relationship("Session", back_populates="chats")


# -----------------------------
# EXPORTS
# -----------------------------
class ExportRecord(Base):
    __tablename__ = "exports"

    id = Column(String, primary_key=True, default=generate_uuid)
    report_id = Column(String, ForeignKey("reports.id"))
    file_type = Column(String)
    file_url = Column(String)
    created_at = Column(DateTime, server_default=func.now())

    report = relationship("Report", back_populates="exports")
