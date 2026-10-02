"""Database tables. IDs are random hex strings (not guessable, not sequential).

No table ever stores a data value from an uploaded dataset. Audit and job rows hold IDs,
counts and codes only.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from nazeer_api.db import utcnow

ROLES = ("admin", "member")
JOB_STATUSES = ("queued", "running", "succeeded", "failed")


def new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    memberships: Mapped[list[Membership]] = relationship(back_populates="user", cascade="all, delete-orphan")

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # The organization's pseudonymization key, AES-256-GCM encrypted under NAZEER_MASTER_KEY.
    enc_key: Mapped[bytes] = mapped_column(LargeBinary(128), nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    memberships: Mapped[list[Membership]] = relationship(back_populates="org", cascade="all, delete-orphan")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_membership_org_user"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")
    data_manager: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    org: Mapped[Organization] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")

    @property
    def can_manage_data(self) -> bool:
        return self.role == "admin" or self.data_manager


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    user: Mapped[User] = relationship()


class EmailToken(Base):
    """Single-use email links (verify / reset). Only the SHA-256 of the token is stored."""
    __tablename__ = "email_tokens"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Invitation(Base):
    __tablename__ = "invitations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")
    data_manager: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    invited_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    org: Mapped[Organization] = relationship()


class Job(Base):
    """A background job. payload/result hold IDs, counts and codes only, never data values."""
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_created", "status", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditEvent(Base):
    """Who did what, when. Never values: IDs, action codes and counts only (enforced in audit.py)."""
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_org_created", "org_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


# ---------------------------------------------------------------- P2: datasets, twins, shares

from sqlalchemy.dialects.mysql import LONGBLOB  # noqa: E402

BlobBytes = LargeBinary().with_variant(LONGBLOB(), "mysql")
DATASET_STATUSES = ("processing", "ready", "failed")


class Dataset(Base):
    """An upload and its processing session. Originals live only in an encrypted, expiring Blob."""
    __tablename__ = "datasets"
    __table_args__ = (Index("ix_datasets_org_created", "org_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="processing")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Structure and detection summary: table/column names, types, tags, counts, span offsets. No values.
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    session_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    originals_deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Blob(Base):
    """Encrypted bytes (AES-256-GCM, per-organization storage key). kinds: upload, tables, twin."""
    __tablename__ = "blobs"
    __table_args__ = (Index("ix_blobs_expires", "expires_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(BlobBytes, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Twin(Base):
    __tablename__ = "twins"
    __table_args__ = (Index("ix_twins_org_created", "org_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    blob_id: Mapped[str | None] = mapped_column(ForeignKey("blobs.id", ondelete="SET NULL"), nullable=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    verdict: Mapped[str] = mapped_column(String(8), nullable=False)
    report: Mapped[dict] = mapped_column(JSON, nullable=False)  # the engine's report: metrics, never values
    proof: Mapped[dict] = mapped_column(JSON, nullable=False)   # the four verdict cards
    key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    dataset: Mapped[Dataset] = relationship()


class Share(Base):
    __tablename__ = "shares"
    __table_args__ = (Index("ix_shares_org_created", "org_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    twin_id: Mapped[str] = mapped_column(ForeignKey("twins.id", ondelete="CASCADE"), nullable=False, index=True)
    formats: Mapped[list] = mapped_column(JSON, nullable=False)
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    twin: Mapped[Twin] = relationship()
    org: Mapped[Organization] = relationship()


class ShareLink(Base):
    """A single-use link for one external recipient; accepting it binds the share to that account."""
    __tablename__ = "share_links"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    share_id: Mapped[str] = mapped_column(ForeignKey("shares.id", ondelete="CASCADE"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    accepted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ShareGrant(Base):
    """Who may see a share: members chosen by the admin, or accounts that accepted a share link."""
    __tablename__ = "share_grants"
    __table_args__ = (UniqueConstraint("share_id", "user_id", name="uq_grant_share_user"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    share_id: Mapped[str] = mapped_column(ForeignKey("shares.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    via: Mapped[str] = mapped_column(String(8), nullable=False)  # member | link
    link_id: Mapped[str | None] = mapped_column(ForeignKey("share_links.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    share: Mapped[Share] = relationship()


class Return(Base):
    """Results a recipient sent back for a masked twin. Only verified rows are kept (their token and
    the columns the recipient added), encrypted. Re-linking output is a separate short-lived blob;
    no mapping is ever stored."""
    __tablename__ = "returns"
    __table_args__ = (Index("ix_returns_org_created", "org_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    share_id: Mapped[str] = mapped_column(ForeignKey("shares.id", ondelete="CASCADE"), nullable=False, index=True)
    twin_id: Mapped[str] = mapped_column(ForeignKey("twins.id", ondelete="CASCADE"), nullable=False, index=True)
    submitted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    rows_total: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_accepted: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected: Mapped[dict] = mapped_column(JSON, nullable=False)   # reason -> count
    columns: Mapped[list] = mapped_column(JSON, nullable=False)    # added column names only
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # verification report: counts, row numbers, names
    blob_id: Mapped[str | None] = mapped_column(ForeignKey("blobs.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    # re-linking (admin only): none | running | ready | failed | expired
    relink_status: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    relink_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    relink_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    relink_upload_id: Mapped[str | None] = mapped_column(ForeignKey("blobs.id", ondelete="SET NULL"), nullable=True)
    relinked_blob_id: Mapped[str | None] = mapped_column(ForeignKey("blobs.id", ondelete="SET NULL"), nullable=True)
    relink_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    relink_matched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relink_downloads: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    share: Mapped[Share] = relationship()
    twin: Mapped[Twin] = relationship()
