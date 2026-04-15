import os
import time
from decimal import Decimal

import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "store_db")
DB_USER = os.getenv("DB_USER", "store_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "store_pass")

app = FastAPI(title="Online Store Transactions API")


class OrderItemInput(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class PlaceOrderRequest(BaseModel):
    customer_id: int = Field(gt=0)
    items: list[OrderItemInput] = Field(min_length=1)


class UpdateEmailRequest(BaseModel):
    customer_id: int = Field(gt=0)
    new_email: str = Field(min_length=5)


class AddProductRequest(BaseModel):
    product_name: str = Field(min_length=1)
    price: Decimal = Field(gt=0)


def get_connection():
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def wait_for_db(max_attempts=20, delay=2):
    for _ in range(max_attempts):
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
            return
        except Exception:
            time.sleep(delay)
    raise RuntimeError("Could not connect to database.")


def scenario_1_place_order(customer_id: int, items: list[OrderItemInput]) -> int:
    with get_connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM Customers
                    WHERE CustomerID = %s;
                    """,
                    (customer_id,),
                )
                if cur.fetchone() is None:
                    raise ValueError(f"Customer {customer_id} not found.")

                cur.execute(
                    """
                    INSERT INTO Orders (CustomerID, OrderDate, TotalAmount)
                    VALUES (%s, NOW(), 0)
                    RETURNING OrderID;
                    """,
                    (customer_id,),
                )
                order_id = cur.fetchone()[0]

                for item in items:
                    cur.execute(
                        """
                        SELECT Price
                        FROM Products
                        WHERE ProductID = %s;
                        """,
                        (item.product_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise ValueError(f"Product {item.product_id} not found.")

                    subtotal = row[0] * item.quantity
                    cur.execute(
                        """
                        INSERT INTO OrderItems (OrderID, ProductID, Quantity, Subtotal)
                        VALUES (%s, %s, %s, %s);
                        """,
                        (order_id, item.product_id, item.quantity, subtotal),
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

    return order_id


def scenario_2_update_customer_email(customer_id: int, new_email: str):
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


def scenario_3_add_product(product_name: str, price: Decimal) -> int:
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
                return cur.fetchone()[0]


@app.on_event("startup")
def on_startup():
    wait_for_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/scenario1/place-order")
def place_order(payload: PlaceOrderRequest):
    try:
        order_id = scenario_1_place_order(payload.customer_id, payload.items)
        return {"message": "Order created", "order_id": order_id}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.patch("/scenario2/customer-email")
def update_email(payload: UpdateEmailRequest):
    try:
        scenario_2_update_customer_email(payload.customer_id, payload.new_email)
        return {"message": "Customer email updated"}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status_code=400, detail="Email already exists")


@app.post("/scenario3/product")
def add_product(payload: AddProductRequest):
    product_id = scenario_3_add_product(payload.product_name, payload.price)
    return {"message": "Product added", "product_id": product_id}
