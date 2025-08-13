# Vanilla Python Bank App

A minimal full-stack bank app using:
- Backend: Python + Flask (in-memory store; no DB required)
- Frontend: Vanilla HTML/CSS/JS served by Flask

Features:
- Register, login, logout (session-based)
- View balance and recent transactions
- Deposit, withdraw, and transfer to another user
- Health check endpoint

## Quick start

1) Install dependencies with your system Python

```
pip install -r requirements.txt
```

2) Run the server

```
python server.py
```

Open http://127.0.0.1:5000 in your browser.

3) Optional: Run a smoke test (no server needed; uses Flask test client)

```
python scripts/smoke_test.py
```

## Endpoints (JSON)
- POST /api/register { username, password }
- POST /api/login { username, password }
- POST /api/logout
- GET  /api/me
- POST /api/deposit { amount }           # amount as decimal string (e.g., "12.34")
- POST /api/withdraw { amount }
- POST /api/transfer { to_username, amount }
- GET  /api/transactions?limit=10
- GET  /api/health

Notes:
- Amounts are stored as integer cents server-side; frontend converts decimal strings.
- This is a demo app. Do not use in production.

## Dev tips
- Data is in-memory and resets on server restart.
- Session secret is hard-coded for demo. Change `SECRET_KEY` in `server.py` for local tweaks.
