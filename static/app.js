async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || 'GET',
    headers: { 'Content-Type': 'application/json' },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch (e) { data = { raw: text }; }
  if (!res.ok) {
    throw new Error((data && data.error) || 'Request failed');
  }
  return data;
}

function qs(id) { return document.getElementById(id); }
function set(el, text) { el.textContent = text; }
function show(id, v) { qs(id).classList.toggle('hidden', !v); }
function msg(id, text) { set(qs(id), text || ''); }

async function refresh() {
  try {
    const me = await api('/api/me');
    set(qs('userName'), me.username);
    set(qs('balance'), me.balance);
    show('dashboard', true);
    show('welcome', true);
    show('loginBlock', false);
    await loadTx();
  } catch (_) {
    show('dashboard', false);
    show('welcome', false);
    show('loginBlock', true);
  }
}

async function loadTx() {
  const data = await api('/api/transactions?limit=10');
  const ul = qs('txList');
  ul.innerHTML = '';
  for (const it of data.items) {
    const li = document.createElement('li');
    const dir = it.type.includes('out') || it.type === 'withdraw' ? '-' : '+';
    li.textContent = `[${it.created_at}] ${it.type} ${dir}$${it.amount} ${it.counterparty ? ' (' + it.counterparty + ')' : ''}`;
    ul.appendChild(li);
  }
}

window.addEventListener('DOMContentLoaded', () => {
  qs('loginBtn').onclick = async () => {
    try {
      await api('/api/login', { method: 'POST', body: { username: qs('username').value, password: qs('password').value } });
      msg('authMsg', '');
      await refresh();
    } catch (e) { msg('authMsg', e.message); }
  };
  
  qs('registerBtn').onclick = async () => {
    try {
      await api('/api/register', { method: 'POST', body: { username: qs('username').value, password: qs('password').value } });
      msg('authMsg', '');
      await refresh();
    } catch (e) { msg('authMsg', e.message); }
  };

  qs('logoutBtn').onclick = async () => {
    await api('/api/logout', { method: 'POST' });
    await refresh();
  };

  qs('depositBtn').onclick = async () => {
    try {
      const amount = qs('amount').value;
      await api('/api/deposit', { method: 'POST', body: { amount } });
      msg('dashMsg', 'Deposit successful');
      await refresh();
    } catch (e) { msg('dashMsg', e.message); }
  };

  qs('withdrawBtn').onclick = async () => {
    try {
      const amount = qs('amount').value;
      await api('/api/withdraw', { method: 'POST', body: { amount } });
      msg('dashMsg', 'Withdraw successful');
      await refresh();
    } catch (e) { msg('dashMsg', e.message); }
  };

  qs('transferBtn').onclick = async () => {
    try {
      const to_username = qs('toUser').value;
      const amount = qs('transferAmount').value;
      await api('/api/transfer', { method: 'POST', body: { to_username, amount } });
      msg('dashMsg', 'Transfer successful');
      await refresh();
    } catch (e) { msg('dashMsg', e.message); }
  };

  refresh();
});
