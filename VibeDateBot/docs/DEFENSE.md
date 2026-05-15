# Текст для защиты: технологии, зачем нужны и где в коде

## PostgreSQL

Технология: PostgreSQL.

Зачем: основная реляционная база данных. Хранит пользователей Telegram, анкеты, настройки поиска, метаданные фотографий, лайки, скипы, мэтчи и рейтинги. Без PostgreSQL бот не сохраняет состояние пользователей и не может показывать ленту.

Где в коде:

- `docker-compose.yml` — сервис `db` (порт хоста **55432**);
- `docs/vibedatebd.sql` — схема: `users`, `profiles`, `photos`, `likes`, `matches`, `ratings`;
- `app/db.py` — пул `asyncpg`, регистрация, рефералы, лента, реакции, фото, индексы (`ensure_runtime_schema`);
- `app/handlers/common.py` — `/start`, `/invite`;
- `app/handlers/dating.py` — анкета, лента, лайк/скип, мэтч.

---

## Redis

Технология: Redis.

Зачем: используется не только для Celery. Redis кэширует предварительно отранжированные анкеты (до 10 штук на пользователя), чтобы не выполнять тяжёлый SQL-запрос на каждый свайп. Отдельно Redis хранит счётчики rate-limit (защита от спама кнопками). Также Redis — broker и backend для Celery.

Где в коде:

- `docker-compose.yml` — сервис `redis`;
- `app/services/feed_cache.py` — очередь `vibedate:feed:{tg_id}`, `LPOP`/`RPUSH`, дозаполнение до 10 id;
- `app/middleware/rate_limit.py` — `INCR` и `EXPIRE`, лимит 30 действий в минуту;
- `app/main.py` — подключение Redis, middleware;
- `app/handlers/dating.py` — лента через `pop_next_feed_candidate`;
- `app/celery_app.py` — `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`.

---

## Celery

Технология: Celery + Celery Beat.

Зачем: фоновые задачи. Рейтинги пересчитываются периодически (раз в 10 минут) для всех анкет в таблице `ratings`, а не только в момент лайка. Отдельная задача `notify_match` отправляет уведомление о мэтче в Telegram, чтобы не блокировать основной поток бота.

Где в коде:

- `docker-compose.yml` — сервисы `celery-worker` и `celery-beat`;
- `app/celery_app.py` — настройка Celery и расписание `recalculate-all-ratings`;
- `app/tasks.py` — задачи `recalculate_all_ratings`, `notify_match`;
- `app/services/profile.py` — `refresh_profile_rating`, вызывается из задач;
- `app/handlers/dating.py` — при мэтче `notify_match.delay(...)`.

---

## RabbitMQ

Технология: RabbitMQ.

Зачем: брокер сообщений для потоковой обработки событий взаимодействия с анкетами. Бот публикует события `reaction` и `match` в очередь; отдельный consumer читает поток и логирует обработку (демонстрация связки бот → MQ → фоновые сервисы).

Где в коде:

- `docker-compose.yml` — сервис `rabbitmq` (AMQP **5672**, UI **15672**);
- `app/events_rabbitmq.py` — очередь `vibedate.profile_events`, метод `publish_profile_interaction`;
- `app/handlers/dating.py` — публикация после лайка/скипа и при мэтче;
- `app/event_consumer.py` — запуск: `python -m app.event_consumer`;
- `.env.example` — `RABBITMQ_URL`.

---

## MinIO / S3

Технология: MinIO как S3-совместимое хранилище.

Зачем: хранение пользовательских фото. Файлы не кладутся в PostgreSQL, чтобы не раздувать БД. В PostgreSQL хранится только `s3_key` и порядок фото, а байты — в bucket `vibedate-photos`.

Где в коде:

- `docker-compose.yml` — сервисы `minio`, `minio-init` (API **9000**, консоль **9002** на хосте);
- `app/services/storage.py` — загрузка, скачивание, создание bucket;
- `app/config.py` — `MINIO_ENDPOINT`, ключи, имя bucket;
- `app/handlers/dating.py` — `/add_photo`: файл из Telegram → MinIO; `/my_profile`: показ фото из MinIO;
- `app/db.py` — таблица `photos`, поле `s3_key`;
- `docs/vibedatebd.sql` — модель `photos`.

---

## Система рейтинга

Технология: многоуровневый рейтинг анкет (3 уровня по ТЗ).

Зачем: анкеты в ленте показываются не случайно, а по итоговому `combined_rating`. Учитываются заполненность профиля, предпочтения, реакции других пользователей и рефералы.

Где в коде:

- `docs/vibedatebd.sql` — таблица `ratings`;
- `app/services/rating.py` — `calc_primary_rating`, `calc_behavior_rating`, `calc_combined_rating`, `calc_referral_bonus`;
- `app/services/profile.py` — пересчёт и запись в `profiles` + `ratings`;
- `app/db.py` — счётчики лайков/скипов/мэтчей, `get_activity_peak_share` (активность по часам суток);
- `app/db.py` — сортировка ленты по `combined_rating`;
- `app/tasks.py` — периодический полный пересчёт;
- `tests/test_rating.py` — unit-тесты формул.

Уровень 1 (первичный): возраст, пол, город, интересы, предпочтения (`looking_for`, `min_age`, `max_age`), число фото, заполненность анкеты.

Уровень 2 (поведенческий): лайки и скипы, соотношение лайков, число мэтчей, диалоги, пик активности по часам (из `likes.created_at`).

Уровень 3 (комбинированный): `primary * 0.6 + behavior * 0.4 + referral_bonus`.

---

## Реферальная система

Технология: referral links.

Зачем: дополнительный фактор комбинированного рейтинга — пользователь приглашает друга по ссылке, за каждого приглашённого начисляется бонус к рейтингу.

Где в коде:

- `docs/vibedatebd.sql` — поля `referral_code`, `referred_by` в `users`;
- `app/db.py` — генерация кода, привязка по `?start=ref_КОД`, `count_referrals_for_user`;
- `app/handlers/common.py` — `/invite`, обработка реферала в `/start`;
- `app/services/rating.py` — `calc_referral_bonus` в `calc_combined_rating`.

---

## Prometheus (метрики)

Технология: Prometheus (клиент prometheus-client).

Зачем: сбор метрик бота — число показов ленты и число лайков/скипов. Позволяет оценить нагрузку без разбора логов вручную.

Где в коде:

- `docker-compose.yml` — порт **9100** у сервиса `app`;
- `app/metrics.py` — счётчики `vibedate_feed_views_total`, `vibedate_reactions_total`;
- `app/main.py` — `start_metrics_http_server_if_configured`;
- `app/handlers/dating.py` — `inc_feed_view`, `inc_reaction`;
- `.env.example` — `METRICS_PORT=9100`.

Проверка: `http://localhost:9100/metrics`.

---

## Structlog / JSON-логирование

Технология: structlog.

Зачем: структурированные JSON-логи с timestamp и уровнем. Удобно фильтровать события в Docker (`feed_shown`, `reaction_saved`, `photo_uploaded_minio`), без бессмысленного спама в консоль.

Где в коде:

- `app/main.py` — настройка structlog, события старта;
- `app/handlers/dating.py` — логи сценариев пользователя;
- `app/middleware/rate_limit.py` — лог превышения лимита.

---

## GitHub Actions (CI/CD)

Технология: GitHub Actions.

Зачем: автоматическая проверка проекта при push: unit-тесты формул рейтинга и валидация `docker-compose.yml`.

Где в коде:

- `.github/workflows/ci.yml` — job `test` (pytest + `docker compose config`);
- в репозитории GitHub workflow в корне, код бота в папке `VibeDateBot/`.

---

## Нагрузочное тестирование (JMeter)

Технология: Apache JMeter.

Зачем: демонстрация нагрузочного теста (RPS, latency) на HTTP endpoint метрик бота.

Где в коде:

- `docs/jmeter/metrics-load.jmx` — сценарий: 30 потоков, GET `http://localhost:9100/metrics`, 30 секунд;
- перед тестом поднять стек: `docker compose up -d`, в `.env` указать `METRICS_PORT=9100`.

Запуск: JMeter → Open → `metrics-load.jmx` → Run → Summary Report.

---

## Telegram Bot API / aiogram

Технология: aiogram и Telegram Bot API.

Зачем: основной пользовательский интерфейс. Регистрация, анкета, фото, лента, лайки, скипы, мэтчи с контактами.

Где в коде:

- `app/main.py` — `Bot`, `Dispatcher`, polling;
- `app/handlers/common.py` — `/start`, `/help`, `/invite`;
- `app/handlers/dating.py` — FSM анкеты, лента, callback like/skip;
- `app/keyboards/main.py` — клавиатуры;
- `app/config.py` — `BOT_TOKEN`;
- `Dockerfile` — Python 3.11, `python -m app.main`.

---

## Docker Compose

Технология: Docker Compose.

Зачем: разворачивание всей системы одной командой: БД, Redis, MinIO, RabbitMQ, бот, Celery worker и beat.

Где в коде:

- `docker-compose.yml` — все сервисы, порты, volumes;
- `Dockerfile` — образ приложения;
- `.env.example` — переменные окружения.

Запуск: `docker compose up --build`.

Порты на хосте: Postgres **55432**, Redis **6379**, MinIO API **9000**, MinIO Console **9002**, RabbitMQ **5672** / UI **15672**, метрики **9100**.

---

## Тестирование (pytest)

Технология: pytest.

Зачем: автоматическая проверка формул рейтинга (этап 4 — тестирование продукта).

Где в коде:

- `tests/test_rating.py` — тесты всех трёх уровней рейтинга и реферального бонуса;
- `pytest.ini` — `pythonpath = .`;
- `requirements.txt` — зависимость `pytest`;
- `.github/workflows/ci.yml` — запуск тестов в CI.

Команда: `PYTHONPATH=. python3 -m pytest tests/test_rating.py -q`.

---

## Оптимизация базы данных

Технология: индексы PostgreSQL.

Зачем: ускорение выборки ленты и проверки «уже просмотренных» анкет.

Где в коде:

- `docs/vibedatebd.sql` — `idx_likes_from_profile`, `idx_likes_to_profile`, `idx_profiles_updated_at`, `idx_profiles_city`, `idx_photos_profile`;
- `app/db.py` — те же индексы в `ensure_runtime_schema`.

---

## Этапы продукта (кратко)

Этап 1 — планирование: `docs/vibedatebd.sql`, схема в `docs/`, архитектура в compose.

Этап 2 — базовый бот: `/start`, анкета, aiogram (`app/handlers/`).

Этап 3 — анкеты и ранжирование: CRUD, 3 уровня рейтинга, Redis-кэш ленты, интеграция с ботом.

Этап 4 — дополнительно: Celery, оптимизация БД (индексы), pytest, метрики и логи, MinIO, RabbitMQ, CI, JMeter.

---

## Схема потока данных (для устного ответа)

1. Пользователь открывает ленту — id кандидата из Redis, карточка проверяется в PostgreSQL.
2. Лайк/скип — запись в `likes`, обновление `ratings`, событие в RabbitMQ, метрика Prometheus.
3. Взаимный лайк — `matches`, уведомления через Celery (`notify_match`).
4. Фото — Telegram → MinIO → `photos.s3_key` в PostgreSQL.
5. Раз в 10 минут Celery пересчитывает все рейтинги.
