-- SQL Isolation anomalies demo setup (PostgreSQL)

DROP TABLE IF EXISTS accounts;

CREATE TABLE accounts (
    id BIGSERIAL PRIMARY KEY,
    owner TEXT NOT NULL,
    balance NUMERIC(12, 2) NOT NULL CHECK (balance >= 0),
    city TEXT NOT NULL
);

INSERT INTO accounts (owner, balance, city) VALUES
('alice', 1000.00, 'Moscow'),
('bob', 700.00, 'Moscow'),
('carol', 1200.00, 'Kazan');
