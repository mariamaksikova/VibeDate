-- LOST UPDATE — PostgreSQL, READ COMMITTED

-- СЕССИЯ 1 (шаг 1)
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT id, holder_name, balance FROM accounts WHERE id = 2;

-- СЕССИЯ 2 (шаг 2–3)
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT id, holder_name, balance FROM accounts WHERE id = 2;
UPDATE accounts SET balance = 600.00 WHERE id = 2;
COMMIT;

-- СЕССИЯ 1 (шаг 4)
UPDATE accounts SET balance = 550.00 WHERE id = 2;
COMMIT;

-- Проверка
SELECT id, holder_name, balance FROM accounts WHERE id = 2;
