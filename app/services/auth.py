from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Owner, Subscription, SubscriptionStatus

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


async def register_owner(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    name: str,
    phone: str | None = None,
) -> Owner:
    owner = Owner(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        name=name.strip(),
        phone=phone,
        webhook_secret=token_urlsafe(24),
    )
    session.add(owner)
    await session.flush()

    trial_ends = datetime.now(UTC) + timedelta(days=settings.trial_days)
    session.add(
        Subscription(
            owner_id=owner.id,
            status=SubscriptionStatus.TRIAL,
            trial_ends_at=trial_ends,
        )
    )
    await session.commit()
    await session.refresh(owner)
    return owner


async def authenticate_owner(session: AsyncSession, email: str, password: str) -> Owner | None:
    result = await session.execute(select(Owner).where(Owner.email == email.lower().strip()))
    owner = result.scalar_one_or_none()
    if owner is None or not verify_password(password, owner.password_hash):
        return None
    return owner


def subscription_is_usable(sub: Subscription | None) -> bool:
    if sub is None:
        return False
    now = datetime.now(UTC)
    if sub.status == SubscriptionStatus.TRIAL and sub.trial_ends_at and sub.trial_ends_at > now:
        return True
    if sub.status == SubscriptionStatus.ACTIVE and sub.paid_until and sub.paid_until > now:
        return True
    return False
