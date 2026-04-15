CREATE TABLE IF NOT EXISTS Customers (
    CustomerID SERIAL PRIMARY KEY,
    FirstName VARCHAR(100) NOT NULL,
    LastName VARCHAR(100) NOT NULL,
    Email VARCHAR(255) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS Products (
    ProductID SERIAL PRIMARY KEY,
    ProductName VARCHAR(255) NOT NULL,
    Price NUMERIC(10, 2) NOT NULL CHECK (Price >= 0)
);

CREATE TABLE IF NOT EXISTS Orders (
    OrderID SERIAL PRIMARY KEY,
    CustomerID INT NOT NULL REFERENCES Customers(CustomerID),
    OrderDate TIMESTAMP NOT NULL DEFAULT NOW(),
    TotalAmount NUMERIC(10, 2) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS OrderItems (
    OrderItemID SERIAL PRIMARY KEY,
    OrderID INT NOT NULL REFERENCES Orders(OrderID) ON DELETE CASCADE,
    ProductID INT NOT NULL REFERENCES Products(ProductID),
    Quantity INT NOT NULL CHECK (Quantity > 0),
    Subtotal NUMERIC(10, 2) NOT NULL CHECK (Subtotal >= 0)
);

INSERT INTO Customers (FirstName, LastName, Email)
VALUES
    ('Ivan', 'Petrov', 'ivan.petrov@mail.com'),
    ('Anna', 'Sidorova', 'anna.sidorova@mail.com')
ON CONFLICT (Email) DO NOTHING;

INSERT INTO Products (ProductName, Price)
VALUES
    ('Keyboard', 30.00),
    ('Mouse', 15.00),
    ('Monitor', 200.00)
ON CONFLICT DO NOTHING;
