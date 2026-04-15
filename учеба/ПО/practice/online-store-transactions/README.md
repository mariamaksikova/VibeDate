# Online Store Transactions

Простое решение практики с 3 SQL-транзакциями:

1. Оформление заказа (`Orders` + `OrderItems` + пересчет `TotalAmount`)
2. Обновление email клиента (`Customers`)
3. Добавление нового продукта (`Products`)

## Запуск

```bash
docker compose up --build
```

После запуска сервис `app` подключится к PostgreSQL и выполнит все 3 сценария.
