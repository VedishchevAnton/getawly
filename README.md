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

1. Регистрация → триал 14 дней  
2. Кабинет → Бот → token от @BotFather  
3. Объекты → добавить жильё  
4. Гость: `/start` → даты → заявка  

Папку можно позже переименовать в `getawly`.
