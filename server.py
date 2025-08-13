import os
import threading
from decimal import Decimal, ROUND_DOWN
from flask import Flask, jsonify, request, session, send_from_directory, render_template
from werkzeug.security import generate_password_hash, check_password_hash

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    static_folder=os.path.join(ROOT_DIR, 'static'),
    template_folder=os.path.join(ROOT_DIR, 'templates'),
)
app.config['SECRET_KEY'] = 'dev-secret-change-me'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# --- In-memory store (no DB) ---

store_lock = threading.Lock()
next_user_id = 1
users_by_username = {}           # username -> { id, username, password_hash }
accounts_by_user_id = {}         # user_id -> balance_cents
transactions_by_user_id = {}     # user_id -> [ { type, amount_cents, counterparty, created_at } ]

def init_store_once():
    global next_user_id
    # Nothing to pre-seed; function exists for parity with older init hook
    if 'initialized' not in globals():
        globals()['initialized'] = True


# --- Utils ---

def to_cents(amount_str: str) -> int:
    d = (Decimal(amount_str).quantize(Decimal('0.01'), rounding=ROUND_DOWN))
    return int(d * 100)


def to_decimal_str(cents: int) -> str:
    return f"{Decimal(cents) / Decimal(100):.2f}"


def require_auth():
    uid = session.get('user_id')
    if not uid:
        return None
    return uid


# --- Routes ---

@app.before_request
def ensure_store():
    init_store_once()


@app.get('/')
def index():
    return render_template('index.html')


@app.get('/api/health')
def health():
    return jsonify(status='ok')


@app.post('/api/register')
def register():
    data = request.get_json(force=True)
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify(error='username and password required'), 400

    with store_lock:
        if username in users_by_username:
            return jsonify(error='username taken'), 409
        global next_user_id
        uid = next_user_id
        next_user_id += 1
        users_by_username[username] = {
            'id': uid,
            'username': username,
            'password_hash': generate_password_hash(password),
        }
        accounts_by_user_id[uid] = 0
        transactions_by_user_id[uid] = []

    session['user_id'] = uid
    session['username'] = username
    return jsonify(ok=True)


@app.post('/api/login')
def login():
    data = request.get_json(force=True)
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    with store_lock:
        user = users_by_username.get(username)

    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify(error='invalid credentials'), 401

    session['user_id'] = user['id']
    session['username'] = username
    return jsonify(ok=True)


@app.post('/api/logout')
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get('/api/me')
def me():
    uid = require_auth()
    if not uid:
        return jsonify(auth=False), 401

    with store_lock:
        # find username by scanning or from session
        username = session.get('username')
        balance_cents = accounts_by_user_id.get(uid, 0)
    return jsonify(username=username, balance=to_decimal_str(balance_cents))


@app.post('/api/deposit')
def deposit():
    uid = require_auth()
    if not uid:
        return jsonify(auth=False), 401
    data = request.get_json(force=True)
    amount_str = str(data.get('amount') or '0')
    cents = to_cents(amount_str)
    if cents <= 0:
        return jsonify(error='amount must be > 0'), 400

    with store_lock:
        accounts_by_user_id[uid] = accounts_by_user_id.get(uid, 0) + cents
        transactions_by_user_id.setdefault(uid, []).append({
            'type': 'deposit',
            'amount_cents': cents,
            'counterparty': None,
            'created_at': _now_str(),
        })
    return jsonify(ok=True)


@app.post('/api/withdraw')
def withdraw():
    uid = require_auth()
    if not uid:
        return jsonify(auth=False), 401
    data = request.get_json(force=True)
    cents = to_cents(str(data.get('amount') or '0'))
    if cents <= 0:
        return jsonify(error='amount must be > 0'), 400

    with store_lock:
        bal = accounts_by_user_id.get(uid, 0)
        if cents > bal:
            return jsonify(error='insufficient funds'), 400
        accounts_by_user_id[uid] = bal - cents
        transactions_by_user_id.setdefault(uid, []).append({
            'type': 'withdraw',
            'amount_cents': cents,
            'counterparty': None,
            'created_at': _now_str(),
        })
    return jsonify(ok=True)


@app.post('/api/transfer')
def transfer():
    uid = require_auth()
    if not uid:
        return jsonify(auth=False), 401
    data = request.get_json(force=True)
    to_username = (data.get('to_username') or '').strip()
    cents = to_cents(str(data.get('amount') or '0'))
    if not to_username or cents <= 0:
        return jsonify(error='to_username and positive amount required'), 400

    from_username = session.get('username')
    with store_lock:
        # lookup recipient
        rec = users_by_username.get(to_username)
        if not rec:
            return jsonify(error='recipient not found'), 404
        if rec['id'] == uid:
            return jsonify(error='cannot transfer to self'), 400

        bal = accounts_by_user_id.get(uid, 0)
        if cents > bal:
            return jsonify(error='insufficient funds'), 400

        # debit sender
        accounts_by_user_id[uid] = bal - cents
        transactions_by_user_id.setdefault(uid, []).append({
            'type': 'transfer_out',
            'amount_cents': cents,
            'counterparty': to_username,
            'created_at': _now_str(),
        })

        # credit recipient
        accounts_by_user_id[rec['id']] = accounts_by_user_id.get(rec['id'], 0) + cents
        transactions_by_user_id.setdefault(rec['id'], []).append({
            'type': 'transfer_in',
            'amount_cents': cents,
            'counterparty': from_username,
            'created_at': _now_str(),
        })
    return jsonify(ok=True)


@app.get('/api/transactions')
def list_transactions():
    uid = require_auth()
    if not uid:
        return jsonify(auth=False), 401
    try:
        limit = int(request.args.get('limit', '10'))
        limit = max(1, min(limit, 100))
    except ValueError:
        limit = 10

    with store_lock:
        rows = list(transactions_by_user_id.get(uid, []))
    # newest first
    rows = rows[::-1][:limit]
    items = [{
        'type': r['type'],
        'amount': to_decimal_str(r['amount_cents']),
        'counterparty': r.get('counterparty'),
        'created_at': r['created_at'],
    } for r in rows]
    return jsonify(items=items)


# static index assets (optional direct serve if needed)
@app.get('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.static_folder, filename)


def _now_str():
    import datetime as _dt
    return _dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')


if __name__ == '__main__':
    os.makedirs(app.static_folder, exist_ok=True)
    os.makedirs(app.template_folder, exist_ok=True)
    app.run(debug=True)
