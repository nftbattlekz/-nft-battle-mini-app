# NFT BATTLE — Multiplayer Telegram Mini App

## Запуск локально
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py

Откройте http://127.0.0.1:8080

Для Telegram Mini App нужен HTTPS-адрес.

## Что есть на сервере
- SQLite база пользователей/NFT/боёв/транзакций
- общий серверный баланс
- серверный рандом кейсов
- серверный Battle
- серверный апгрейд
- leaderboard
- REST API

## ВАЖНО ДЛЯ PRODUCTION
В server.py endpoint user_id сейчас имеет DEMO fallback и принимает X-Telegram-User-Id.
Нельзя использовать это в продакшене: пользователь может подменить ID.

Перед публикацией необходимо:
1. Получать Telegram.WebApp.initData из клиента.
2. Проверять initData по BOT_TOKEN на сервере согласно Telegram Web Apps authentication.
3. После проверки брать user.id только из проверенных данных.
4. Перейти с SQLite на PostgreSQL для реального деплоя.
5. Добавить CSRF/auth/rate limits и журналирование.
6. Рандом генерировать только на сервере.
7. Не связывать Credits с реальными деньгами/выводом в этой версии.

## API
GET /api/me
POST /api/open {"case":"starter"}
POST /api/battle {"nft_id":123}
POST /api/upgrade
GET /api/leaderboard
GET /health
