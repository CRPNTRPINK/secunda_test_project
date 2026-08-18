# Асинхронный сервис процессинга платежей

Микросервис принимает запросы на оплату, асинхронно обрабатывает их через эмуляцию
внешнего платежного шлюза и уведомляет клиента о результате через webhook.

**Стек:** FastAPI + Pydantic v2 · SQLAlchemy 2.0 (async) · PostgreSQL 16 · RabbitMQ 3.13
(FastStream) · Alembic · Docker Compose.

---

## Содержание

- [Быстрый старт](#быстрый-старт)
- [Примеры запросов](#примеры-запросов)
- [Архитектура](#архитектура)
- [Outbox pattern](#outbox-pattern)
- [Идемпотентность](#идемпотентность)
- [Retry и Dead Letter Queue](#retry-и-dead-letter-queue)
- [Webhook](#webhook)
- [Модель данных](#модель-данных)
- [Конфигурация](#конфигурация)
- [Разработка и тесты](#разработка-и-тесты)
- [Структура проекта](#структура-проекта)

---

## Быстрый старт

```bash
cp .env.example .env          # при необходимости поправьте API_KEY и порты
docker compose up -d --build
```

Поднимаются четыре сервиса: `postgres`, `rabbitmq`, `api`, `consumer`.
Миграции Alembic накатываются автоматически при старте `api`; `consumer` стартует
после того, как `api` становится healthy.

| Сервис | Адрес с хоста | Порт внутри сети compose |
|---|---|---|
| API | http://localhost:8000 | 8000 |
| Swagger UI | http://localhost:8000/docs | — |
| Health check | http://localhost:8000/health | — |
| RabbitMQ UI | http://localhost:15673 (guest / guest) | 15672 |
| RabbitMQ AMQP | `amqp://guest:guest@localhost:55672/` | 5672 |
| PostgreSQL | `postgresql://payments:payments@localhost:55432/payments` | 5432 |

Наружу Postgres и RabbitMQ отдаются на нестандартных портах (`55432`, `55672`,
`15673`) — чтобы стенд не конфликтовал с локально установленными сервисами и
`docker compose up` не падал с `port is already allocated`. Внутри сети compose
всё общается по обычным `5432` и `5672`, поэтому `DATABASE_URL` и `RABBITMQ_URL`
у сервисов не меняются. Свои порты задаются в `.env`:

```bash
POSTGRES_PORT=5432        # вернуть стандартные, если локальных Postgres/RabbitMQ нет
RABBITMQ_PORT=5672
RABBITMQ_UI_PORT=15672
API_PORT=8000
```

Дополнительно есть демо-приёмник webhook'ов (профиль `demo`):

```bash
docker compose --profile demo up -d webhook-echo     # слушает http://localhost:9000/hook
curl http://localhost:9000/received                  # что он получил
```

Остановить всё: `docker compose --profile demo down` (с данными — добавьте `-v`).

---

## Примеры запросов

Все эндпоинты требуют заголовок `X-API-Key` (значение — `API_KEY`, по умолчанию
`local-dev-api-key`). Исключение — `/health`.

### 1. Создание платежа

```bash
curl -i -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: local-dev-api-key" \
  -H "Idempotency-Key: order-42-attempt-1" \
  -H "Content-Type: application/json" \
  -d '{
        "amount": "1500.00",
        "currency": "RUB",
        "description": "Order #42",
        "metadata": {"order_id": 42, "source": "mobile"},
        "webhook_url": "http://webhook-echo:9000/hook"
      }'
```

```http
HTTP/1.1 202 Accepted
Location: /api/v1/payments/440b0757-02e5-4b6b-b68e-90ad50533132
Idempotent-Replay: false

{
  "payment_id": "440b0757-02e5-4b6b-b68e-90ad50533132",
  "status": "pending",
  "created_at": "2026-08-18T04:59:58.479846Z"
}
```

> `webhook_url` указывается в системе координат consumer'а. Для контейнера
> демо-приёмника это `http://webhook-echo:9000/hook`, для сервиса на хосте —
> `http://host.docker.internal:PORT/...`.

### 2. Получение платежа

```bash
curl -s http://localhost:8000/api/v1/payments/440b0757-02e5-4b6b-b68e-90ad50533132 \
  -H "X-API-Key: local-dev-api-key"
```

```json
{
  "id": "440b0757-02e5-4b6b-b68e-90ad50533132",
  "amount": "1500.00",
  "currency": "RUB",
  "description": "Order #42",
  "metadata": {"order_id": 42, "source": "mobile"},
  "status": "succeeded",
  "idempotency_key": "order-42-attempt-1",
  "webhook_url": "http://webhook-echo:9000/hook",
  "webhook_attempts": 1,
  "webhook_delivered_at": "2026-08-18T05:00:02.202148Z",
  "failure_reason": null,
  "created_at": "2026-08-18T04:59:58.479846Z",
  "processed_at": "2026-08-18T05:00:02.159470Z"
}
```

### Коды ответов

| Код | Когда |
|---|---|
| 202 | Платеж принят в обработку (в т.ч. повторный запрос с тем же `Idempotency-Key`) |
| 200 | Платеж найден (GET) |
| 400 | Отсутствует или пустой `Idempotency-Key` |
| 401 | Нет заголовка `X-API-Key` |
| 403 | Неверный API-ключ |
| 404 | Платеж не найден |
| 409 | `Idempotency-Key` уже использован с другим телом запроса |
| 422 | Ошибка валидации тела запроса или `payment_id` |

---

## Архитектура

```
       ┌──────────┐  1. INSERT payment + outbox (одна транзакция)
HTTP ─▶│   api    │──────────────────────────────────┐
       │ FastAPI  │                                  ▼
       └──────────┘                            ┌───────────┐
             ▲ 5. GET /payments/{id}           │ PostgreSQL │
             └─────────────────────────────────│ payments   │
                                               │ outbox     │
       ┌───────────────────────────┐           └───────────┘
       │        consumer           │              ▲     ▲
       │ ┌───────────────────────┐ │  2. SELECT ... FOR UPDATE SKIP LOCKED
       │ │  outbox relay (task)  │─┼──────────────┘     │
       │ └───────────┬───────────┘ │                    │ 4. UPDATE status
       │             │ publish     │                    │
       │             ▼             │                    │
       │      RabbitMQ payments.new│                    │
       │             │             │                    │
       │ ┌───────────▼───────────┐ │  3. charge (2-5 c, 90/10)  │
       │ │  payment processor    │─┼────────────────────────────┘
       │ └───────────┬───────────┘ │
       └─────────────┼─────────────┘
                     │ 4. POST webhook_url
                     ▼
              клиентский сервис
```

Процесс `consumer` совмещает две задачи: подписчик FastStream на очередь
`payments.new` и фоновый outbox relay. Relay использует `FOR UPDATE SKIP LOCKED`,
поэтому `docker compose up -d --scale consumer=3` безопасен — реплики не будут
публиковать одно и то же событие.

### Топология RabbitMQ

```
outbox relay ──▶ exchange payments (direct)
                        │ rk = payments.new
                        ▼
                 ┌──────────────┐   ошибка (attempt < 3)     ┌────────────────┐
                 │ payments.new │ ─────────────────────────▶ │ payments.retry │
                 └──────┬───────┘   publish c per-message    │  (очередь      │
                        ▲            TTL = backoff           │   ожидания)    │
                        └───────────────────────────────────┐└───────┬────────┘
                        │  TTL истёк → dead-letter обратно  ─┘        │
                        │                                            │
             x-dead-letter-exchange (reject/креш consumer'а)          │
                        │                                            │
                        ▼                                            │
              exchange payments.dlx ──▶ payments.dlq ◀───────────────┘
                                                    исчерпаны 3 попытки
```

- `payments.new` — рабочая очередь; её `x-dead-letter-exchange` = `payments.dlx`
  страхует от падения процесса (непрочитанное сообщение уедет в DLQ, а не потеряется).
- `payments.retry` — очередь ожидания без потребителей: сообщение лежит в ней
  ровно `expiration` мс, после чего dead-letter возвращает его в `payments.new`.
- `payments.dlq` — сообщения, окончательно упавшие после 3 попыток; в заголовках
  лежат `x-attempt` и `x-last-error`.

---

## Outbox pattern

API **никогда не публикует в брокер напрямую**. В одной транзакции пишутся строка
в `payments` и строка в `outbox` — либо сохраняется всё, либо ничего. Событие
уходит в RabbitMQ отдельным процессом (`OutboxRelay`, `app/broker/outbox_relay.py`):

1. `SELECT ... WHERE status='pending' AND available_at <= now() FOR UPDATE SKIP LOCKED LIMIT N`;
2. `broker.publish(...)` в exchange `payments` c `persist=True`;
3. успех → `status='published'`, `published_at=now()`;
   ошибка → `attempts += 1` и `available_at = now() + экспоненциальная задержка`,
   после `OUTBOX_MAX_ATTEMPTS` попыток → `status='failed'` (видно для алертов).

Проверено вручную: при остановленном RabbitMQ запрос всё равно возвращает `202`,
событие лежит в `outbox` со статусом `pending`, а после старта брокера relay
публикует его и платеж дообрабатывается.

Гарантия — **at-least-once**: возможна повторная доставка, поэтому обработчик
идемпотентен (см. ниже).

---

## Идемпотентность

**На входе (API).** `Idempotency-Key` обязателен и хранится в `payments` под
`UNIQUE`-индексом. Дополнительно считается SHA-256 канонизированного тела запроса
(`request_fingerprint`):

- тот же ключ + то же тело → `202` с уже существующим `payment_id`
  и заголовком `Idempotent-Replay: true`, повторной обработки не происходит;
- тот же ключ + другое тело → `409 Conflict`;
- гонка двух параллельных запросов ловится через `IntegrityError` и
  превращается в тот же ответ-повтор.

**В обработчике (consumer).** Перед вызовом шлюза проверяется статус платежа:
если он уже не `pending`, повторная доставка не списывает деньги второй раз, а
только до-отправляет webhook. Доставленный webhook помечается
`webhook_delivered_at` и повторно не отправляется.

---

## Retry и Dead Letter Queue

- Максимум попыток: `MAX_DELIVERY_ATTEMPTS` (по умолчанию **3**).
- Задержка: экспоненциальная, `RETRY_BASE_DELAY_SECONDS * 2^(attempt-1)`,
  ограничена `RETRY_MAX_DELAY_SECONDS` → по умолчанию **2 с, 4 с**, затем DLQ.
- Счётчик попыток едет в заголовке сообщения `x-attempt`, причина последней
  ошибки — в `x-last-error`.
- Обработчик не бросает исключение наружу, а сам решает судьбу сообщения: это
  даёт точный контроль над задержкой и числом попыток (штатный requeue RabbitMQ
  мгновенный и неограниченный).
- `NonRetryableError` (например, платеж отсутствует в БД) отправляется в DLQ сразу.

Лог реальной прогонки с недоступным webhook-приёмником:

```
WARNING  Payment 055e01da... failed on attempt 1/3: webhook delivery failed: unexpected status 500
INFO     Payment 055e01da...: attempt 2 in 2s
WARNING  Payment 055e01da... failed on attempt 2/3: webhook delivery failed: unexpected status 500
INFO     Payment 055e01da...: attempt 3 in 4s
WARNING  Payment 055e01da... failed on attempt 3/3: webhook delivery failed: unexpected status 500
ERROR    Payment 055e01da... moved to DLQ after 3 attempt(s)
```

Посмотреть очереди и содержимое DLQ:

```bash
docker compose exec rabbitmq rabbitmqctl list_queues name messages
# или RabbitMQ UI: http://localhost:15673 → Queues → payments.dlq → Get messages
```

---

## Webhook

После обновления статуса consumer отправляет `POST` на `webhook_url`:

```json
{
  "event": "payment.succeeded",
  "payment_id": "440b0757-02e5-4b6b-b68e-90ad50533132",
  "status": "succeeded",
  "amount": "1500.00",
  "currency": "RUB",
  "description": "Order #42",
  "metadata": {"order_id": 42},
  "failure_reason": null,
  "created_at": "2026-08-18T04:59:58.479846Z",
  "processed_at": "2026-08-18T05:00:02.159470Z"
}
```

Заголовки: `X-Webhook-Event` (`payment.succeeded` / `payment.failed`) и `X-Payment-Id`.
Успехом считается любой `2xx`; таймаут — `WEBHOOK_TIMEOUT_SECONDS`. Неуспех
приводит к повторной попытке через очередь ожидания (см. выше), число попыток
и текст последней ошибки видны в полях `webhook_attempts` / `webhook_last_error`.

Проверить повторы и DLQ локально:

```bash
WEBHOOK_ECHO_FAIL=true docker compose --profile demo up -d --force-recreate webhook-echo
# создать платеж с webhook_url=http://webhook-echo:9000/hook и смотреть логи:
docker compose logs -f consumer
```

---

## Модель данных

**payments**

| Поле | Тип | Комментарий |
|---|---|---|
| `id` | uuid PK | идентификатор платежа |
| `idempotency_key` | varchar(255) UNIQUE | ключ идемпотентности |
| `request_fingerprint` | char(64) | SHA-256 тела запроса |
| `amount` | numeric(18,2) | `CHECK (amount > 0)` |
| `currency` | enum | `RUB`, `USD`, `EUR` |
| `description` | text | |
| `metadata` | jsonb | произвольные данные клиента |
| `status` | enum | `pending`, `succeeded`, `failed` |
| `failure_reason` | text | причина отказа шлюза |
| `webhook_url` | varchar(2048) | |
| `webhook_attempts` | int | сделано попыток доставки |
| `webhook_delivered_at` | timestamptz | флаг успешной доставки |
| `webhook_last_error` | text | |
| `created_at` / `processed_at` | timestamptz | создание / завершение обработки |

**outbox**

| Поле | Тип | Комментарий |
|---|---|---|
| `id` | uuid PK | он же `event_id` в сообщении |
| `aggregate_type` / `aggregate_id` | varchar / uuid | `payment` / `payment_id` |
| `event_type` | varchar(128) | `payment.created` |
| `routing_key` | varchar(128) | `payments.new` |
| `payload` | jsonb | тело сообщения |
| `status` | enum | `pending`, `published`, `failed` |
| `attempts` | int | попыток публикации |
| `available_at` | timestamptz | когда можно публиковать (backoff) |
| `published_at`, `last_error`, `created_at` | | |

Миграции: `migrations/versions/0001_initial_schema.py`.

```bash
docker compose exec api alembic upgrade head     # накатить
docker compose exec api alembic downgrade -1     # откатить
docker compose exec api alembic revision --autogenerate -m "..."
```

---

## Конфигурация

Все параметры читаются из переменных окружения (`app/core/config.py`), полный
список — в `.env.example`. В таблице ниже указаны значения, с которыми сервис
работает в `docker compose` (для запуска без Docker в `DATABASE_URL` /
`RABBITMQ_URL` подставьте `localhost`).

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `API_KEY` | `local-dev-api-key` | статический ключ для `X-API-Key` |
| `DATABASE_URL` | `postgresql+asyncpg://payments:payments@postgres:5432/payments` | БД |
| `RABBITMQ_URL` | `amqp://guest:guest@rabbitmq:5672/` | брокер |
| `PROCESSING_MIN_SECONDS` / `PROCESSING_MAX_SECONDS` | `2` / `5` | длительность эмуляции шлюза |
| `PROCESSING_SUCCESS_RATE` | `0.9` | доля успешных платежей |
| `MAX_DELIVERY_ATTEMPTS` | `3` | попыток обработки сообщения до DLQ |
| `RETRY_BASE_DELAY_SECONDS` / `RETRY_MAX_DELAY_SECONDS` | `2` / `60` | экспоненциальный backoff |
| `WEBHOOK_TIMEOUT_SECONDS` | `10` | таймаут запроса на webhook |
| `OUTBOX_POLL_INTERVAL_SECONDS` / `OUTBOX_BATCH_SIZE` | `1` / `50` | работа relay |
| `OUTBOX_MAX_ATTEMPTS` | `10` | попыток публикации события |
| `CONSUMER_PREFETCH_COUNT` | `10` | сколько сообщений consumer обрабатывает параллельно |
| `LOG_LEVEL` | `INFO` | уровень логирования |

Например, чтобы посмотреть на ветку `failed`, поднимите consumer с
`PROCESSING_SUCCESS_RATE=0`.

---

## Разработка и тесты

Локально, с инфраструктурой из compose (обрати внимание на порты хоста):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
docker compose up -d postgres rabbitmq          # инфраструктура в контейнерах
export DATABASE_URL=postgresql+asyncpg://payments:payments@localhost:55432/payments
export RABBITMQ_URL=amqp://guest:guest@localhost:55672/
alembic upgrade head
uvicorn app.main:app --reload      # терминал 1: API
python -m app.worker               # терминал 2: consumer + outbox relay
```

Тесты и линтер (инфраструктура не требуется):

```bash
pytest        # 36 тестов: валидация схем, отпечаток тела запроса для идемпотентности,
              # backoff, выбор retry/DLQ в consumer, отправка webhook (httpx.MockTransport),
              # контракт API (аутентификация и валидация)
ruff check .
```

Совпадение моделей с миграцией проверяется одной командой:

```bash
docker compose exec api alembic check
```

---

## Структура проекта

```
app/
├── api/
│   ├── deps.py              # X-API-Key, Idempotency-Key, сессия БД
│   └── v1/payments.py       # POST /payments, GET /payments/{id}
├── broker/
│   ├── topology.py          # обменники, очереди, DLQ, заголовки
│   ├── broker.py            # RabbitBroker + декларация топологии
│   ├── outbox_relay.py      # публикация событий из outbox
│   └── consumer.py          # обработчик payments.new: шлюз + webhook + retry
├── core/                    # настройки и логирование
├── db/                      # Base, engine, session factory
├── models/                  # Payment, OutboxMessage, enum'ы
├── schemas/                 # Pydantic-модели запросов, ответов, событий
├── services/                # бизнес-логика: payments, outbox, gateway, webhook, retry
├── main.py                  # FastAPI-приложение
└── worker.py                # процесс consumer + outbox relay
migrations/                  # Alembic
scripts/                     # entrypoint'ы контейнеров и демо-приёмник webhook
tests/                       # pytest
```
