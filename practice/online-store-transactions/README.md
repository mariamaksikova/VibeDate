# Online Store Transactions (Postman API)

Сервис с 3 SQL-транзакциями:

1. Оформление заказа (`Orders` + `OrderItems` + пересчет `TotalAmount`)
2. Обновление email клиента (`Customers`)
3. Добавление нового продукта (`Products`)

## Запуск

```bash
docker compose up --build
```

API будет доступен на `http://localhost:8000`.

## Запросы для Postman

### 1) Сценарий 3: добавить продукт

- Method: `POST`
- URL: `http://localhost:8000/scenario3/product`
- Body (JSON):

```json
{
  "product_name": "Headphones",
  "price": 99.99
}
```

### 2) Сценарий 2: обновить email клиента

- Method: `PATCH`
- URL: `http://localhost:8000/scenario2/customer-email`
- Body (JSON):

```json
{
  "customer_id": 1,
  "new_email": "new_mail@mail.com"
}
```

### 3) Сценарий 1: создать заказ

- Method: `POST`
- URL: `http://localhost:8000/scenario1/place-order`
- Body (JSON):

```json
{
  "customer_id": 1,
  "items": [
    { "product_id": 1, "quantity": 2 },
    { "product_id": 2, "quantity": 1 }
  ]
}
```
