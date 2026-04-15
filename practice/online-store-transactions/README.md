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

