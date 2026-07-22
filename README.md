# Safe City Backend

Backend API для системы экстренного реагирования Safe City.

## Технологии

- **FastAPI** - веб-фреймворк
- **PostgreSQL** - база данных
- **Redis** - кеширование и OTP
- **SQLAlchemy** - ORM
- **Alembic** - миграции
- **JWT** - аутентификация

## Запуск через Docker

```bash
# Запустить все сервисы
docker-compose up -d

# Посмотреть логи
docker-compose logs -f api

# Остановить
docker-compose down
```

## Локальная разработка

```bash
# Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
.\venv\Scripts\activate  # Windows

# Установить зависимости
pip install -r requirements.txt

# Скопировать .env
cp .env.example .env

# Запустить PostgreSQL и Redis (через Docker)
docker-compose up -d db redis

# Применить миграции
alembic upgrade head

# Запустить сервер
uvicorn app.main:app --reload
```

## API Документация

После запуска:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Структура проекта

```
safe_city_back/
├── app/
│   ├── api/           # API роуты
│   │   ├── routes/
│   │   │   ├── auth.py
│   │   │   ├── user.py
│   │   │   └── emergency.py
│   │   └── deps.py    # Зависимости (auth, etc.)
│   ├── core/          # Конфигурация
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── security.py
│   │   └── redis.py
│   ├── models/        # SQLAlchemy модели
│   ├── schemas/       # Pydantic схемы
│   ├── services/      # Бизнес-логика
│   └── main.py
├── alembic/           # Миграции БД
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## API Endpoints

### Auth
- `POST /api/v1/auth/request-otp` - Запросить OTP код
- `POST /api/v1/auth/verify-otp` - Подтвердить OTP и получить токены
- `POST /api/v1/auth/refresh` - Обновить токены

### User
- `GET /api/v1/user/me` - Профиль пользователя
- `PATCH /api/v1/user/me` - Обновить профиль
- `POST /api/v1/user/location` - Обновить геолокацию
- `GET /api/v1/user/subscription` - Статус подписки
- `DELETE /api/v1/user/me` - Удалить аккаунт

### Emergency
- `POST /api/v1/emergency/call` - Создать вызов (SOS)
- `GET /api/v1/emergency/call/active` - Активный вызов
- `GET /api/v1/emergency/call/{id}` - Получить вызов
- `POST /api/v1/emergency/call/{id}/cancel` - Отменить вызов
- `GET /api/v1/emergency/history` - История вызовов

## Telegram-бот для админов

Живёт в `app/bot/` и работает вебхуком **внутри того же процесса**, что и API:
отдельный dyno и отдельное приложение на Heroku не нужны.

- `/stats` — пользователи (всего / за 24 ч / 7 / 30 дней), активные подписки,
  автопродление, платежи и выручка
- уведомление в чат при каждой оплате подписки (новая или продление) —
  отправляется из `PaymentService.handle_successful_result` в фоне

Настройка:

1. `@BotFather` → `/newbot` → скопировать токен.
2. Задать переменные окружения:
   ```bash
   heroku config:set -a safe-city-back \
     TELEGRAM_BOT_TOKEN=123456:AA... \
     PUBLIC_BASE_URL=https://safe-city-back-7c8ed50edd7d.herokuapp.com
   ```
   `PUBLIC_BASE_URL` — точный домен из `heroku domains -a safe-city-back`.
   Короткий `safe-city-back.herokuapp.com` на это приложение не ведёт (404),
   и вебхук, зарегистрированный на него, не получит ни одного апдейта.
3. Написать боту (или в группе, куда он добавлен) `/id` и подставить ответ:
   ```bash
   heroku config:set -a safe-city-back TELEGRAM_ADMIN_CHAT_IDS=123456789,-1002345678901:15
   ```
   Через запятую можно перечислить несколько чатов. У групп id отрицательный;
   суффикс `:15` — id темы форума, если уведомления должны падать в неё, а не
   в «General». Команда `/id` в теме сразу печатает значение в нужном формате.

Список команд для `@BotFather` → `/setcommands`:

```
stats - Статистика: пользователи, подписки, платежи
id - Показать ID этого чата
help - Список команд
```

Вебхук регистрируется автоматически при старте приложения. Диагностика:
`python scratch/telegram_webhook.py`. Без `TELEGRAM_BOT_TOKEN` бот полностью
выключен и на работу API не влияет.
