# Broker Comparison Practice

Практика: сравнение `RabbitMQ` и `Redis` как брокеров сообщений в одинаковых условиях.

## Что внутри

- `benchmark.py` — запускает серию тестов для двух брокеров;
- `docker-compose.yml` — поднимает RabbitMQ, Redis и runner;
- `results/` — сюда сохраняются `results.csv` и `results.json`.

## Какие эксперименты выполняются

- Размер сообщения: `128B`, `1KB`, `10KB`, `100KB`
- Интенсивность: `1000`, `5000`, `10000` msg/sec
- Для каждой комбинации запускается и RabbitMQ, и Redis
- На каждый прогон отправляется `5000` сообщений

## Метрики

- `throughput_msg_sec`
- `avg_latency_ms`
- `p95_latency_ms`
- `max_latency_ms`
- `sent`, `processed`, `errors`
- `queue_left`

## Запуск

```bash
docker compose up --build
```



