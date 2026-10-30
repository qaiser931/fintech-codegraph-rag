"""Durable, tenant-scoped storage. SQLite is permitted for local tests only."""
from __future__ import annotations

import os
import time
import uuid
from functools import lru_cache

from sqlalchemy import (JSON, Column, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint, create_engine, inspect, select, text)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

Base = declarative_base()


def uid():
    return uuid.uuid4().hex


class Workspace(Base):
    __tablename__ = "sw_workspaces"
    owner_id = Column(String, nullable=True, index=True)
    id = Column(String, primary_key=True, default=uid)
    name = Column(String(100), nullable=False)
    color = Column(String, default="teal")
    created = Column(Float, default=time.time)
    github_token = Column(Text, default="")  # Fernet ciphertext, never returned.
    webhook_secret = Column(Text, default="")  # Fernet ciphertext.


class AccessKey(Base):
    __tablename__ = "sw_access_keys"
    id = Column(String, primary_key=True)  # SHA256 of a random 256-bit token.
    workspace_id = Column(String, ForeignKey("sw_workspaces.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    role = Column(String, nullable=False)
    created = Column(Float, default=time.time)
    revoked = Column(Integer, default=0)


class Session(Base):
    __tablename__ = "sw_sessions"
    id = Column(String, primary_key=True)
    access_id = Column(String, nullable=False)
    workspace_id = Column(String, nullable=True)
    role = Column(String, nullable=False)
    name = Column(String, nullable=False)
    csrf = Column(String, nullable=False)
    expires = Column(Float, nullable=False)


class Attempt(Base):
    __tablename__ = "sw_login_attempts"
    id = Column(String, primary_key=True, default=uid)
    address = Column(String, index=True)
    created = Column(Float, default=time.time, index=True)


class Repository(Base):
    __tablename__ = "sw_repositories"
    __table_args__ = (UniqueConstraint("workspace_id", "full_name"),)
    id = Column(String, primary_key=True, default=uid)
    workspace_id = Column(String, ForeignKey("sw_workspaces.id"), nullable=False, index=True)
    full_name = Column(String, nullable=False)
    branch = Column(String, default="")
    sha = Column(String, default="")
    status = Column(String, default="not_indexed")
    snapshot = Column(JSON, default=dict)
    dependencies = Column(JSON, default=dict)
    ci = Column(JSON, default=dict)
    prs = Column(JSON, default=list)
    indexed = Column(Float, nullable=True)
    index_order = Column(Float, default=0, nullable=False)
    created = Column(Float, default=time.time)


class Review(Base):
    __tablename__ = "sw_reviews"
    __table_args__ = (UniqueConstraint("repo_id", "number", "sha"),)
    id = Column(String, primary_key=True, default=uid)
    workspace_id = Column(String, ForeignKey("sw_workspaces.id"), nullable=False, index=True)
    repo_id = Column(String, ForeignKey("sw_repositories.id"), nullable=False, index=True)
    number = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    sha = Column(String, nullable=False)
    base_sha = Column(String, default="")
    status = Column(String, default="needs_review")
    summary = Column(Text, default="")
    files = Column(JSON, default=list)
    context = Column(JSON, default=list)
    checks = Column(JSON, default=dict)
    created = Column(Float, default=time.time)
    elapsed = Column(Float, default=0)


class Finding(Base):
    __tablename__ = "sw_findings"
    id = Column(String, primary_key=True, default=uid)
    workspace_id = Column(String, ForeignKey("sw_workspaces.id"), nullable=False, index=True)
    review_id = Column(String, ForeignKey("sw_reviews.id"), nullable=False, index=True)
    severity = Column(String, nullable=False)
    title = Column(String, nullable=False)
    detail = Column(Text, nullable=False)
    next_step = Column(Text, nullable=False)
    evidence = Column(JSON, nullable=False)
    patch = Column(Text, default="")
    origin = Column(String, default="static")
    status = Column(String, default="open")
    feedback = Column(String, nullable=True)
    updated = Column(Float, default=time.time)
    created = Column(Float, default=time.time)


class Job(Base):
    __tablename__ = "sw_jobs"
    __table_args__ = (UniqueConstraint("dedupe"),)
    id = Column(String, primary_key=True, default=uid)
    workspace_id = Column(String, ForeignKey("sw_workspaces.id"), nullable=False, index=True)
    repo_id = Column(String, ForeignKey("sw_repositories.id"), nullable=False)
    kind = Column(String, nullable=False)
    payload = Column(JSON, default=dict)
    dedupe = Column(String, nullable=False)
    stage = Column(String, default="snapshot")
    status = Column(String, default="queued")
    error = Column(Text, default="")
    result_id = Column(String, default="")
    lease_until = Column(Float, default=0)
    created = Column(Float, default=time.time)
    updated = Column(Float, default=time.time)


class Report(Base):
    __tablename__ = "sw_reports"
    __table_args__ = (UniqueConstraint("workspace_id", "period"),)
    id = Column(String, primary_key=True, default=uid)
    workspace_id = Column(String, ForeignKey("sw_workspaces.id"), nullable=False, index=True)
    period = Column(String, nullable=False)
    title = Column(String, nullable=False)
    markdown = Column(Text, nullable=False)
    created = Column(Float, default=time.time)


class Audit(Base):
    __tablename__ = "sw_audit"
    id = Column(String, primary_key=True, default=uid)
    workspace_id = Column(String, nullable=True, index=True)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    created = Column(Float, default=time.time)


@lru_cache(maxsize=1)
def database():
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("Connect a Postgres database and set DATABASE_URL.")
    local = url.startswith("sqlite:")
    if local and (os.getenv("VERCEL") or os.getenv("STACKWISE_LOCAL") != "1"):
        raise RuntimeError("SQLite is only supported with STACKWISE_LOCAL=1 outside Vercel.")
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if not local and not url.startswith("postgresql+psycopg://"):
        raise RuntimeError("Use a Postgres DATABASE_URL.")
    options = ({"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
               if local else {"poolclass": NullPool, "connect_args": {"connect_timeout": 8}})
    engine = create_engine(url, **options)
    Base.metadata.create_all(engine)
    try:
        inspector = inspect(engine)
        if "sw_workspaces" in inspector.get_table_names():
            columns = [c["name"] for c in inspector.get_columns("sw_workspaces")]
            if "owner_id" not in columns:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE sw_workspaces ADD COLUMN owner_id VARCHAR"))
    except Exception:
        pass
    return sessionmaker(bind=engine, expire_on_commit=False)


def accessible_workspaces_query(identity):
    if identity.access_id == "owner":
        return select(Workspace).where((Workspace.owner_id == "owner") | (Workspace.owner_id == None))
    elif identity.access_id.startswith("github:"):
        return select(Workspace).where((Workspace.owner_id == identity.access_id) | (Workspace.id == identity.workspace_id))
    else:
        return select(Workspace).where(Workspace.id == identity.workspace_id)


def scoped(query, model, identity):
    """Every collection lookup goes through the same authorization predicate."""
    if identity.access_id == "owner":
        ws_subquery = select(Workspace.id).where((Workspace.owner_id == "owner") | (Workspace.owner_id == None))
        if hasattr(model, "workspace_id"):
            if getattr(model, "__name__", "") == "Audit":
                return query.filter((model.workspace_id.in_(ws_subquery)) | (model.workspace_id == None))
            return query.filter(model.workspace_id.in_(ws_subquery))
        return query
    elif identity.access_id.startswith("github:"):
        ws_subquery = select(Workspace.id).where((Workspace.owner_id == identity.access_id) | (Workspace.id == identity.workspace_id))
        if hasattr(model, "workspace_id"):
            return query.filter(model.workspace_id.in_(ws_subquery))
        return query
    else:
        if hasattr(model, "workspace_id"):
            return query.filter(model.workspace_id == identity.workspace_id)
        return query
