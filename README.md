# Getawly

Кабинет хозяина + свой Telegram-бот для заявок на жильё. Монетизация — подписка хозяина (триал 14 дней).

## Стек

| Слой | Выбор |
|------|--------|
| Python | **3.12** |
| API | FastAPI + Uvicorn |
| БД | PostgreSQL 16 + SQLAlchemy 2 + Alembic |
| Бот | aiogram 3 (webhook `/tg/{secret}`) |
| Кабинет | Jinja2 + HTMX |
| Деплой | Docker Compose |

## Быстрый старт

```powershell
cd D:\testProjects\getawly
docker compose down -v
docker compose up --build
```

Кабинет: http://localhost:8088/

### Публичный BASE_URL

```powershell
winget install --id Cloudflare.cloudflared
.\scripts\start-tunnel.ps1
```

Скопируй `https://….trycloudflare.com` в `.env` → `BASE_URL=...` → `docker compose up -d api`.

## Сценарий

1. Регистрация → триал 30 дней
2. Кабинет → Бот → token от @BotFather
3. Кабинет → Бот → «Привязать Telegram», чтобы получать заявки
4. Объекты → добавить жильё и фотографии
5. Гость: `/start` → даты → заявка
6. Хозяину приходит карточка заявки с кнопками «Подтвердить» / «Отклонить»
7. По окончании триала — 100 ₽ за 30 дней, иначе бот перестаёт принимать заявки

## Оплата

Провайдер выбирается переменной `PAYMENT_PROVIDER`:

| Значение | Когда |
|----------|-------|
| `stub` | Разработка. Локальная страница с кнопкой «Подтвердить оплату», денег нет. |
| `manual` | Старт. Владелец переводит по СБП (`MANUAL_PAYMENT_DETAILS`) и жмёт «Я оплатил»; платёж ждёт подтверждения. |
| `yookassa` | Боевой. Нужны `YOOKASSA_SHOP_ID` и `YOOKASSA_SECRET_KEY`. |

Ручные платежи подтверждаются на `/admin/payments`. Доступ туда — по списку
`ADMIN_EMAILS` (через запятую); для всех остальных страница отвечает 404.

## Тесты

```powershell
docker compose up -d postgres
.\.venv\Scripts\python.exe -m pytest -v
```

Тесты идут против отдельной базы `getawly_test` на том же сервере. Postgres
опубликован на порту **55432**, а не 5432: на машинах с локально установленным
PostgreSQL порты 5432-5434 обычно заняты, и подключение молча уходит не туда.
Переопределяется переменной `TEST_DATABASE_URL`.

Папку можно позже переименовать в `getawly`.
