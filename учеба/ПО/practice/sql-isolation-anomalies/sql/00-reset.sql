TRUNCATE accounts RESTART IDENTITY CASCADE;
TRUNCATE products RESTART IDENTITY CASCADE;

INSERT INTO accounts (holder_name, balance) VALUES
    ('Анна Иванова', 1000.00),
    ('Борис Петров', 500.00);

INSERT INTO products (name, price, category) VALUES
    ('Наушники', 45.00, 'electronics'),
    ('Книга SQL', 35.00, 'books'),
    ('Кабель USB', 12.00, 'electronics'),
    ('Кружка', 18.00, 'home');

SELECT 'accounts' AS table_name, * FROM accounts;
SELECT 'products' AS table_name, * FROM products;
