import uuid
from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, MetaData
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

# Custom type for UUIDs with default generation in PG
UUID_PK = Annotated[
    uuid.UUID,
    mapped_column(primary_key=True, server_default=func.gen_random_uuid()),
]

# Custom type for TIMESTAMPTZ
TimestampTZ = Annotated[datetime, mapped_column(DateTime(timezone=True))]


# Naming convention for constraints to ensure Alembic autogenerate works reliably
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(AsyncAttrs, DeclarativeBase):
    metadata = MetaData(naming_convention=convention)


class TimestampMixin:
    """Mixin for created_at and updated_at."""

    created_at: Mapped[TimestampTZ] = mapped_column(server_default=func.now())
    updated_at: Mapped[TimestampTZ] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class SoftDeleteMixin:
    """Mixin for soft-delete support."""

    deleted_at: Mapped[TimestampTZ | None] = mapped_column(default=None)
