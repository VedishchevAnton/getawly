from datetime import date, datetime
from enum import StrEnum
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SubscriptionStatus(StrEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class BookingStatus(StrEnum):
    NEW = "new"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    CANCELLED = "cancelled"


class Owner(Base):
    __tablename__ = "owners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    bot_token: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True)
    bot_username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscription: Mapped[Optional["Subscription"]] = relationship(
        back_populates="owner", uselist=False, cascade="all, delete-orphan"
    )
    units: Mapped[list["Unit"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="owner")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), unique=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status", values_callable=lambda x: [e.value for e in x]),
        default=SubscriptionStatus.TRIAL,
    )
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped["Owner"] = relationship(back_populates="subscription")


class Unit(Base):
    """One rentable unit (room / apartment) belonging to a single owner."""

    __tablename__ = "units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    price_per_night: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    capacity: Mapped[int] = mapped_column(Integer, default=2)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped["Owner"] = relationship(back_populates="units")
    photos: Mapped[list["UnitPhoto"]] = relationship(
        back_populates="unit", cascade="all, delete-orphan", order_by="UnitPhoto.sort_order"
    )
    blocked_dates: Mapped[list["BlockedDate"]] = relationship(
        back_populates="unit", cascade="all, delete-orphan"
    )
    bookings: Mapped[list["Booking"]] = relationship(back_populates="unit")


class UnitPhoto(Base):
    __tablename__ = "unit_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(512))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    unit: Mapped["Unit"] = relationship(back_populates="photos")


class BlockedDate(Base):
    """Owner-marked occupancy (manual calendar). Bookings also occupy ranges."""

    __tablename__ = "blocked_dates"
    __table_args__ = (UniqueConstraint("unit_id", "day", name="uq_unit_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date)
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    unit: Mapped["Unit"] = relationship(back_populates="blocked_dates")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), index=True)
    guest_name: Mapped[str] = mapped_column(String(120))
    guest_phone: Mapped[str] = mapped_column(String(32))
    guest_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    check_in: Mapped[date] = mapped_column(Date)
    check_out: Mapped[date] = mapped_column(Date)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status", values_callable=lambda x: [e.value for e in x]),
        default=BookingStatus.NEW,
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped["Owner"] = relationship(back_populates="bookings")
    unit: Mapped["Unit"] = relationship(back_populates="bookings")
