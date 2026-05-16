-- NON-REPEATABLE READ — PostgreSQL, READ COMMITTED

-- СЕССИЯ 1 (шаг 1)
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT id, holder_name, balance FROM accounts WHERE id = 1;

-- СЕССИЯ 2 (шаг 2)
BEGIN;
UPDATE accounts SET balance = 2000.00 WHERE id = 1;
COMMIT;

-- СЕССИЯ 1 (шаг 3)
SELECT id, holder_name, balance FROM accounts WHERE id = 1;
COMMIT;
