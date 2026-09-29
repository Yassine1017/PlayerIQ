"""Shared private-schema metadata and the external Supabase Auth reference."""

from sqlalchemy import Column, MetaData, Table, Uuid
from sqlalchemy.orm import DeclarativeBase

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(schema="playeriq", naming_convention=NAMING)


# Supabase owns this table. It is present only so SQLAlchemy can resolve FKs;
# the PlayerIQ migration never creates or alters auth.users.
auth_users = Table(
    "users",
    Base.metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    schema="auth",
    info={"external": True},
)
