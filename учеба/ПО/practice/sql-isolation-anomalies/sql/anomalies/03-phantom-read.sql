-- PHANTOM READ — PostgreSQL, READ COMMITTED

-- СЕССИЯ 1 (шаг 1)
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT COUNT(*) AS cnt_cheap FROM products WHERE price < 50;

-- СЕССИЯ 2 (шаг 2)
BEGIN;
INSERT INTO products (name, price, category)
VALUES ('Планшет', 29.99, 'electronics');
COMMIT;

-- СЕССИЯ 1 (шаг 3)
SELECT COUNT(*) AS cnt_cheap FROM products WHERE price < 50;
COMMIT;
