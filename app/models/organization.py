from sqlalchemy import CheckConstraint, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Organization(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="UTC")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    fiscal_year_start_month: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")

    __table_args__ = (
        CheckConstraint("char_length(btrim(name)) >= 1", name="name_not_blank"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso"),
        CheckConstraint("fiscal_year_start_month BETWEEN 1 AND 12", name="fiscal_month_range"),
    )