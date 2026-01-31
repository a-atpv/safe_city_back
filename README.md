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
