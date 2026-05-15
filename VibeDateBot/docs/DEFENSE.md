# Текст для защиты: технологии, зачем нужны и где в коде (VibeDate)

## PostgreSQL

**Технология:** PostgreSQL.

**Зачем:** основная реляционная база данных. Хранит пользователей Telegram, анкеты, настройки поиска, метаданные фото, лайки/скипы, мэтчи и рейтинги. Без PostgreSQL бот не сохраняет состояние пользователей и не может показывать ленту.

**Где в коде:**

- `docker-compose.yml` — сервис `db` (образ `postgres:16`, порт хоста **55432**);
- `docs/vibedatebd.sql` — схема таблиц `users`, `profiles`, `photos`, `likes`, `matches`, `ratings`;
- `app/db.py` — пул `asyncpg`, регистрация (`ensure_user_and_profile`), CRUD анкеты, лента (`get_next_candidate`, `get_next_candidate_ids`, `get_candidate_for_viewer`), реакции (`react_to_candidate`), фото;
- `app/db.py` — `ensure_runtime_schema` — лёгкие миграции и индексы при старте;
- `app/handlers/common.py` — `/start`, создание пользователя и пустой анкеты;
- `app/handlers/dating.py` — заполнение анкеты, лента, лайк/скип, мэтч.

---

## Redis

**Технология:** Redis.

**Зачем:** (1) кэш предварительно отранжированной ленты — до 10 `profile_id` на пользователя, чтобы не выполнять тяжёлый SQL на каждый свайп; (2) брокер и backend для Celery.

**Где в коде:**

- `docker-compose.yml` — сервис `redis`;
- `.env.example` — `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`;
- `app/main.py` — подключение `Redis.from_url`, передача `redis` в хендлеры;
- `app/services/feed_cache.py` — ключ `vibedate:feed:{tg_id}`, `LPOP`/`RPUSH`, дозаполнение очереди (`ensure_feed_queue_depth`, `pop_next_feed_candidate`);
- `app/handlers/dating.py` — `_show_feed`: при наличии Redis — `pop_next_feed_candidate`, иначе fallback `get_next_candidate`;
- `app/celery_app.py` — broker/backend Celery через Redis.

---

## Celery

**Технология:** Celery + Celery Beat.

**Зачем:** фоновый периодический пересчёт рейтингов всех анкет (раз в 10 минут). Рейтинг также обновляется сразу при лайке/скипе и правке профиля, но Celery даёт полный проход по таблице `ratings` без нагрузки на бота в момент действия пользователя.

**Где в коде:**

- `docker-compose.yml` — сервисы `celery-worker` и `celery-beat`;
- `app/celery_app.py` — приложение Celery, расписание `recalculate-all-ratings` (600 с);
- `app/tasks.py` — задача `recalculate_all_ratings` (обход `profiles`, вызов `refresh_profile_rating`);
- `app/services/profile.py` — `refresh_profile_rating` — запись в `profiles` и `ratings`.

---

## RabbitMQ

**Технология:** RabbitMQ.

**Зачем:** брокер сообщений для событий взаимодействия с анкетами. После лайка/скипа бот публикует JSON в очередь; отдельный consumer может читать поток (демонстрация асинхронной обработки из ТЗ).

**Где в коде:**

- `docker-compose.yml` — сервис `rabbitmq` (AMQP **5672**, UI **15672**);
- `.env.example` — `RABBITMQ_URL`;
- `app/events_rabbitmq.py` — очередь `vibedate.profile_events`, `publish_profile_interaction`;
- `app/handlers/dating.py` — после успешной реакции `asyncio.to_thread(publish_profile_interaction, ...)`;
- `app/event_consumer.py` — пример потребителя: `python -m app.event_consumer`;
- `app/main.py` — `shutdown_publisher` при остановке бота.

---

## MinIO / S3

**Технология:** MinIO как S3-совместимое хранилище.

**Зачем:** по архитектуре проекта — хранение файлов фото вне PostgreSQL (в БД только `s3_key` и метаданные). Сейчас в compose MinIO поднят, настройки в конфиге есть; загрузка фото в боте сохраняет ключ вида `tg:{file_id}` (Telegram), полноценная выгрузка в MinIO — следующий шаг интеграции.

**Где в коде:**

- `docker-compose.yml` — сервис `minio` (API **9000**, консоль **9001**);
- `.env.example` — `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`;
- `app/config.py` — поля MinIO в `Settings`;
- `docs/vibedatebd.sql` — таблица `photos`, поле `s3_key`;
- `app/db.py` — `add_profile_photo_by_tg_id`, `get_profile_photos_by_tg_id`;
- `app/handlers/dating.py` — команда/кнопка «Добавить фото», показ фото по `file_id`.

---

## Система рейтинга

**Технология:** многоуровневый рейтинг анкет (первичный + поведенческий + комбинированный).

**Зачем:** лента сортируется не случайно, а по качеству анкеты и реакциям других пользователей. Учитываются заполненность профиля, фото, лайки/скипы, мэтчи, диалоги; в формуле комбинированного рейтинга заложен `referral_bonus`.

**Где в коде:**

- `docs/vibedatebd.sql` — таблица `ratings`, поля `primary_rating`, `combined_rating`, счётчики лайков/скипов/мэтчей;
- `app/services/rating.py` — `calc_primary_rating`, `calc_behavior_rating`, `calc_combined_rating`;
- `app/services/profile.py` — `refresh_profile_rating` после изменений;
- `app/db.py` — обновление счётчиков в `react_to_candidate`, сортировка ленты по `combined_rating`;
- `app/handlers/dating.py` — пересчёт после реакции и редактирования анкеты;
- `app/tasks.py` + `app/celery_app.py` — периодический полный пересчёт;
- `tests/test_rating.py` — unit-тесты формул.

**Уровни по ТЗ:**


| Уровень             | Реализация                                                                          |
| ------------------- | ----------------------------------------------------------------------------------- |
| 1 — первичный       | возраст, город, интересы, предпочтения, фото, заполненность (`calc_primary_rating`) |
| 2 — поведенческий   | лайки/скипы, мэтчи, диалоги (`calc_behavior_rating`, счётчики в `ratings`)          |
| 3 — комбинированный | веса 60% / 40% + `referral_bonus` (`calc_combined_rating`)                          |


---

## Prometheus (метрики)

**Технология:** prometheus-client.

**Зачем:** счётчики для демонстрации наблюдаемости: сколько раз показали ленту и сколько лайков/скипов обработали.

**Где в коде:**

- `.env.example` — `METRICS_PORT=9100`;
- `docker-compose.yml` — проброс порта **9100** у сервиса `app`;
- `app/metrics.py` — `vibedate_feed_views_total`, `vibedate_reactions_total`, HTTP-сервер метрик;
- `app/main.py` — `start_metrics_http_server_if_configured`;
- `app/handlers/dating.py` — `inc_feed_view()`, `inc_reaction(is_like=...)`.

Проверка: `http://localhost:9100/metrics` при запущенном compose.

---

## Structlog / JSON-логирование

**Технология:** structlog.

**Зачем:** структурированные JSON-логи с уровнем и временем — удобнее искать события в Docker-логах, чем обычный текст.

**Где в коде:**

- `app/main.py` — `structlog.configure`, события `redis_ok`, `bot_started`, `bot_stopped`;
- `app/handlers/dating.py` — `feed_shown`, `reaction_saved`, `reaction_failed`.

---

## Telegram Bot API / aiogram

**Технология:** aiogram 3 + Telegram Bot API.

**Зачем:** основной интерфейс для пользователя: регистрация, анкета, фото, лента, лайки, скипы, мэтчи с контактами.

**Где в коде:**

- `app/main.py` — `Bot`, `Dispatcher`, `start_polling`;
- `app/handlers/common.py` — `/start`, главное меню;
- `app/handlers/dating.py` — FSM заполнения анкеты, редактирование, лента, callback-кнопки like/skip;
- `app/keyboards/main.py` — reply- и inline-клавиатуры;
- `app/config.py` — `BOT_TOKEN`, `load_settings`;
- `Dockerfile` — образ Python 3.11, запуск `python -m app.main`.

---

## Docker Compose

**Технология:** Docker Compose.

**Зачем:** поднять весь стек одной командой для зачёта и локальной разработки: БД, кэш, очереди, бот, фоновые воркеры.

**Где в коде:**

- `docker-compose.yml` — сервисы `db`, `redis`, `minio`, `rabbitmq`, `app`, `celery-worker`, `celery-beat`;
- `Dockerfile` — сборка образа приложения;
- `.env` / `.env.example` — переменные окружения;
- `README.md` — инструкция `docker compose up --build`.

---

## Тестирование (pytest)

**Технология:** pytest.

**Зачем:** автоматическая проверка формул рейтинга (этап 4 — тестирование продукта).

**Где в коде:**

- `tests/test_rating.py` — тесты `calc_primary_rating`, `calc_behavior_rating`, `calc_combined_rating`;
- `pytest.ini` — `pythonpath = .`;
- `requirements.txt` — зависимость `pytest`.

Запуск: `PYTHONPATH=. python3 -m pytest tests/test_rating.py -q` (удобнее внутри Docker с Python 3.11).

---

## Оптимизация БД

**Технология:** индексы PostgreSQL.

**Зачем:** ускорить выборку ленты и проверку уже просмотренных анкет (лайки по `from_profile` / `to_profile`, сортировка по `updated_at`, фильтр по городу).

**Где в коде:**

- `docs/vibedatebd.sql` — `idx_likes_from_profile`, `idx_likes_to_profile`, `idx_profiles_updated_at`, `idx_profiles_city`, `idx_photos_profile`;
- `app/db.py` — создание тех же индексов в `ensure_runtime_schema`.

---

## Реферальная система 

**Технология:** реферальные поля и бонус в рейтинге.

**Зачем:** по ТЗ — дополнительный фактор комбинированного рейтинга за приглашение друзей.

**Где в коде:**

- `docs/vibedatebd.sql` — в `users`: `referral_code`, `referred_by`;
- `app/services/rating.py` — параметр `referral_bonus` в `calc_combined_rating`;
- `tests/test_rating.py` — тест с `referral_bonus`.



---

## Краткая схема потока данных (для устного ответа)

1. Пользователь жмёт **«Лента анкет»** → бот берёт `profile_id` из Redis-очереди (или из SQL, если Redis недоступен).
2. Карточка подгружается из PostgreSQL с проверкой фильтров и рейтинга.
3. **Лайк/скип** → запись в `likes`, обновление `ratings`, пересчёт рейтинга, событие в RabbitMQ, метрика Prometheus.
4. При взаимном лайке → запись в `matches`, отправка контактов обоим в Telegram.
5. Раз в 10 минут Celery пересчитывает рейтинги всех анкет.

---

