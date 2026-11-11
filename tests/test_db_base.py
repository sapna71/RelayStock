import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, MetaData, String, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.base import NAMING_CONVENTION, Base, TimestampMixin, UUIDPKMixin


def test_app_base_uses_naming_convention():
    assert Base.metadata.naming_convention == NAMING_CONVENTION


async def test_mixins_and_constraint_names_in_postgres(engine):
    class TBase(DeclarativeBase):
        metadata = MetaData(naming_convention=NAMING_CONVENTION)

    class Item(UUIDPKMixin, TimestampMixin, TBase):
        __tablename__ = "tmp_item"
        name: Mapped[str] = mapped_column(String(50), nullable=False)
        __table_args__ = (CheckConstraint("length(name) > 0", name="name_nonempty"),)

    async with engine.connect() as conn:
        trans = await conn.begin()  # DDL is transactional in PostgreSQL: nothing persists
        await conn.run_sync(TBase.metadata.create_all)
        async with AsyncSession(bind=conn, expire_on_commit=False) as s:
            item = Item(name="widget")
            s.add(item)
            await s.flush()
            assert isinstance(item.id, uuid.UUID)
            assert isinstance(item.created_at, datetime) and item.created_at.tzinfo is not None
        names = {r[0] for r in await conn.execute(text(
    "SELECT conname FROM pg_constraint "
    "WHERE conrelid = 'tmp_item'::regclass AND contype IN ('p', 'c')"))}
        assert names == {"pk_tmp_item", "ck_tmp_item_name_nonempty"}
        await trans.rollback()