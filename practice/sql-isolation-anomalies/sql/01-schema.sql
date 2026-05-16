
CREATE TABLE IF NOT EXISTS accounts (
    id          SERIAL PRIMARY KEY,
    holder_name TEXT NOT NULL,
    balance     NUMERIC(12, 2) NOT NULL CHECK (balance >= 0)
);

CREATE TABLE IF NOT EXISTS products (
    id       SERIAL PRIMARY KEY,
    name     TEXT NOT NULL,
    price    NUMERIC(10, 2) NOT NULL CHECK (price > 0),
    category TEXT NOT NULL DEFAULT 'general'
);
