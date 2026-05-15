# VibeDate

Telegram dating-бот. Стек: aiogram, PostgreSQL, Redis, MinIO, RabbitMQ, Celery, Docker Compose.

Текст для защиты (технологии, зачем, где в коде): **`docs/DEFENSE.md`**.

## Запуск

```bash
cp .env.example .env
# указать BOT_TOKEN
docker compose up --build
```

| Сервис | Порт на хосте |
|--------|----------------|
| Postgres | 55433 |
| Redis | 6380 |
| MinIO API | 9003 |
| MinIO Console | **9002** |
| RabbitMQ UI | 15673 |
| Метрики Prometheus | 9101 |

Если порт 9002 занят — останови другой MinIO или измени mapping в `docker-compose.yml`.

## Админка

В `.env` добавь свой Telegram ID (через [@userinfobot](https://t.me/userinfobot)):

```env
ADMIN_TG_IDS=ваш_id
```

Команды в боте: `/admin`, `/admin_stats`, `/admin_top`, `/admin_user <tg_id>`, `/admin_recalc`.

## Тесты

```bash
PYTHONPATH=. python3 -m pytest tests/test_rating.py -q
```
