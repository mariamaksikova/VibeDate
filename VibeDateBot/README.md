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
| Postgres | 55432 |
| Redis | 6379 |
| MinIO API | 9000 |
| MinIO Console | **9002** |
| RabbitMQ UI | 15672 |
| Метрики Prometheus | 9100 |

Если порт 9002 занят — останови другой MinIO или измени mapping в `docker-compose.yml`.

## Тесты

```bash
PYTHONPATH=. python3 -m pytest tests/test_rating.py -q
```
