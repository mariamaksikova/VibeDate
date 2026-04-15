import os
import time

import psycopg


DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "store_db")
DB_USER = os.getenv("DB_USER", "store_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "store_pass")


def get_connection():
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def wait_for_db(max_attempts=20, delay=2):
    for attempt in range(1, max_attempts + 1):
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
            print("Database is ready.")
            return
        except Exception as error:
            print(f"DB not ready (attempt {attempt}/{max_attempts}): {error}")
            time.sleep(delay)
    raise RuntimeError("Could not connect to database.")


def scenario_1_place_order(customer_id, items):
    with get_connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO Orders (CustomerID, OrderDate, TotalAmount)
                    VALUES (%s, NOW(), 0)
                    RETURNING OrderID;
                    """,
                    (customer_id,),
                )
                order_id = cur.fetchone()[0]

                for product_id, quantity in items:
                    cur.execute(
                        """
                        SELECT Price
                        FROM Products
                        WHERE ProductID = %s;
                        """,
                        (product_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise ValueError(f"Product {product_id} not found.")

                    price = row[0]
                    subtotal = price * quantity

                    cur.execute(
                        """
                        INSERT INTO OrderItems (OrderID, ProductID, Quantity, Subtotal)
                        VALUES (%s, %s, %s, %s);
                        """,
                        (order_id, product_id, quantity, subtotal),
                    )

                cur.execute(
                    """
                    UPDATE Orders
                    SET TotalAmount = (
                        SELECT COALESCE(SUM(Subtotal), 0)
                        FROM OrderItems
                        WHERE OrderID = %s
                    )
                    WHERE OrderID = %s;
                    """,
                    (order_id, order_id),
                )

    print(f"Scenario 1 complete: order #{order_id} created.")


def scenario_2_update_customer_email(customer_id, new_email):
    with get_connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE Customers
                    SET Email = %s
                    WHERE CustomerID = %s;
                    """,
                    (new_email, customer_id),
                )

                if cur.rowcount == 0:
                    raise ValueError(f"Customer {customer_id} not found.")

    print(f"Scenario 2 complete: customer #{customer_id} email updated.")


def scenario_3_add_product(product_name, price):
    with get_connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO Products (ProductName, Price)
                    VALUES (%s, %s)
                    RETURNING ProductID;
                    """,
                    (product_name, price),
                )
                product_id = cur.fetchone()[0]

    print(f"Scenario 3 complete: product #{product_id} added.")


if __name__ == "__main__":
    wait_for_db()

    scenario_3_add_product("Webcam", 55.00)
    scenario_2_update_customer_email(1, "ivan.petrov+new@mail.com")
    scenario_1_place_order(1, [(1, 2), (2, 1)])
