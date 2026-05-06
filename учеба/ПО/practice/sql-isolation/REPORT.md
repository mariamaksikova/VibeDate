# ПРАКТИКА: АНОМАЛИИ ИЗОЛЯЦИИ В SQL

## Выбранная БД

- PostgreSQL
- Базовый уровень изоляции в примерах: `READ COMMITTED` (где не указано иначе)

## Подготовка

1. Выполнить `schema_and_seed.sql`.
2. Открыть два параллельных SQL-сеанса:
   - `Session A`
   - `Session B`
3. Для чистоты экспериментов перед каждым сценарием возвращать тестовые данные:

```sql
UPDATE accounts
SET balance = CASE owner
    WHEN 'alice' THEN 1000.00
    WHEN 'bob' THEN 700.00
    WHEN 'carol' THEN 1200.00
END,
city = CASE owner
    WHEN 'alice' THEN 'Moscow'
    WHEN 'bob' THEN 'Moscow'
    WHEN 'carol' THEN 'Kazan'
END;
```

---

## 1) Dirty Read (грязное чтение)

> В PostgreSQL в `READ COMMITTED` грязное чтение не допускается. Ниже показан тест, где аномалия **не воспроизводится**, что тоже корректный результат.

### Шаги воспроизведения

**Session A**

```sql
BEGIN;
UPDATE accounts SET balance = 1.00 WHERE owner = 'alice';
-- Транзакцию НЕ коммитим
```

**Session B**

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT balance FROM accounts WHERE owner = 'alice';
COMMIT;
```

**Session A**

```sql
ROLLBACK;
```

### Полученный результат

- `Session B` видит старое подтвержденное значение (`1000.00`), а не `1.00`.
- Dirty read не возникает.

### Как избежать

- Использовать `READ COMMITTED` и выше.
- Не использовать `READ UNCOMMITTED` в СУБД, где он действительно допускает грязные чтения.

---

## 2) Non-Repeatable Read (неповторяемое чтение)

### Шаги воспроизведения

**Session A**

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT balance FROM accounts WHERE owner = 'bob'; -- 700.00
```

**Session B**

```sql
BEGIN;
UPDATE accounts SET balance = 900.00 WHERE owner = 'bob';
COMMIT;
```

**Session A**

```sql
SELECT balance FROM accounts WHERE owner = 'bob'; -- уже 900.00
COMMIT;
```

### Полученный результат

- Внутри одной транзакции `Session A` прочитала разные значения одной строки.
- Non-repeatable read воспроизводится.

### Как избежать

- Повысить изоляцию до `REPEATABLE READ` или `SERIALIZABLE`.
- При необходимости использовать блокировку `SELECT ... FOR UPDATE`.

---

## 3) Phantom Read (фантомное чтение)

### Шаги воспроизведения

**Session A**

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT COUNT(*) FROM accounts WHERE city = 'Moscow'; -- 2
```

**Session B**

```sql
BEGIN;
INSERT INTO accounts (owner, balance, city)
VALUES ('dave', 400.00, 'Moscow');
COMMIT;
```

**Session A**

```sql
SELECT COUNT(*) FROM accounts WHERE city = 'Moscow'; -- 3
COMMIT;
```

### Полученный результат

- Повторный запрос в `Session A` вернул больше строк из-за вставки в `Session B`.
- Phantom read воспроизводится.

### Как избежать

- Использовать `REPEATABLE READ`/`SERIALIZABLE`.
- Для критичных диапазонов применять подходящие блокировки и дизайн транзакций.

---

## 4) Lost Update (потерянное обновление)

### Шаги воспроизведения

Перед сценарием вернуть `alice` к `1000.00`.

**Session A**

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT balance FROM accounts WHERE owner = 'alice'; -- 1000.00
-- логика: +100
```

**Session B**

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT balance FROM accounts WHERE owner = 'alice'; -- 1000.00
-- логика: +300
UPDATE accounts SET balance = 1300.00 WHERE owner = 'alice';
COMMIT;
```

**Session A**

```sql
UPDATE accounts SET balance = 1100.00 WHERE owner = 'alice';
COMMIT;
```

Проверка:

```sql
SELECT balance FROM accounts WHERE owner = 'alice'; -- 1100.00
```

### Полученный результат

- Обновление `Session B` (до `1300.00`) перезаписано коммитом `Session A` (`1100.00`).
- Lost update воспроизводится.

### Как избежать

- Пессимистическая блокировка: `SELECT ... FOR UPDATE`.
- Оптимистический контроль версий (столбец `version` и `UPDATE ... WHERE version = ...`).
- Изоляция `SERIALIZABLE` для критичных финансовых операций.

---

## Итог

- Выбраны 4 аномалии: `dirty read`, `non-repeatable read`, `phantom read`, `lost update`.
- Фактически воспроизведены 3 аномалии (`non-repeatable`, `phantom`, `lost update`).
- Для `dirty read` показан отрицательный результат (в PostgreSQL это нормальное поведение при `READ COMMITTED`).

## Что приложить к сдаче

- Скриншоты из двух сессий SQL по каждому сценарию.
- Скриншот состояния таблицы после каждого сценария.
