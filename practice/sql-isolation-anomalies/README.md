# Практика: аномалии изоляции в SQL (PostgreSQL)

Практическая работа по параллельным транзакциям: воспроизведение аномалий изоляции в **PostgreSQL** через **pgAdmin** (два окна Query Tool).

## Отчёт 

**[report/REPORT.md](./report/REPORT.md)** — финальный отчёт со скриншотами, шагами воспроизведения, результатами и способами избежать каждую аномалию.

В отчёте:

- все **4 аномалии** из задания (dirty read, non-repeatable read, phantom read, lost update);
- **скриншоты** из pgAdmin в `report/screenshots/`;
- для **dirty read** — попытка воспроизведения и объяснение, почему в PostgreSQL аномалия **не возникает** (MVCC, `READ UNCOMMITTED` = `READ COMMITTED`);
- для остальных трёх — подтверждённые результаты на уровне `READ COMMITTED`;
- раздел «как избежать» для каждой аномалии.

## Результаты по аномалиям


| Аномалия            | В PostgreSQL                           | Уровень изоляции   |
| ------------------- | -------------------------------------- | ------------------ |
| Dirty read          | Не воспроизводится (встроенная защита) | `READ UNCOMMITTED` |
| Non-repeatable read | Воспроизведена                         | `READ COMMITTED`   |
| Phantom read        | Воспроизведена                         | `READ COMMITTED`   |
| Lost update         | Воспроизведена                         | `READ COMMITTED`   |


## Структура проекта

```
sql-isolation-anomalies/
├── README.md                 ← этот файл
├── sql/
│   ├── 00-create-database.sql
│   ├── 01-schema.sql
│   ├── 02-seed-data.sql
│   ├── 00-reset.sql
│   └── anomalies/
│       ├── 01-dirty-read-postgres.sql
│       ├── 02-non-repeatable-read.sql
│       ├── 03-phantom-read.sql
│       └── 04-lost-update.sql
└── report/
    ├── REPORT.md             ← отчёт
    └── screenshots/          ← скриншоты
```

## СУБД и инструменты

- **PostgreSQL** локально (`localhost:5432`)
- **pgAdmin** — два параллельных Query Tool

