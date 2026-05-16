-- ============================================================
-- DIRTY READ — попытка в PostgreSQL (аномалия НЕ возникает)
-- PostgreSQL: READ UNCOMMITTED работает как READ COMMITTED (MVCC).
-- ============================================================

-- ---------- СЕССИЯ 1 (шаг 1) ----------
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
UPDATE accounts SET balance = 5000.00 WHERE id = 1;
SELECT id, holder_name, balance FROM accounts WHERE id = 1;


-- ---------- СЕССИЯ 2 (шаг 2) ----------
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
SELECT id, holder_name, balance FROM accounts WHERE id = 1;


-- ---------- СЕССИЯ 1 (шаг 3) ----------
ROLLBACK;

