# Subscription, Payments and Booking Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Замкнуть продуктовый сценарий Getawly: месяц триала, оплата 100 ₽ за 30 дней тремя провайдерами, отключение бота при неоплате, уведомления хозяину в Telegram и загрузка фотографий объектов.

**Architecture:** Платёжные провайдеры прячутся за протоколом `PaymentProvider`; все пути успешной оплаты сходятся в одной идемпотентной функции `apply_successful_payment`. Доступ к боту определяется сравнением дат в чистой функции, без фоновых задач. Уведомления хозяину идут через его собственного бота, чат привязывается deep link’ом.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, aiogram 3, Jinja2, httpx, pytest + pytest-asyncio, PostgreSQL 16.

**Spec:** [docs/superpowers/specs/2026-09-23-subscription-and-bookings-design.md](../specs/2026-09-23-subscription-and-bookings-design.md)

## Global Constraints

- Python `>=3.12,<3.13`; все новые зависимости фиксируются с верхней границей, как принято в `pyproject.toml`.
- `ruff` с `line-length = 100`, правила `E`, `F`, `I`, `UP`. Код должен проходить `ruff check .`.
- Тариф: **100 ₽**, период **30 дней**, триал **30 дней**.
- Валюта в коде и в базе — `RUB`.
- Все datetime — timezone-aware, в UTC (`datetime.now(UTC)`). Колонки объявляются как `DateTime(timezone=True)`.
- Пользовательские строки — на русском, как в существующих шаблонах и обработчиках бота.
- Комментарии в коде — на английском, как в существующих файлах.
- Ни один секрет не попадает в репозиторий: новые настройки только через `.env`, в `.env.example` идут пустые значения или плейсхолдеры.

## Review Focus

1. **Оплата во время триала сжигает остаток.** Если считать `paid_until = now + 30 дней`, клиент, заплативший на второй день месячного триала, теряет 28 дней. Тест — Задача 4.
2. **Повторное уведомление ЮKassa продлевает подписку дважды.** ЮKassa повторяет доставку до получения 200; без проверки статуса каждая повторная доставка добавляет 30 дней. Тест — Задача 8.
3. **Подтверждение брони из чужого чата.** `callback_data` содержит последовательный id брони, перебор тривиален; без сверки `chat.id` любой гость подтвердит себе бронь. Тест — Задача 11.
4. **Файл с неразрешённым типом или больше лимита попадает на диск.** Проверка обязана срабатывать до записи файла, иначе диск заполняется мусором даже при «отклонённой» загрузке. Тест — Задача 12.
5. **`/start` с чужим или мусорным кодом привязывает чат.** Неверный код должен молча вести себя как обычный старт гостя, а не сохранять `chat_id` и не падать. Тест — Задача 10.

---

## Фазы

- **Фаза 1 (Задачи 1–9)** — тестовая инфраструктура, подписка, три провайдера, админка, отключение бота. По её завершении монетизация работает целиком.
- **Фаза 2 (Задачи 10–11)** — привязка Telegram хозяина и уведомления о заявках.
- **Фаза 3 (Задачи 12–13)** — загрузка и показ фотографий.

Между фазами можно остановиться: каждая оставляет проект в рабочем состоянии.

---

## Файловая структура

**Создаются:**

| Файл | Ответственность |
|------|-----------------|
| `app/services/payments.py` | Протокол провайдера, три реализации, `apply_successful_payment`, `next_paid_until` |
| `app/services/notify.py` | Отправка уведомлений хозяину и гостю, устойчивая к ошибкам Telegram |
| `app/services/photos.py` | Валидация и сохранение файлов фотографий |
| `app/api/payments.py` | Маршруты оплаты в кабинете и вебхук ЮKassa |
| `app/api/admin.py` | Зависимость `get_current_admin` и страница подтверждения платежей |
| `alembic/versions/002_payments_and_telegram_link.py` | Таблица `payments`, колонки `telegram_chat_id` и `link_code` |
| `templates/cabinet/pay_stub.html` | Имитация платёжной формы для разработки |
| `templates/cabinet/pay_manual.html` | Реквизиты СБП и форма «Я оплатил» |
| `templates/admin/payments.html` | Список неподтверждённых платежей |
| `tests/conftest.py` | Тестовая база, сессия с откатом, HTTP-клиент |
| `tests/*.py` | Тесты по таблице из спеки |

**Изменяются:** `app/config.py`, `app/models/__init__.py`, `app/services/auth.py`, `app/services/bot_runtime.py`, `app/api/cabinet.py`, `app/api/units.py`, `app/api/router.py`, `app/bot/handlers/start.py`, `app/bot/handlers/booking.py`, `app/bot/keyboards.py`, `templates/cabinet/subscription.html`, `templates/cabinet/dashboard.html`, `templates/cabinet/bot.html`, `templates/cabinet/unit_detail.html`, `pyproject.toml`, `.env.example`, `README.md`

---

# ФАЗА 1 — Подписка и оплата

## Задача 1: Тестовая инфраструктура

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/__init__.py`, `tests/conftest.py`, `tests/test_smoke.py`

**Interfaces:**
- Consumes: ничего
- Produces: фикстуры `engine` (session scope), `db_session` (AsyncSession с откатом после теста), `client` (`httpx.AsyncClient` с подменённым `get_db`), `owner_factory` (создаёт владельца с подпиской)

Тесты идут против PostgreSQL, а не SQLite: в моделях используются `Enum` с `values_callable`, `BigInteger` и `Numeric`, и расхождение диалектов здесь стоит дороже, чем удобство. База поднимается той же `docker compose up -d postgres`.

- [ ] **Step 1: Добавить тестовые зависимости**

В `pyproject.toml`, секция `[project.optional-dependencies]`:

```toml
dev = [
    "ruff>=0.8.0,<0.9",
    "pytest>=8.3.0,<9",
    "pytest-asyncio>=0.24.0,<0.25",
]
```

В конец файла:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Установить зависимости**

Run: `uv pip install --system -e ".[dev]"`
Expected: pytest и pytest-asyncio установлены.

- [ ] **Step 3: Создать `tests/__init__.py`**

Пустой файл.

- [ ] **Step 4: Написать `tests/conftest.py`**

```python
import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db import get_db
from app.main import app
from app.models import Base, Owner, Subscription, SubscriptionStatus
from app.services.auth import hash_password

ADMIN_DB_URL = os.getenv(
    "TEST_ADMIN_DATABASE_URL",
    "postgresql+asyncpg://getawly:getawly@localhost:5432/postgres",
)
TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://getawly:getawly@localhost:5432/getawly_test",
)


async def _ensure_database() -> None:
    """CREATE DATABASE cannot run inside a transaction, hence AUTOCOMMIT."""
    admin = create_async_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        exists = await conn.exec_driver_sql(
            "SELECT 1 FROM pg_database WHERE datname = 'getawly_test'"
        )
        if exists.scalar() is None:
            await conn.exec_driver_sql("CREATE DATABASE getawly_test")
    await admin.dispose()


@pytest_asyncio.fixture(scope="session")
async def engine():
    await _ensure_database()
    eng = create_async_engine(TEST_DB_URL)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Each test runs inside a transaction that is rolled back afterwards."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.close()
        await trans.rollback()


@pytest_asyncio.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def owner_factory(db_session):
    async def _make(
        email: str = "owner@example.com",
        *,
        status: SubscriptionStatus = SubscriptionStatus.TRIAL,
        trial_ends_at=None,
        paid_until=None,
    ) -> Owner:
        owner = Owner(
            email=email,
            password_hash=hash_password("secret123"),
            name="Хозяин",
            webhook_secret=f"secret-{email}",
            link_code=f"link-{email}",
        )
        db_session.add(owner)
        await db_session.flush()
        db_session.add(
            Subscription(
                owner_id=owner.id,
                status=status,
                trial_ends_at=trial_ends_at,
                paid_until=paid_until,
            )
        )
        await db_session.flush()
        await db_session.refresh(owner, ["subscription"])
        return owner

    return _make
```

Примечание: `owner_factory` передаёт `link_code`, которого в модели пока нет — колонка появится в Задаче 3. Это не мешает: фикстура ленивая, а smoke-тест её не использует, поэтому Задача 1 проходит. Первым пользователем `owner_factory` станет Задача 3, где колонка уже будет.

- [ ] **Step 5: Написать smoke-тест**

`tests/test_smoke.py`:

```python
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 6: Запустить тесты**

Run: `docker compose up -d postgres` затем `pytest -v`
Expected: PASS. Если падает на подключении — база ещё поднимается, повторить через несколько секунд.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml tests/
git commit -m "test: add pytest infrastructure with a dedicated test database"
```

---

## Задача 2: Настройки тарифа и триала

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: ничего
- Produces: `settings.trial_days = 30`, `settings.subscription_price_rub`, `settings.subscription_period_days`, `settings.payment_provider`, `settings.manual_payment_details`, `settings.admin_emails`, свойство `settings.admin_email_list -> list[str]`

- [ ] **Step 1: Написать падающий тест**

`tests/test_config.py`:

```python
from app.config import Settings


def test_trial_is_one_month():
    assert Settings().trial_days == 30


def test_tariff_defaults():
    settings = Settings()
    assert settings.subscription_price_rub == 100
    assert settings.subscription_period_days == 30
    assert settings.payment_provider == "stub"


def test_admin_emails_are_parsed_and_normalised():
    settings = Settings(admin_emails=" Boss@Example.com , second@example.com ")
    assert settings.admin_email_list == ["boss@example.com", "second@example.com"]


def test_admin_email_list_is_empty_when_unset():
    assert Settings(admin_emails="").admin_email_list == []
```

- [ ] **Step 2: Запустить тест**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `trial_days` равен 14, остальных атрибутов нет.

- [ ] **Step 3: Изменить `app/config.py`**

Заменить `trial_days: int = 14` и добавить новые поля:

```python
    trial_days: int = 30

    subscription_price_rub: int = 100
    subscription_period_days: int = 30

    # stub | manual | yookassa
    payment_provider: str = "stub"
    manual_payment_details: str = ""
    admin_emails: str = ""

    platform_bot_token: str | None = None
    yookassa_shop_id: str | None = None
    yookassa_secret_key: str | None = None

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]
```

- [ ] **Step 4: Запустить тест**

Run: `pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Обновить `.env.example`**

Заменить блок `# Trial` на:

```
# Подписка
TRIAL_DAYS=30
SUBSCRIPTION_PRICE_RUB=100
SUBSCRIPTION_PERIOD_DAYS=30

# Платежи: stub (разработка) | manual (перевод по СБП) | yookassa
PAYMENT_PROVIDER=stub
MANUAL_PAYMENT_DETAILS=
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=

# Кто подтверждает ручные платежи, через запятую
ADMIN_EMAILS=
```

- [ ] **Step 6: Commit**

```bash
git add app/config.py .env.example tests/test_config.py
git commit -m "feat: add tariff settings and extend trial to one month"
```

---

## Задача 3: Модель платежа и миграция

**Files:**
- Modify: `app/models/__init__.py`
- Modify: `tests/conftest.py` (включить `link_code` в `owner_factory`)
- Create: `alembic/versions/002_payments_and_telegram_link.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: ничего
- Produces: `PaymentStatus` (`PENDING`/`SUCCEEDED`/`FAILED`), модель `Payment` (`id`, `owner_id`, `amount`, `currency`, `status`, `provider`, `external_id`, `comment`, `created_at`, `paid_at`, `owner`), поля `Owner.telegram_chat_id` и `Owner.link_code`

- [ ] **Step 1: Написать падающий тест**

`tests/test_models.py`:

```python
from decimal import Decimal

from sqlalchemy import select

from app.models import Payment, PaymentStatus


async def test_payment_defaults_to_pending(db_session, owner_factory):
    owner = await owner_factory()
    payment = Payment(
        owner_id=owner.id,
        amount=Decimal("100.00"),
        provider="manual",
    )
    db_session.add(payment)
    await db_session.flush()

    stored = (
        await db_session.execute(select(Payment).where(Payment.id == payment.id))
    ).scalar_one()
    assert stored.status == PaymentStatus.PENDING
    assert stored.currency == "RUB"
    assert stored.paid_at is None


async def test_owner_has_telegram_link_fields(db_session, owner_factory):
    owner = await owner_factory()
    assert owner.telegram_chat_id is None
    assert owner.link_code == "link-owner@example.com"
```

- [ ] **Step 2: Запустить тест**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — `Payment` не существует.

- [ ] **Step 3: Добавить модель в `app/models/__init__.py`**

После `class BookingStatus(StrEnum)` добавить:

```python
class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
```

В класс `Owner`, после `webhook_secret`:

```python
    telegram_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    link_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, unique=True)
```

В конец файла:

```python
class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="RUB", server_default="RUB")
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", values_callable=lambda x: [e.value for e in x]),
        default=PaymentStatus.PENDING,
        server_default=PaymentStatus.PENDING.value,
    )
    provider: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped["Owner"] = relationship()
```

`external_id` уникален и допускает NULL: в PostgreSQL несколько NULL не конфликтуют, поэтому ручные и тестовые платежи без внешнего идентификатора спокойно сосуществуют, а повторная запись одного платежа ЮKassa отсекается на уровне базы.

- [ ] **Step 4: Включить `link_code` в `owner_factory`**

В `tests/conftest.py` поле `link_code` уже передаётся — убедиться, что строка не закомментирована.

- [ ] **Step 5: Запустить тест**

Run: `pytest tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 6: Создать миграцию**

`alembic/versions/002_payments_and_telegram_link.py`:

```python
"""payments table and telegram link fields

Revision ID: 002
Revises: 001
"""

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("owners", sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True))
    op.add_column("owners", sa.Column("link_code", sa.String(32), nullable=True))
    op.create_unique_constraint("uq_owners_link_code", "owners", ["link_code"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="RUB"),
        sa.Column(
            "status",
            sa.Enum("pending", "succeeded", "failed", name="payment_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("external_id"),
    )
    op.create_index("ix_payments_owner_id", "payments", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_owner_id", table_name="payments")
    op.drop_table("payments")
    sa.Enum(name="payment_status").drop(op.get_bind(), checkfirst=True)
    op.drop_constraint("uq_owners_link_code", "owners", type_="unique")
    op.drop_column("owners", "link_code")
    op.drop_column("owners", "telegram_chat_id")
```

- [ ] **Step 7: Проверить миграцию на чистой базе**

Run: `docker compose down -v; docker compose up -d postgres; alembic upgrade head`
Expected: обе ревизии применяются без ошибок.

Затем проверить откат: `alembic downgrade 001` и снова `alembic upgrade head`.

- [ ] **Step 8: Commit**

```bash
git add app/models/__init__.py alembic/versions/002_payments_and_telegram_link.py tests/
git commit -m "feat: add payment model and telegram link fields"
```

---

## Задача 4: Арифметика продления подписки

**Files:**
- Create: `app/services/payments.py`
- Test: `tests/test_subscription.py`

**Interfaces:**
- Consumes: `Subscription`, `SubscriptionStatus` из `app.models`
- Produces: `next_paid_until(sub: Subscription, now: datetime, days: int) -> datetime`

Это ядро монетизации и самая вероятная точка ошибки, поэтому оно вынесено в чистую функцию без базы и без сети.

- [ ] **Step 1: Написать падающий тест**

`tests/test_subscription.py`:

```python
from datetime import UTC, datetime, timedelta

from app.models import Subscription, SubscriptionStatus
from app.services.auth import subscription_is_usable
from app.services.payments import next_paid_until

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


def test_payment_during_trial_keeps_remaining_days():
    """Paying on day 2 of a 30-day trial must not burn the other 28 days."""
    sub = Subscription(status=SubscriptionStatus.TRIAL, trial_ends_at=NOW + timedelta(days=28))
    assert next_paid_until(sub, NOW, 30) == NOW + timedelta(days=58)


def test_payment_after_trial_expired_starts_from_now():
    sub = Subscription(status=SubscriptionStatus.TRIAL, trial_ends_at=NOW - timedelta(days=3))
    assert next_paid_until(sub, NOW, 30) == NOW + timedelta(days=30)


def test_renewal_stacks_on_top_of_active_period():
    sub = Subscription(status=SubscriptionStatus.ACTIVE, paid_until=NOW + timedelta(days=10))
    assert next_paid_until(sub, NOW, 30) == NOW + timedelta(days=40)


def test_renewal_after_lapse_starts_from_now():
    sub = Subscription(status=SubscriptionStatus.ACTIVE, paid_until=NOW - timedelta(days=5))
    assert next_paid_until(sub, NOW, 30) == NOW + timedelta(days=30)


def test_subscription_lapses_once_paid_until_is_in_the_past():
    past = datetime.now(UTC) - timedelta(seconds=1)
    sub = Subscription(status=SubscriptionStatus.ACTIVE, paid_until=past)
    assert subscription_is_usable(sub) is False
```

- [ ] **Step 2: Запустить тест**

Run: `pytest tests/test_subscription.py -v`
Expected: FAIL — модуль `app.services.payments` не существует.

- [ ] **Step 3: Создать `app/services/payments.py`**

```python
"""Subscription payments: provider abstraction and the single activation path."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.models import Subscription


def next_paid_until(sub: Subscription, now: datetime, days: int) -> datetime:
    """Extend from the latest of now, the paid period and the trial.

    Paying mid-trial must not discard the unused remainder, otherwise the
    cheapest move is always to wait until the service cuts you off.
    """
    base = now
    for candidate in (sub.paid_until, sub.trial_ends_at):
        if candidate is not None and candidate > base:
            base = candidate
    return base + timedelta(days=days)
```

- [ ] **Step 4: Запустить тест**

Run: `pytest tests/test_subscription.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/payments.py tests/test_subscription.py
git commit -m "feat: add subscription extension arithmetic"
```

---

## Задача 5: Идемпотентная активация платежа

**Files:**
- Modify: `app/services/payments.py`
- Test: `tests/test_payments.py`

**Interfaces:**
- Consumes: `next_paid_until`, модели `Payment`, `PaymentStatus`, `Subscription`, `SubscriptionStatus`
- Produces: `async apply_successful_payment(session: AsyncSession, payment: Payment) -> bool` — возвращает `True`, только если этот вызов перевёл платёж в `succeeded`

- [ ] **Step 1: Написать падающий тест**

`tests/test_payments.py`:

```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models import Payment, PaymentStatus, SubscriptionStatus
from app.services.payments import apply_successful_payment


async def _pending(db_session, owner) -> Payment:
    payment = Payment(owner_id=owner.id, amount=Decimal("100.00"), provider="manual")
    db_session.add(payment)
    await db_session.flush()
    return payment


async def test_activation_extends_subscription(db_session, owner_factory):
    owner = await owner_factory(trial_ends_at=datetime.now(UTC) + timedelta(days=10))
    payment = await _pending(db_session, owner)

    activated = await apply_successful_payment(db_session, payment)

    assert activated is True
    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.paid_at is not None
    await db_session.refresh(owner, ["subscription"])
    assert owner.subscription.status == SubscriptionStatus.ACTIVE
    assert owner.subscription.paid_until > datetime.now(UTC) + timedelta(days=39)


async def test_second_activation_is_a_no_op(db_session, owner_factory):
    """YooKassa retries delivery until it sees a 200; retries must not stack days."""
    owner = await owner_factory(trial_ends_at=datetime.now(UTC) + timedelta(days=10))
    payment = await _pending(db_session, owner)

    await apply_successful_payment(db_session, payment)
    await db_session.refresh(owner, ["subscription"])
    first = owner.subscription.paid_until

    activated_again = await apply_successful_payment(db_session, payment)

    assert activated_again is False
    await db_session.refresh(owner, ["subscription"])
    assert owner.subscription.paid_until == first
```

- [ ] **Step 2: Запустить тест**

Run: `pytest tests/test_payments.py -v`
Expected: FAIL — `apply_successful_payment` не существует.

- [ ] **Step 3: Дописать `app/services/payments.py`**

Добавить импорты и функцию:

```python
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Payment, PaymentStatus, Subscription, SubscriptionStatus


async def apply_successful_payment(session: AsyncSession, payment: Payment) -> bool:
    """The single place a payment turns into subscription time.

    Every provider funnels here. Idempotent: returns False when the payment
    was already settled, so repeated webhook deliveries cannot stack days.
    """
    if payment.status == PaymentStatus.SUCCEEDED:
        return False

    now = datetime.now(UTC)
    payment.status = PaymentStatus.SUCCEEDED
    payment.paid_at = now

    sub = (
        await session.execute(
            select(Subscription).where(Subscription.owner_id == payment.owner_id)
        )
    ).scalar_one_or_none()
    if sub is None:
        sub = Subscription(owner_id=payment.owner_id)
        session.add(sub)

    sub.paid_until = next_paid_until(sub, now, settings.subscription_period_days)
    sub.status = SubscriptionStatus.ACTIVE
    await session.commit()
    return True
```

- [ ] **Step 4: Запустить тест**

Run: `pytest tests/test_payments.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/payments.py tests/test_payments.py
git commit -m "feat: add idempotent payment activation"
```

---

## Задача 6: Провайдеры платежей

**Files:**
- Modify: `app/services/payments.py`
- Test: `tests/test_providers.py`

**Interfaces:**
- Consumes: `settings`, модель `Payment`
- Produces: `PaymentProvider` (Protocol с `name: str` и `async create_payment(payment, return_url) -> str`), классы `StubProvider`, `ManualProvider`, `YooKassaProvider`, функция `get_provider() -> PaymentProvider`, `YooKassaProvider.fetch_status(external_id) -> str`

- [ ] **Step 1: Написать падающий тест**

`tests/test_providers.py`:

```python
from decimal import Decimal

import pytest

from app.models import Payment
from app.services.payments import (
    ManualProvider,
    StubProvider,
    YooKassaProvider,
    get_provider,
)


def _payment() -> Payment:
    payment = Payment(id=42, owner_id=1, amount=Decimal("100.00"), provider="stub")
    return payment


async def test_stub_provider_points_at_local_confirmation_page():
    url = await StubProvider().create_payment(_payment(), "http://test/cabinet/subscription")
    assert url == "/cabinet/subscription/stub/42"


async def test_manual_provider_points_at_instructions_page():
    url = await ManualProvider().create_payment(_payment(), "http://test/cabinet/subscription")
    assert url == "/cabinet/subscription/manual/42"


def test_get_provider_resolves_by_settings(monkeypatch):
    import app.services.payments as payments

    monkeypatch.setattr(payments.settings, "payment_provider", "manual")
    assert isinstance(get_provider(), ManualProvider)

    monkeypatch.setattr(payments.settings, "payment_provider", "stub")
    assert isinstance(get_provider(), StubProvider)


def test_get_provider_rejects_unknown_name(monkeypatch):
    import app.services.payments as payments

    monkeypatch.setattr(payments.settings, "payment_provider", "bitcoin")
    with pytest.raises(ValueError, match="bitcoin"):
        get_provider()


def test_yookassa_requires_credentials(monkeypatch):
    import app.services.payments as payments

    monkeypatch.setattr(payments.settings, "yookassa_shop_id", None)
    monkeypatch.setattr(payments.settings, "yookassa_secret_key", None)
    with pytest.raises(ValueError, match="YOOKASSA"):
        YooKassaProvider()
```

- [ ] **Step 2: Запустить тест**

Run: `pytest tests/test_providers.py -v`
Expected: FAIL — провайдеров не существует.

- [ ] **Step 3: Дописать `app/services/payments.py`**

```python
import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

YOOKASSA_API = "https://api.yookassa.ru/v3/payments"


class PaymentProvider(Protocol):
    name: str

    async def create_payment(self, payment: Payment, return_url: str) -> str:
        """Return the URL the owner should be sent to in order to pay."""


class StubProvider:
    """Development only: a local page that pretends to be a payment form."""

    name = "stub"

    async def create_payment(self, payment: Payment, return_url: str) -> str:
        return f"/cabinet/subscription/stub/{payment.id}"


class ManualProvider:
    """Owner transfers by SBP, an admin confirms it by hand."""

    name = "manual"

    async def create_payment(self, payment: Payment, return_url: str) -> str:
        return f"/cabinet/subscription/manual/{payment.id}"


class YooKassaProvider:
    name = "yookassa"

    def __init__(self) -> None:
        if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
            raise ValueError("YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY must be set")
        self._auth = (settings.yookassa_shop_id, settings.yookassa_secret_key)

    async def create_payment(self, payment: Payment, return_url: str) -> str:
        body = {
            "amount": {"value": f"{payment.amount:.2f}", "currency": payment.currency},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": f"Подписка Getawly, платёж #{payment.id}",
            "metadata": {"payment_id": str(payment.id)},
        }
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.post(
                YOOKASSA_API,
                json=body,
                auth=self._auth,
                headers={"Idempotence-Key": f"getawly-payment-{payment.id}"},
            )
            response.raise_for_status()
            data = response.json()
        payment.external_id = data["id"]
        return data["confirmation"]["confirmation_url"]

    async def fetch_status(self, external_id: str) -> str:
        """Ask YooKassa directly. Webhook bodies are unsigned and untrusted."""
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.get(f"{YOOKASSA_API}/{external_id}", auth=self._auth)
            response.raise_for_status()
            return response.json()["status"]


def get_provider() -> PaymentProvider:
    match settings.payment_provider:
        case "stub":
            return StubProvider()
        case "manual":
            return ManualProvider()
        case "yookassa":
            return YooKassaProvider()
        case unknown:
            raise ValueError(f"Unknown PAYMENT_PROVIDER: {unknown}")
```

- [ ] **Step 4: Запустить тест**

Run: `pytest tests/test_providers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/payments.py tests/test_providers.py
git commit -m "feat: add stub, manual and yookassa payment providers"
```

---

## Задача 7: Маршруты оплаты в кабинете

**Files:**
- Create: `app/api/payments.py`, `templates/cabinet/pay_stub.html`, `templates/cabinet/pay_manual.html`
- Modify: `app/api/router.py`, `templates/cabinet/subscription.html`, `templates/cabinet/dashboard.html`, `app/api/cabinet.py`
- Test: `tests/test_payment_routes.py`

**Interfaces:**
- Consumes: `get_provider`, `apply_successful_payment`, `get_current_owner`, `settings`
- Produces: маршруты `POST /cabinet/subscription/pay`, `GET /cabinet/subscription/stub/{payment_id}`, `POST /cabinet/subscription/stub/{payment_id}/confirm`, `GET /cabinet/subscription/manual/{payment_id}`, `POST /cabinet/subscription/manual/{payment_id}/claim`

- [ ] **Step 1: Написать падающий тест**

`tests/test_payment_routes.py`:

```python
from sqlalchemy import select

from app.models import Payment, PaymentStatus, SubscriptionStatus


async def _login(client, owner):
    return await client.post(
        "/login",
        data={"email": owner.email, "password": "secret123"},
        follow_redirects=False,
    )


async def test_pay_creates_pending_payment_and_redirects(client, db_session, owner_factory):
    owner = await owner_factory()
    await _login(client, owner)

    response = await client.post("/cabinet/subscription/pay", follow_redirects=False)

    assert response.status_code == 303
    payment = (
        await db_session.execute(select(Payment).where(Payment.owner_id == owner.id))
    ).scalar_one()
    assert payment.status == PaymentStatus.PENDING
    assert int(payment.amount) == 100
    assert response.headers["location"] == f"/cabinet/subscription/stub/{payment.id}"


async def test_stub_confirmation_activates_subscription(client, db_session, owner_factory):
    owner = await owner_factory()
    await _login(client, owner)
    await client.post("/cabinet/subscription/pay", follow_redirects=False)
    payment = (
        await db_session.execute(select(Payment).where(Payment.owner_id == owner.id))
    ).scalar_one()

    await client.post(
        f"/cabinet/subscription/stub/{payment.id}/confirm", follow_redirects=False
    )

    await db_session.refresh(payment)
    await db_session.refresh(owner, ["subscription"])
    assert payment.status == PaymentStatus.SUCCEEDED
    assert owner.subscription.status == SubscriptionStatus.ACTIVE


async def test_owner_cannot_confirm_someone_elses_payment(client, db_session, owner_factory):
    victim = await owner_factory("victim@example.com")
    attacker = await owner_factory("attacker@example.com")
    payment = Payment(owner_id=victim.id, amount=100, provider="stub")
    db_session.add(payment)
    await db_session.flush()

    await _login(client, attacker)
    response = await client.post(
        f"/cabinet/subscription/stub/{payment.id}/confirm", follow_redirects=False
    )

    await db_session.refresh(payment)
    assert response.status_code == 404
    assert payment.status == PaymentStatus.PENDING


async def test_manual_claim_records_comment_but_does_not_activate(
    client, db_session, owner_factory, monkeypatch
):
    import app.services.payments as payments

    monkeypatch.setattr(payments.settings, "payment_provider", "manual")
    owner = await owner_factory()
    await _login(client, owner)
    await client.post("/cabinet/subscription/pay", follow_redirects=False)
    payment = (
        await db_session.execute(select(Payment).where(Payment.owner_id == owner.id))
    ).scalar_one()

    await client.post(
        f"/cabinet/subscription/manual/{payment.id}/claim",
        data={"comment": "Иван И., ...1234"},
        follow_redirects=False,
    )

    await db_session.refresh(payment)
    await db_session.refresh(owner, ["subscription"])
    assert payment.comment == "Иван И., ...1234"
    assert payment.status == PaymentStatus.PENDING
    assert owner.subscription.status == SubscriptionStatus.TRIAL
```

- [ ] **Step 2: Запустить тест**

Run: `pytest tests/test_payment_routes.py -v`
Expected: FAIL — маршрутов нет.

- [ ] **Step 3: Создать `app/api/payments.py`**

```python
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_owner
from app.config import settings
from app.db import get_db
from app.models import Owner, Payment, PaymentStatus
from app.services.payments import apply_successful_payment, get_provider

router = APIRouter(prefix="/cabinet/subscription", tags=["payments"])
templates = Jinja2Templates(directory="templates")


async def _own_pending_payment(
    session: AsyncSession, owner_id: int, payment_id: int
) -> Payment:
    """404 rather than 403: a foreign payment should not even be acknowledged."""
    payment = (
        await session.execute(
            select(Payment).where(Payment.id == payment_id, Payment.owner_id == owner_id)
        )
    ).scalar_one_or_none()
    if payment is None:
        raise HTTPException(status_code=404)
    return payment


@router.post("/pay")
async def start_payment(
    request: Request,
    session: AsyncSession = Depends(get_db),
    owner: Owner = Depends(get_current_owner),
):
    payment = Payment(
        owner_id=owner.id,
        amount=Decimal(settings.subscription_price_rub),
        provider=settings.payment_provider,
    )
    session.add(payment)
    await session.flush()

    provider = get_provider()
    return_url = f"{settings.base_url.rstrip('/')}/cabinet/subscription"
    url = await provider.create_payment(payment, return_url)
    await session.commit()
    return RedirectResponse(url, status_code=303)


@router.get("/stub/{payment_id}", response_class=HTMLResponse)
async def stub_form(
    payment_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db),
    owner: Owner = Depends(get_current_owner),
):
    payment = await _own_pending_payment(session, owner.id, payment_id)
    return templates.TemplateResponse(
        request, "cabinet/pay_stub.html", {"owner": owner, "payment": payment}
    )


@router.post("/stub/{payment_id}/confirm")
async def stub_confirm(
    payment_id: int,
    session: AsyncSession = Depends(get_db),
    owner: Owner = Depends(get_current_owner),
):
    payment = await _own_pending_payment(session, owner.id, payment_id)
    await apply_successful_payment(session, payment)
    return RedirectResponse("/cabinet/subscription", status_code=303)


@router.get("/manual/{payment_id}", response_class=HTMLResponse)
async def manual_form(
    payment_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db),
    owner: Owner = Depends(get_current_owner),
):
    payment = await _own_pending_payment(session, owner.id, payment_id)
    return templates.TemplateResponse(
        request,
        "cabinet/pay_manual.html",
        {
            "owner": owner,
            "payment": payment,
            "details": settings.manual_payment_details,
            "price": settings.subscription_price_rub,
        },
    )


@router.post("/manual/{payment_id}/claim")
async def manual_claim(
    payment_id: int,
    comment: str = Form(""),
    session: AsyncSession = Depends(get_db),
    owner: Owner = Depends(get_current_owner),
):
    """Records the owner's claim only. Money is confirmed by an admin."""
    payment = await _own_pending_payment(session, owner.id, payment_id)
    if payment.status == PaymentStatus.PENDING:
        payment.comment = comment.strip()[:500]
        await session.commit()
    return RedirectResponse("/cabinet/subscription", status_code=303)
```

- [ ] **Step 4: Создать `templates/cabinet/pay_stub.html`**

```html
{% extends "base.html" %}
{% block title %}Оплата — Getawly{% endblock %}
{% block content %}
<section class="form-card">
  <h1>Тестовая оплата</h1>
  <p class="muted">Это имитация платёжной формы для разработки. Настоящие деньги не списываются.</p>
  <p>Платёж #{{ payment.id }} на сумму {{ payment.amount }} ₽</p>
  <form method="post" action="/cabinet/subscription/stub/{{ payment.id }}/confirm">
    <button type="submit">Подтвердить оплату</button>
  </form>
</section>
{% endblock %}
```

- [ ] **Step 5: Создать `templates/cabinet/pay_manual.html`**

```html
{% extends "base.html" %}
{% block title %}Оплата — Getawly{% endblock %}
{% block content %}
<section class="form-card">
  <h1>Оплата подписки</h1>
  <p>Переведите <strong>{{ price }} ₽</strong> по реквизитам:</p>
  <p><strong>{{ details or 'Реквизиты не настроены, напишите в поддержку.' }}</strong></p>
  <p class="muted">После перевода нажмите кнопку ниже. Подписка продлится, как только мы увидим поступление — обычно в течение дня.</p>
  <form method="post" action="/cabinet/subscription/manual/{{ payment.id }}/claim">
    <label>Имя отправителя и последние 4 цифры
      <input name="comment" placeholder="Иван И., ...1234" required>
    </label>
    <button type="submit">Я оплатил</button>
  </form>
</section>
{% endblock %}
```

- [ ] **Step 6: Подключить роутер**

В `app/api/router.py` добавить импорт `payments` и `api_router.include_router(payments.router)`.

- [ ] **Step 7: Добавить кнопку оплаты**

В `templates/cabinet/subscription.html` заменить последний абзац (`<p class="muted">Оплата через ЮKassa...`) на:

```html
  <form method="post" action="/cabinet/subscription/pay">
    <button type="submit">Оплатить {{ price }} ₽ за {{ period_days }} дней</button>
  </form>
```

В `app/api/cabinet.py`, в `subscription_page`, добавить в контекст:

```python
            "price": settings.subscription_price_rub,
            "period_days": settings.subscription_period_days,
```

В `templates/cabinet/dashboard.html`, сразу после открытия блока content, добавить баннер:

```html
{% if not sub_ok %}
<div class="error">Подписка неактивна — бот не принимает заявки. <a href="/cabinet/subscription">Оплатить</a></div>
{% endif %}
```

- [ ] **Step 8: Запустить тесты**

Run: `pytest tests/test_payment_routes.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/api/payments.py app/api/router.py app/api/cabinet.py templates/
git add tests/test_payment_routes.py
git commit -m "feat: add subscription payment routes for stub and manual providers"
```

---

## Задача 8: Вебхук ЮKassa

**Files:**
- Modify: `app/api/webhooks.py`
- Test: `tests/test_yookassa_webhook.py`

**Interfaces:**
- Consumes: `YooKassaProvider.fetch_status`, `apply_successful_payment`
- Produces: маршрут `POST /webhooks/yookassa`, всегда отвечающий 200

Тело уведомления не подписано и потому недоверенно: из него берётся только идентификатор, статус перезапрашивается у ЮKassa.

- [ ] **Step 1: Написать падающий тест**

`tests/test_yookassa_webhook.py`:

```python
from decimal import Decimal

from app.models import Payment, PaymentStatus, SubscriptionStatus


async def _payment(db_session, owner, external_id: str) -> Payment:
    payment = Payment(
        owner_id=owner.id,
        amount=Decimal("100.00"),
        provider="yookassa",
        external_id=external_id,
    )
    db_session.add(payment)
    await db_session.flush()
    return payment


async def test_webhook_activates_when_api_confirms(
    client, db_session, owner_factory, monkeypatch
):
    import app.api.webhooks as webhooks

    owner = await owner_factory()
    payment = await _payment(db_session, owner, "yk-1")

    async def fake_status(external_id: str) -> str:
        assert external_id == "yk-1"
        return "succeeded"

    monkeypatch.setattr(webhooks, "fetch_yookassa_status", fake_status)

    response = await client.post(
        "/webhooks/yookassa",
        json={"event": "payment.succeeded", "object": {"id": "yk-1", "status": "succeeded"}},
    )

    assert response.status_code == 200
    await db_session.refresh(payment)
    await db_session.refresh(owner, ["subscription"])
    assert payment.status == PaymentStatus.SUCCEEDED
    assert owner.subscription.status == SubscriptionStatus.ACTIVE


async def test_forged_webhook_is_ignored_when_api_disagrees(
    client, db_session, owner_factory, monkeypatch
):
    """The body claims success; YooKassa says otherwise. The body loses."""
    import app.api.webhooks as webhooks

    owner = await owner_factory()
    payment = await _payment(db_session, owner, "yk-2")

    async def fake_status(external_id: str) -> str:
        return "pending"

    monkeypatch.setattr(webhooks, "fetch_yookassa_status", fake_status)

    response = await client.post(
        "/webhooks/yookassa",
        json={"event": "payment.succeeded", "object": {"id": "yk-2", "status": "succeeded"}},
    )

    assert response.status_code == 200
    await db_session.refresh(payment)
    assert payment.status == PaymentStatus.PENDING


async def test_repeated_delivery_does_not_extend_twice(
    client, db_session, owner_factory, monkeypatch
):
    import app.api.webhooks as webhooks

    owner = await owner_factory()
    await _payment(db_session, owner, "yk-3")

    async def fake_status(external_id: str) -> str:
        return "succeeded"

    monkeypatch.setattr(webhooks, "fetch_yookassa_status", fake_status)
    body = {"event": "payment.succeeded", "object": {"id": "yk-3"}}

    await client.post("/webhooks/yookassa", json=body)
    await db_session.refresh(owner, ["subscription"])
    first = owner.subscription.paid_until

    await client.post("/webhooks/yookassa", json=body)
    await db_session.refresh(owner, ["subscription"])

    assert owner.subscription.paid_until == first


async def test_unknown_payment_is_acknowledged(client, monkeypatch):
    """Answer 200 anyway, otherwise YooKassa retries forever."""
    response = await client.post(
        "/webhooks/yookassa", json={"object": {"id": "does-not-exist"}}
    )
    assert response.status_code == 200
```

- [ ] **Step 2: Запустить тест**

Run: `pytest tests/test_yookassa_webhook.py -v`
Expected: FAIL — маршрута нет.

- [ ] **Step 3: Изменить `app/api/webhooks.py`**

```python
import logging

from aiogram.types import Update
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Payment
from app.services.bot_runtime import process_update
from app.services.payments import YooKassaProvider, apply_successful_payment

router = APIRouter(tags=["webhooks"])
logger = logging.getLogger(__name__)


async def fetch_yookassa_status(external_id: str) -> str:
    """Indirection kept module-level so tests can replace it."""
    return await YooKassaProvider().fetch_status(external_id)


@router.post("/tg/{secret}")
async def telegram_webhook(secret: str, request: Request) -> Response:
    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": None})
    await process_update(secret, update)
    return Response(status_code=200)


@router.post("/webhooks/yookassa")
async def yookassa_webhook(
    request: Request, session: AsyncSession = Depends(get_db)
) -> Response:
    """Always answers 200: YooKassa retries anything else until it succeeds.

    The notification body is unsigned, so it is treated as a hint only — the
    authoritative status is fetched back from the API.
    """
    body = await request.json()
    external_id = (body.get("object") or {}).get("id")
    if not external_id:
        return Response(status_code=200)

    payment = (
        await session.execute(select(Payment).where(Payment.external_id == external_id))
    ).scalar_one_or_none()
    if payment is None:
        logger.warning("YooKassa notification for unknown payment %s", external_id)
        return Response(status_code=200)

    try:
        status = await fetch_yookassa_status(external_id)
    except Exception:
        logger.exception("Could not verify YooKassa payment %s", external_id)
        return Response(status_code=200)

    if status == "succeeded":
        await apply_successful_payment(session, payment)
    return Response(status_code=200)
```

- [ ] **Step 4: Запустить тест**

Run: `pytest tests/test_yookassa_webhook.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/webhooks.py tests/test_yookassa_webhook.py
git commit -m "feat: add yookassa webhook with server-side status verification"
```

---

## Задача 9: Админка и отключение бота

**Files:**
- Create: `app/api/admin.py`, `templates/admin/payments.html`
- Modify: `app/api/router.py`, `app/services/bot_runtime.py`
- Test: `tests/test_admin.py`, `tests/test_bot_gate.py`

**Interfaces:**
- Consumes: `settings.admin_email_list`, `apply_successful_payment`, `subscription_is_usable`
- Produces: `get_current_admin`, маршруты `GET /admin/payments` и `POST /admin/payments/{payment_id}/confirm`, функция `owner_bot_is_active(owner: Owner) -> bool` в `bot_runtime`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_bot_gate.py`:

```python
from datetime import UTC, datetime, timedelta

from app.models import SubscriptionStatus
from app.services.bot_runtime import owner_bot_is_active


async def test_active_trial_allows_the_bot(owner_factory):
    owner = await owner_factory(trial_ends_at=datetime.now(UTC) + timedelta(days=5))
    assert owner_bot_is_active(owner) is True


async def test_expired_trial_stops_the_bot(owner_factory):
    owner = await owner_factory(trial_ends_at=datetime.now(UTC) - timedelta(days=1))
    assert owner_bot_is_active(owner) is False


async def test_paid_subscription_allows_the_bot(owner_factory):
    owner = await owner_factory(
        status=SubscriptionStatus.ACTIVE, paid_until=datetime.now(UTC) + timedelta(days=3)
    )
    assert owner_bot_is_active(owner) is True


async def test_deactivated_owner_stops_the_bot_even_when_paid(owner_factory):
    owner = await owner_factory(
        status=SubscriptionStatus.ACTIVE, paid_until=datetime.now(UTC) + timedelta(days=30)
    )
    owner.is_active = False
    assert owner_bot_is_active(owner) is False
```

`tests/test_admin.py`:

```python
from decimal import Decimal

from app.models import Payment, PaymentStatus, SubscriptionStatus


async def _login(client, owner):
    await client.post(
        "/login", data={"email": owner.email, "password": "secret123"}, follow_redirects=False
    )


async def test_admin_confirmation_activates_subscription(
    client, db_session, owner_factory, monkeypatch
):
    import app.api.admin as admin

    monkeypatch.setattr(admin.settings, "admin_emails", "boss@example.com")
    boss = await owner_factory("boss@example.com")
    customer = await owner_factory("customer@example.com")
    payment = Payment(owner_id=customer.id, amount=Decimal("100.00"), provider="manual")
    db_session.add(payment)
    await db_session.flush()

    await _login(client, boss)
    response = await client.post(
        f"/admin/payments/{payment.id}/confirm", follow_redirects=False
    )

    assert response.status_code == 303
    await db_session.refresh(payment)
    await db_session.refresh(customer, ["subscription"])
    assert payment.status == PaymentStatus.SUCCEEDED
    assert customer.subscription.status == SubscriptionStatus.ACTIVE


async def test_non_admin_cannot_open_admin_page(client, owner_factory, monkeypatch):
    import app.api.admin as admin

    monkeypatch.setattr(admin.settings, "admin_emails", "boss@example.com")
    intruder = await owner_factory("intruder@example.com")
    await _login(client, intruder)

    response = await client.get("/admin/payments", follow_redirects=False)

    assert response.status_code == 404


async def test_non_admin_cannot_confirm_payment(client, db_session, owner_factory, monkeypatch):
    import app.api.admin as admin

    monkeypatch.setattr(admin.settings, "admin_emails", "boss@example.com")
    intruder = await owner_factory("intruder@example.com")
    payment = Payment(owner_id=intruder.id, amount=Decimal("100.00"), provider="manual")
    db_session.add(payment)
    await db_session.flush()
    await _login(client, intruder)

    response = await client.post(
        f"/admin/payments/{payment.id}/confirm", follow_redirects=False
    )

    await db_session.refresh(payment)
    assert response.status_code == 404
    assert payment.status == PaymentStatus.PENDING
```

- [ ] **Step 2: Запустить тесты**

Run: `pytest tests/test_admin.py tests/test_bot_gate.py -v`
Expected: FAIL — ни `owner_bot_is_active`, ни админки нет.

- [ ] **Step 3: Добавить гейт в `app/services/bot_runtime.py`**

Импортировать `subscription_is_usable` и добавить функцию:

```python
from app.services.auth import subscription_is_usable


def owner_bot_is_active(owner: Owner) -> bool:
    """A bot answers guests only while the owner is active and paid up."""
    return bool(owner.is_active) and subscription_is_usable(owner.subscription)
```

Заменить проверку в `process_update`:

```python
async def process_update(secret: str, update: Update) -> None:
    async with SessionLocal() as session:
        owner = await get_owner_by_secret(session, secret)
        if owner is None:
            logger.warning("Unknown webhook secret")
            return
        await session.refresh(owner, ["subscription"])
        allowed = owner_bot_is_active(owner)
        entry = await get_or_create_owner_bot(owner)

    if entry is None:
        return
    if not allowed:
        chat_id = _chat_id_from_update(update)
        if chat_id is not None:
            await entry.bot.send_message(
                chat_id, "Бот временно недоступен. Попробуйте позже."
            )
        return
    await entry.dp.feed_update(entry.bot, update)


def _chat_id_from_update(update: Update) -> int | None:
    if update.message is not None:
        return update.message.chat.id
    if update.callback_query is not None and update.callback_query.message is not None:
        return update.callback_query.message.chat.id
    return None
```

Импорт `get_owner_by_secret` должен подгружать подписку — в нём заменить запрос на:

```python
async def get_owner_by_secret(session: AsyncSession, secret: str) -> Owner | None:
    result = await session.execute(
        select(Owner)
        .where(Owner.webhook_secret == secret)
        .options(selectinload(Owner.subscription))
    )
    return result.scalar_one_or_none()
```

Добавить импорт `from sqlalchemy.orm import selectinload` и убрать ставшую лишней строку `await session.refresh(owner, ["subscription"])`.

- [ ] **Step 4: Создать `app/api/admin.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_owner
from app.config import settings
from app.db import get_db
from app.models import Owner, Payment, PaymentStatus
from app.services.payments import apply_successful_payment

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")


async def get_current_admin(owner: Owner = Depends(get_current_owner)) -> Owner:
    """404 rather than 403 — the admin area should not announce itself."""
    if owner.email.lower() not in settings.admin_email_list:
        raise HTTPException(status_code=404)
    return owner


@router.get("/payments", response_class=HTMLResponse)
async def pending_payments(
    request: Request,
    admin: Owner = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    payments = (
        await session.execute(
            select(Payment)
            .where(Payment.status == PaymentStatus.PENDING)
            .options(selectinload(Payment.owner))
            .order_by(Payment.created_at.desc())
        )
    ).scalars().all()
    return templates.TemplateResponse(
        request, "admin/payments.html", {"owner": admin, "payments": payments}
    )


@router.post("/payments/{payment_id}/confirm")
async def confirm_payment(
    payment_id: int,
    admin: Owner = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    payment = (
        await session.execute(select(Payment).where(Payment.id == payment_id))
    ).scalar_one_or_none()
    if payment is None:
        raise HTTPException(status_code=404)
    await apply_successful_payment(session, payment)
    return RedirectResponse("/admin/payments", status_code=303)
```

- [ ] **Step 5: Создать `templates/admin/payments.html`**

```html
{% extends "base.html" %}
{% block title %}Платежи — Getawly{% endblock %}
{% block content %}
<section class="form-card">
  <h1>Неподтверждённые платежи</h1>
  {% if not payments %}
    <p class="muted">Ничего не ждёт подтверждения.</p>
  {% endif %}
  {% for payment in payments %}
    <div class="row">
      <p><strong>{{ payment.amount }} ₽</strong> — {{ payment.owner.email }} ({{ payment.provider }})</p>
      <p class="muted">{{ payment.comment or 'без комментария' }} · {{ payment.created_at.strftime('%d.%m.%Y %H:%M') }}</p>
      <form method="post" action="/admin/payments/{{ payment.id }}/confirm">
        <button type="submit">Подтвердить</button>
      </form>
    </div>
  {% endfor %}
</section>
{% endblock %}
```

- [ ] **Step 6: Подключить роутер**

В `app/api/router.py` добавить импорт `admin` и `api_router.include_router(admin.router)`.

- [ ] **Step 7: Запустить все тесты**

Run: `pytest -v` и `ruff check .`
Expected: всё PASS, замечаний ruff нет.

- [ ] **Step 8: Commit**

```bash
git add app/api/admin.py app/api/router.py app/services/bot_runtime.py templates/admin/
git add tests/test_admin.py tests/test_bot_gate.py
git commit -m "feat: gate bots on active subscription and add manual payment confirmation"
```

**Фаза 1 завершена.** Монетизация работает целиком: триал месяц, оплата, продление, отключение при неоплате.

---

# ФАЗА 2 — Уведомления хозяину

## Задача 10: Привязка Telegram хозяина

**Files:**
- Modify: `app/services/auth.py`, `app/bot/handlers/start.py`, `app/api/cabinet.py`, `templates/cabinet/bot.html`
- Test: `tests/test_telegram_link.py`

**Interfaces:**
- Consumes: `Owner.link_code`, `Owner.telegram_chat_id`
- Produces: генерация `link_code` при регистрации, `async link_owner_chat(session, owner_id, payload, chat_id) -> bool` в `app/services/auth.py`

- [ ] **Step 1: Написать падающий тест**

`tests/test_telegram_link.py`:

```python
from app.services.auth import link_owner_chat, register_owner


async def test_registration_generates_a_link_code(db_session):
    owner = await register_owner(
        db_session, email="new@example.com", password="secret123", name="Новый"
    )
    assert owner.link_code
    assert len(owner.link_code) >= 12


async def test_correct_code_links_the_chat(db_session, owner_factory):
    owner = await owner_factory()

    linked = await link_owner_chat(db_session, owner.id, owner.link_code, 555)

    assert linked is True
    await db_session.refresh(owner)
    assert owner.telegram_chat_id == 555


async def test_wrong_code_links_nothing(db_session, owner_factory):
    owner = await owner_factory()

    linked = await link_owner_chat(db_session, owner.id, "not-the-code", 555)

    assert linked is False
    await db_session.refresh(owner)
    assert owner.telegram_chat_id is None


async def test_empty_payload_links_nothing(db_session, owner_factory):
    owner = await owner_factory()
    assert await link_owner_chat(db_session, owner.id, "", 555) is False
    assert await link_owner_chat(db_session, owner.id, None, 555) is False
```

- [ ] **Step 2: Запустить тест**

Run: `pytest tests/test_telegram_link.py -v`
Expected: FAIL — `link_owner_chat` не существует.

- [ ] **Step 3: Изменить `app/services/auth.py`**

В `register_owner`, в конструктор `Owner`, добавить `link_code=token_urlsafe(12)`.

В конец файла:

```python
async def link_owner_chat(
    session: AsyncSession, owner_id: int, payload: str | None, chat_id: int
) -> bool:
    """Bind the owner's Telegram chat, but only on an exact code match.

    A wrong or missing payload is not an error: it is simply an ordinary
    /start from a guest, and must be treated as such.
    """
    if not payload:
        return False
    owner = await session.get(Owner, owner_id)
    if owner is None or not owner.link_code or owner.link_code != payload:
        return False
    owner.telegram_chat_id = chat_id
    await session.commit()
    return True
```

- [ ] **Step 4: Запустить тест**

Run: `pytest tests/test_telegram_link.py -v`
Expected: PASS.

- [ ] **Step 5: Обработать deep link в боте**

`app/bot/handlers/start.py` — заменить содержимое на:

```python
from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.keyboards import main_menu
from app.bot.states import BookingFSM
from app.db import SessionLocal
from app.services.auth import link_owner_chat

router = Router()


async def _greet_guest(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Привет! Я помогу подобрать жильё и оставить заявку хозяину.\n\n"
        "Нажмите «Найти жильё», чтобы выбрать даты.",
        reply_markup=main_menu(),
    )


@router.message(CommandStart(deep_link=True))
async def cmd_start_deeplink(
    message: Message, command: CommandObject, state: FSMContext, owner_id: int
) -> None:
    async with SessionLocal() as session:
        linked = await link_owner_chat(session, owner_id, command.args, message.chat.id)

    if linked:
        await state.clear()
        await message.answer("Готово! Сюда будут приходить заявки от гостей.")
        return
    await _greet_guest(message, state)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await _greet_guest(message, state)


@router.message(F.text == "Найти жильё")
async def find_housing(message: Message, state: FSMContext) -> None:
    await state.set_state(BookingFSM.check_in)
    await message.answer("Введите дату заезда в формате ДД.ММ.ГГГГ\nНапример: 01.10.2026")
```

Порядок регистрации важен: обработчик с `deep_link=True` должен стоять выше обычного `CommandStart`.

- [ ] **Step 6: Показать ссылку привязки в кабинете**

В `app/api/cabinet.py`, в `bot_settings`, добавить в контекст `"base_url": settings.base_url`.

В `templates/cabinet/bot.html` после формы с токеном добавить:

```html
{% if owner.bot_username and owner.link_code %}
  <p>Чтобы получать заявки в Telegram, откройте
    <a href="https://t.me/{{ owner.bot_username }}?start={{ owner.link_code }}">эту ссылку</a>
    {% if owner.telegram_chat_id %}<span class="ok">— уже привязано</span>{% endif %}
  </p>
{% endif %}
```

- [ ] **Step 7: Запустить все тесты**

Run: `pytest -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/services/auth.py app/bot/handlers/start.py app/api/cabinet.py templates/cabinet/bot.html
git add tests/test_telegram_link.py
git commit -m "feat: link owner telegram chat through a deep link"
```

---

## Задача 11: Уведомления о заявках

**Files:**
- Create: `app/services/notify.py`
- Modify: `app/bot/keyboards.py`, `app/bot/handlers/booking.py`
- Test: `tests/test_notify.py`

**Interfaces:**
- Consumes: `Booking`, `Owner`, `Unit`, `BookingStatus`
- Produces: `booking_decision_kb(booking_id: int) -> InlineKeyboardMarkup` в `app/bot/keyboards.py`; `async notify_owner_new_booking(bot, owner, booking, unit)`, `async notify_guest_decision(bot, booking)` и `async decide_booking(session, owner, chat_id, booking_id, action) -> Booking | None` в `app/services/notify.py`

- [ ] **Step 1: Написать падающий тест**

`tests/test_notify.py`:

```python
from datetime import date
from decimal import Decimal

from app.models import Booking, BookingStatus, Unit
from app.services.notify import decide_booking


async def _booking(db_session, owner) -> Booking:
    unit = Unit(owner_id=owner.id, title="Домик", price_per_night=Decimal("2500"))
    db_session.add(unit)
    await db_session.flush()
    booking = Booking(
        owner_id=owner.id,
        unit_id=unit.id,
        guest_name="Гость",
        guest_phone="+79990000000",
        check_in=date(2026, 10, 1),
        check_out=date(2026, 10, 5),
    )
    db_session.add(booking)
    await db_session.flush()
    return booking


async def test_owner_confirms_from_their_own_chat(db_session, owner_factory):
    owner = await owner_factory()
    owner.telegram_chat_id = 777
    booking = await _booking(db_session, owner)

    result = await decide_booking(db_session, owner, 777, booking.id, "confirm")

    assert result is not None
    assert result.status == BookingStatus.CONFIRMED


async def test_decision_from_a_foreign_chat_is_refused(db_session, owner_factory):
    """Booking ids are sequential, so callback_data is trivially guessable."""
    owner = await owner_factory()
    owner.telegram_chat_id = 777
    booking = await _booking(db_session, owner)

    result = await decide_booking(db_session, owner, 999, booking.id, "confirm")

    assert result is None
    await db_session.refresh(booking)
    assert booking.status == BookingStatus.NEW


async def test_decision_is_refused_when_owner_never_linked_a_chat(db_session, owner_factory):
    owner = await owner_factory()
    booking = await _booking(db_session, owner)

    result = await decide_booking(db_session, owner, 777, booking.id, "confirm")

    assert result is None


async def test_owner_cannot_decide_a_booking_of_another_owner(db_session, owner_factory):
    first = await owner_factory("first@example.com")
    first.telegram_chat_id = 777
    second = await owner_factory("second@example.com")
    booking = await _booking(db_session, second)

    result = await decide_booking(db_session, first, 777, booking.id, "confirm")

    assert result is None
```

- [ ] **Step 2: Запустить тест**

Run: `pytest tests/test_notify.py -v`
Expected: FAIL — `app.services.notify` не существует.

- [ ] **Step 3: Создать `app/services/notify.py`**

```python
"""Telegram notifications. Never allowed to break the booking flow."""

from __future__ import annotations

import logging

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import booking_decision_kb
from app.models import Booking, BookingStatus, Owner, Unit

logger = logging.getLogger(__name__)

_DECISIONS = {"confirm": BookingStatus.CONFIRMED, "decline": BookingStatus.DECLINED}


async def notify_owner_new_booking(
    bot: Bot, owner: Owner, booking: Booking, unit: Unit
) -> None:
    if not owner.telegram_chat_id:
        return
    text = (
        f"<b>Новая заявка #{booking.id}</b>\n"
        f"{unit.title}\n"
        f"{booking.check_in.strftime('%d.%m.%Y')} → {booking.check_out.strftime('%d.%m.%Y')}\n"
        f"Гость: {booking.guest_name}\n"
        f"Телефон: {booking.guest_phone}"
    )
    try:
        await bot.send_message(
            owner.telegram_chat_id, text, reply_markup=booking_decision_kb(booking.id)
        )
    except Exception:
        # A blocked bot or a Telegram outage must not lose the booking.
        logger.exception("Could not notify owner %s about booking %s", owner.id, booking.id)


async def notify_guest_decision(bot: Bot, booking: Booking) -> None:
    if not booking.guest_telegram_id:
        return
    if booking.status == BookingStatus.CONFIRMED:
        text = f"Заявка #{booking.id} подтверждена. Хозяин свяжется с вами."
    else:
        text = f"К сожалению, заявка #{booking.id} отклонена."
    try:
        await bot.send_message(booking.guest_telegram_id, text)
    except Exception:
        logger.exception("Could not notify guest about booking %s", booking.id)


async def decide_booking(
    session: AsyncSession, owner: Owner, chat_id: int, booking_id: int, action: str
) -> Booking | None:
    """Apply an owner's decision, or return None if the caller has no right to it.

    The chat check is the security boundary: booking ids are sequential, so
    anyone could guess a callback payload if the chat were not verified.
    """
    if not owner.telegram_chat_id or owner.telegram_chat_id != chat_id:
        return None
    status = _DECISIONS.get(action)
    if status is None:
        return None

    booking = (
        await session.execute(
            select(Booking).where(Booking.id == booking_id, Booking.owner_id == owner.id)
        )
    ).scalar_one_or_none()
    if booking is None:
        return None

    booking.status = status
    await session.commit()
    return booking
```

- [ ] **Step 4: Запустить тест**

Run: `pytest tests/test_notify.py -v`
Expected: FAIL — `booking_decision_kb` не существует.

- [ ] **Step 5: Добавить клавиатуру**

В `app/bot/keyboards.py` дописать:

```python
def booking_decision_kb(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Подтвердить", callback_data=f"booking:confirm:{booking_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"booking:decline:{booking_id}"),
            ]
        ]
    )
```

Проверить, что `InlineKeyboardMarkup` и `InlineKeyboardButton` уже импортированы; если нет — добавить `from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup`.

- [ ] **Step 6: Запустить тест**

Run: `pytest tests/test_notify.py -v`
Expected: PASS.

- [ ] **Step 7: Отправлять уведомление при создании заявки**

В `app/bot/handlers/booking.py`, в `got_phone`, изменить сигнатуру на `async def got_phone(message: Message, state: FSMContext, owner_id: int, bot: Bot)` и после успешного создания заявки, до ответа гостю, добавить:

```python
    async with SessionLocal() as session:
        owner = await session.get(Owner, owner_id)
        unit = await session.get(Unit, unit_id)
        if owner is not None and unit is not None:
            await notify_owner_new_booking(bot, owner, booking, unit)
```

Добавить импорты: `from aiogram import Bot`, `from app.models import Owner, Unit`, `from app.services.notify import notify_owner_new_booking`.

- [ ] **Step 8: Обработать нажатие кнопок**

В конец `app/bot/handlers/booking.py`:

```python
@router.callback_query(F.data.startswith("booking:"))
async def booking_decision(callback: CallbackQuery, owner_id: int, bot: Bot) -> None:
    _, action, raw_id = callback.data.split(":")
    chat_id = callback.message.chat.id if callback.message else 0

    async with SessionLocal() as session:
        owner = await session.get(Owner, owner_id)
        if owner is None:
            await callback.answer("Недоступно", show_alert=True)
            return
        booking = await decide_booking(session, owner, chat_id, int(raw_id), action)

    if booking is None:
        await callback.answer("Недоступно", show_alert=True)
        return

    await notify_guest_decision(bot, booking)
    await callback.answer("Готово")
    if callback.message:
        await callback.message.answer(
            f"Заявка #{booking.id}: {'подтверждена' if action == 'confirm' else 'отклонена'}."
        )
```

Добавить импорты `decide_booking` и `notify_guest_decision`.

- [ ] **Step 9: Запустить все тесты и линтер**

Run: `pytest -v` и `ruff check .`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add app/services/notify.py app/bot/keyboards.py app/bot/handlers/booking.py tests/test_notify.py
git commit -m "feat: notify owner about new bookings with inline decisions"
```

**Фаза 2 завершена.**

---

# ФАЗА 3 — Фотографии объектов

## Задача 12: Валидация и сохранение фотографий

**Files:**
- Create: `app/services/photos.py`
- Test: `tests/test_photos.py`

**Interfaces:**
- Consumes: ничего
- Produces: константы `ALLOWED_TYPES`, `MAX_BYTES`, `MAX_PHOTOS`; `validate_photo(content_type: str | None, size: int, existing_count: int) -> tuple[str | None, str | None]` (расширение, ошибка); `async save_photo(unit_id: int, data: bytes, extension: str) -> str` — возвращает относительный путь

- [ ] **Step 1: Написать падающий тест**

`tests/test_photos.py`:

```python
from pathlib import Path

import pytest

from app.services.photos import MAX_BYTES, save_photo, validate_photo


def test_jpeg_is_accepted():
    extension, error = validate_photo("image/jpeg", 1024, 0)
    assert extension == ".jpg"
    assert error is None


def test_png_and_webp_are_accepted():
    assert validate_photo("image/png", 1024, 0)[0] == ".png"
    assert validate_photo("image/webp", 1024, 0)[0] == ".webp"


def test_foreign_type_is_rejected():
    extension, error = validate_photo("application/pdf", 1024, 0)
    assert extension is None
    assert "формат" in error.lower()


def test_missing_type_is_rejected():
    extension, error = validate_photo(None, 1024, 0)
    assert extension is None
    assert error


def test_oversized_file_is_rejected():
    extension, error = validate_photo("image/jpeg", MAX_BYTES + 1, 0)
    assert extension is None
    assert "5" in error


def test_photo_limit_per_unit_is_enforced():
    extension, error = validate_photo("image/jpeg", 1024, 10)
    assert extension is None
    assert "10" in error


async def test_saved_file_never_uses_the_client_name(tmp_path, monkeypatch):
    import app.services.photos as photos

    monkeypatch.setattr(photos, "UPLOAD_ROOT", tmp_path)

    relative = await save_photo(7, b"binary-content", ".jpg")

    assert relative.startswith("units/7/")
    assert relative.endswith(".jpg")
    assert "../" not in relative
    written = Path(tmp_path) / relative
    assert written.read_bytes() == b"binary-content"
```

- [ ] **Step 2: Запустить тест**

Run: `pytest tests/test_photos.py -v`
Expected: FAIL — модуля нет.

- [ ] **Step 3: Создать `app/services/photos.py`**

```python
"""Unit photo storage.

File names are always generated. A client-supplied name is never used,
not even sanitised: that is the whole path-traversal class of bug, gone.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_BYTES = 5 * 1024 * 1024
MAX_PHOTOS = 10
UPLOAD_ROOT = Path("uploads")


def validate_photo(
    content_type: str | None, size: int, existing_count: int
) -> tuple[str | None, str | None]:
    """Return (extension, error). Checked before anything touches the disk."""
    if existing_count >= MAX_PHOTOS:
        return None, f"Больше {MAX_PHOTOS} фотографий на объект загрузить нельзя"
    extension = ALLOWED_TYPES.get(content_type or "")
    if extension is None:
        return None, "Неподдерживаемый формат. Нужен JPEG, PNG или WebP"
    if size > MAX_BYTES:
        return None, "Файл больше 5 МБ"
    return extension, None


async def save_photo(unit_id: int, data: bytes, extension: str) -> str:
    relative = f"units/{unit_id}/{uuid4().hex}{extension}"
    destination = UPLOAD_ROOT / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return relative
```

- [ ] **Step 4: Запустить тест**

Run: `pytest tests/test_photos.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/photos.py tests/test_photos.py
git commit -m "feat: add photo validation and storage"
```

---

## Задача 13: Загрузка фотографий и показ в боте

**Files:**
- Modify: `app/api/units.py`, `templates/cabinet/unit_detail.html`, `app/bot/handlers/booking.py`, `README.md`
- Test: `tests/test_photo_routes.py`

**Interfaces:**
- Consumes: `validate_photo`, `save_photo`, `_get_owner_unit`
- Produces: маршруты `POST /cabinet/units/{unit_id}/photos` и `POST /cabinet/units/{unit_id}/photos/{photo_id}/delete`

- [ ] **Step 1: Написать падающий тест**

`tests/test_photo_routes.py`:

```python
from decimal import Decimal

from sqlalchemy import select

from app.models import Unit, UnitPhoto


async def _login(client, owner):
    await client.post(
        "/login", data={"email": owner.email, "password": "secret123"}, follow_redirects=False
    )


async def _unit(db_session, owner) -> Unit:
    unit = Unit(owner_id=owner.id, title="Домик", price_per_night=Decimal("2500"))
    db_session.add(unit)
    await db_session.flush()
    return unit


async def test_upload_stores_photo(client, db_session, owner_factory, tmp_path, monkeypatch):
    import app.services.photos as photos

    monkeypatch.setattr(photos, "UPLOAD_ROOT", tmp_path)
    owner = await owner_factory()
    unit = await _unit(db_session, owner)
    await _login(client, owner)

    response = await client.post(
        f"/cabinet/units/{unit.id}/photos",
        files={"file": ("photo.jpg", b"jpeg-bytes", "image/jpeg")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    photo = (
        await db_session.execute(select(UnitPhoto).where(UnitPhoto.unit_id == unit.id))
    ).scalar_one()
    assert photo.path.startswith(f"units/{unit.id}/")
    assert "photo.jpg" not in photo.path


async def test_foreign_type_is_rejected_and_nothing_is_written(
    client, db_session, owner_factory, tmp_path, monkeypatch
):
    import app.services.photos as photos

    monkeypatch.setattr(photos, "UPLOAD_ROOT", tmp_path)
    owner = await owner_factory()
    unit = await _unit(db_session, owner)
    await _login(client, owner)

    response = await client.post(
        f"/cabinet/units/{unit.id}/photos",
        files={"file": ("payload.pdf", b"%PDF-1.4", "application/pdf")},
        follow_redirects=False,
    )

    assert response.status_code == 400
    rows = (
        await db_session.execute(select(UnitPhoto).where(UnitPhoto.unit_id == unit.id))
    ).scalars().all()
    assert rows == []
    assert list(tmp_path.rglob("*.pdf")) == []


async def test_cannot_upload_to_another_owners_unit(
    client, db_session, owner_factory, tmp_path, monkeypatch
):
    import app.services.photos as photos

    monkeypatch.setattr(photos, "UPLOAD_ROOT", tmp_path)
    victim = await owner_factory("victim@example.com")
    attacker = await owner_factory("attacker@example.com")
    unit = await _unit(db_session, victim)
    await _login(client, attacker)

    response = await client.post(
        f"/cabinet/units/{unit.id}/photos",
        files={"file": ("photo.jpg", b"jpeg-bytes", "image/jpeg")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/cabinet/units"
    rows = (
        await db_session.execute(select(UnitPhoto).where(UnitPhoto.unit_id == unit.id))
    ).scalars().all()
    assert rows == []
```

- [ ] **Step 2: Запустить тест**

Run: `pytest tests/test_photo_routes.py -v`
Expected: FAIL — маршрутов нет.

- [ ] **Step 3: Добавить маршруты в `app/api/units.py`**

Импорты: `from fastapi import File, UploadFile`, `from app.models import UnitPhoto`, `from app.services import photos` и `from app.services.photos import MAX_BYTES, save_photo, validate_photo`.

Корень хранилища берётся как `photos.UPLOAD_ROOT`, а не импортируется именем: `from ... import UPLOAD_ROOT` связывает значение в момент импорта, и подмена пути в тестах перестала бы действовать.

```python
@router.post("/{unit_id}/photos")
async def upload_photo(
    unit_id: int,
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    owner: Owner = Depends(get_current_owner),
):
    unit = await _get_owner_unit(session, owner.id, unit_id)
    if unit is None:
        return RedirectResponse("/cabinet/units", status_code=303)

    data = await file.read(MAX_BYTES + 1)
    extension, error = validate_photo(file.content_type, len(data), len(unit.photos))
    if error is not None:
        return templates.TemplateResponse(
            request,
            "cabinet/unit_detail.html",
            {"owner": owner, "unit": unit, "error": error},
            status_code=400,
        )

    path = await save_photo(unit.id, data, extension)
    session.add(UnitPhoto(unit_id=unit.id, path=path, sort_order=len(unit.photos)))
    await session.commit()
    return RedirectResponse(f"/cabinet/units/{unit.id}", status_code=303)


@router.post("/{unit_id}/photos/{photo_id}/delete")
async def delete_photo(
    unit_id: int,
    photo_id: int,
    session: AsyncSession = Depends(get_db),
    owner: Owner = Depends(get_current_owner),
):
    unit = await _get_owner_unit(session, owner.id, unit_id)
    if unit is None:
        return RedirectResponse("/cabinet/units", status_code=303)
    photo = next((p for p in unit.photos if p.id == photo_id), None)
    if photo is not None:
        (photos.UPLOAD_ROOT / photo.path).unlink(missing_ok=True)
        await session.delete(photo)
        await session.commit()
    return RedirectResponse(f"/cabinet/units/{unit.id}", status_code=303)
```

Файл читается через `file.read(MAX_BYTES + 1)`: лишний байт нужен, чтобы отличить «ровно лимит» от «больше лимита», не загружая в память гигабайт.

В `unit_detail` добавить `"error": None` в контекст, иначе шаблон упадёт на необъявленной переменной.

- [ ] **Step 4: Обновить `templates/cabinet/unit_detail.html`**

Добавить:

```html
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<section>
  <h2>Фотографии</h2>
  <div class="photos">
    {% for photo in unit.photos %}
      <figure>
        <img src="/media/{{ photo.path }}" alt="{{ unit.title }}" style="max-width:200px">
        <form method="post" action="/cabinet/units/{{ unit.id }}/photos/{{ photo.id }}/delete">
          <button type="submit">Удалить</button>
        </form>
      </figure>
    {% endfor %}
  </div>
  <form method="post" action="/cabinet/units/{{ unit.id }}/photos" enctype="multipart/form-data">
    <input type="file" name="file" accept="image/jpeg,image/png,image/webp" required>
    <button type="submit">Загрузить фото</button>
  </form>
</section>
```

- [ ] **Step 5: Показать фото гостю в боте**

В `app/bot/handlers/booking.py`, в `choose_unit`, после `await state.update_data(unit_id=unit_id)` добавить:

```python
    async with SessionLocal() as session:
        unit = (
            await session.execute(
                select(Unit).where(Unit.id == unit_id).options(selectinload(Unit.photos))
            )
        ).scalar_one_or_none()

    if unit is not None and unit.photos:
        try:
            await callback.message.answer_photo(
                FSInputFile(str(photos.UPLOAD_ROOT / unit.photos[0].path)),
                caption=f"<b>{unit.title}</b>\n{unit.description or ''}",
            )
        except Exception:
            logger.exception("Could not send photo for unit %s", unit_id)
```

Добавить импорты: `from aiogram.types import FSInputFile`, `from sqlalchemy import select`, `from sqlalchemy.orm import selectinload`, `from app.services import photos`, `import logging` и `logger = logging.getLogger(__name__)`.

- [ ] **Step 6: Обновить README**

В раздел «Сценарий» добавить пункт про оплату и уведомления:

```markdown
## Сценарий

1. Регистрация → триал 30 дней
2. Кабинет → Бот → token от @BotFather
3. Кабинет → Бот → привязать Telegram, чтобы получать заявки
4. Объекты → добавить жильё и фотографии
5. Гость: `/start` → даты → заявка
6. Хозяину приходит заявка с кнопками «Подтвердить» / «Отклонить»
7. По окончании триала — 100 ₽ за 30 дней

## Тесты

```powershell
docker compose up -d postgres
pytest -v
```
```

- [ ] **Step 7: Запустить всё**

Run: `pytest -v` и `ruff check .`
Expected: все тесты проходят, замечаний нет.

- [ ] **Step 8: Commit**

```bash
git add app/api/units.py app/bot/handlers/booking.py templates/cabinet/unit_detail.html README.md
git add tests/test_photo_routes.py
git commit -m "feat: add unit photo upload, deletion and display in the bot"
```

**Фаза 3 завершена.**

---

## Финальная проверка

- [ ] `pytest -v` — все тесты проходят
- [ ] `ruff check .` — замечаний нет
- [ ] `docker compose down -v; docker compose up --build` — приложение поднимается с нуля, миграции накатываются
- [ ] Ручной проход: регистрация → подключение бота → привязка Telegram → объект с фото → заявка от гостя → уведомление хозяину → подтверждение → оплата через stub → подписка активна
