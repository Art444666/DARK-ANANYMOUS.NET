from flask import Flask, render_template, render_template_string, session, request, redirect, url_for
from flask_socketio import SocketIO, join_room, emit, send
import random

# ---------- Инициализация ----------
app = Flask(__name__, template_folder='')
app.secret_key = "anonchat"
socketio = SocketIO(app)

# ---------- Глобальное состояние ----------
rooms = {}         # room_name → {'owner': username, 'private': bool, 'password': str}
participants = {}  # room_name → set of usernames
bans = {}          # room_name → set of banned usernames
sid_to_name = {}   # sid → username

users = {}         # ip → nickname

ADMIN_PASS = "1234"
blacklist_ips = set()
global_block = False
block_reason = "Глобальная блокировка"

# ---------- Встроенный шаблон регистрации ----------
REGISTER_TEMPLATE = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Регистрация</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: Arial, sans-serif; background:#0b0f14; color:#e6edf3;
           display:flex; align-items:center; justify-content:center; height:100vh; }
    .card { background:#111720; padding:24px; border-radius:12px; max-width:420px; width:92%; }
    h1 { margin:0 0 12px; font-size:22px; }
    label { display:block; margin:12px 0 6px; color:#9aa4ad; }
    input[type=text]{ width:100%; padding:10px; border-radius:8px; border:1px solid #30363d; background:#0d1117; color:#e6edf3; }
    button{ margin-top:12px; width:100%; padding:10px; border-radius:8px; border:none; background:linear-gradient(135deg,#238636,#2ea043); color:#fff; font-weight:bold; cursor:pointer;}
    .ip { color:#3da9fc; font-weight:bold; }
    .err { color:#ff7b72; margin-top:8px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Регистрация</h1>
    <p>Ваш IP: <span class="ip">{{ ip }}</span></p>
    <form method="post" action="{{ url_for('register') }}">
      <label>Введите ник</label>
      <input type="text" name="nickname" maxlength="24" placeholder="Например: Artem" required />
      {% if error %}<div class="err">{{ error }}</div>{% endif %}
      <button type="submit">Продолжить</button>
    </form>
  </div>
</body>
</html>
"""

# ---------- Роуты ----------
@app.route('/')
def index():
    ip = request.remote_addr or '0.0.0.0'

    # Блокировка (глобальная или по IP)
    if global_block or ip in blacklist_ips:
        return render_template('block.html', company="AnonChat", ip=ip, reason=block_reason)

    # Админ уже в сессии → панель
    if session.get('is_admin'):
        return render_template('admin.html', username="Админ")

    # Авторизация по IP
    if ip in users:
        username = users[ip]
        session['username'] = username
        session['room'] = None
        session['is_admin'] = False
        return render_template('chat.html', username=username, rooms=rooms)

    # Регистрация
    return render_template_string(REGISTER_TEMPLATE, ip=ip, error=None)


@app.route('/register', methods=['POST'])
def register():
    ip = request.remote_addr or '0.0.0.0'
    nickname = (request.form.get('nickname') or '').strip()

    # Валидация
    if len(nickname) < 2:
        return render_template_string(REGISTER_TEMPLATE, ip=ip, error="Ник слишком короткий.")
    if len(nickname) > 24:
        return render_template_string(REGISTER_TEMPLATE, ip=ip, error="Ник превышает 24 символа.")
    if nickname in users.values():
        return render_template_string(REGISTER_TEMPLATE, ip=ip, error="Ник уже используется.")

    # сохраняем ник
    users[ip] = nickname
    session['username'] = nickname
    session['room'] = None

    # админские права только для ника "Administrator"
    if nickname == "Administrator":
        session['is_admin'] = True
    else:
        session['is_admin'] = False

    return redirect(url_for('index'))
@app.route('/admin')
def admin_panel():
    ip = request.remote_addr or '0.0.0.0'
    if not session.get('is_admin'):
        return render_template('block.html', company="AnonChat", ip=ip, reason="Нет прав администратора")
    return render_template('admin.html', username=session.get('username', 'Админ'))

# ---------- Socket.IO события ----------
@socketio.on('connect')
def on_connect():
    if not session.get('username'):
        ip = request.remote_addr or '0.0.0.0'
        session['username'] = users.get(ip, f"Гость#{random.randint(1000,9999)}")
        session['room'] = None
        session.setdefault('is_admin', False)

    sid_to_name[request.sid] = session['username']
    emit('room_list', format_room_list())

@socketio.on('disconnect')
def on_disconnect():
    sid_to_name.pop(request.sid, None)

@socketio.on('admin_login')
def admin_login(data):
    password = (data or {}).get('password', '')
    if password == ADMIN_PASS:
        session['is_admin'] = True
        emit('admin_success', '✅ Вход в режим админа выполнен.')
        emit('redirect_admin', '/admin', to=request.sid)
    else:
        emit('admin_error', '❌ Неверный пароль.')

# --- Новый функционал для админа ---
@socketio.on('admin_ban_room')
def admin_ban_room(data):
    if not session.get('is_admin'):
        emit('admin_error', '⚠️ Нет прав администратора.')
        return

    room = (data or {}).get('room', '').strip()
    if not room or room not in rooms:
        emit('admin_error', '❌ Комната не найдена.')
        return

    participants.pop(room, None)
    bans.pop(room, None)
    rooms.pop(room, None)

    emit('admin_success', f'⛔ Комната "{room}" удалена администратором.', broadcast=True)
    emit('room_list', format_room_list(), broadcast=True)

@socketio.on('admin_user_list')
def admin_user_list():
    if not session.get('is_admin'):
        emit('admin_error', '⚠️ Нет прав администратора.')
        return

    user_list = [{"ip": ip, "nickname": nick} for ip, nick in users.items()]
    emit('admin_user_list', user_list, to=request.sid)
@socketio.on('get_all_users')
def get_all_users():
    if not session.get('is_admin'):
        emit('admin_error', '⚠️ Нет прав администратора.')
        return
    # users = {ip: nickname}
    data = [{"ip": ip, "nickname": nick} for ip, nick in users.items()]
    emit('all_users', data, to=request.sid)
# ---------- Утилиты ----------
def update_userlist(room):
    users_in_room = list(participants.get(room, []))
    owner = rooms.get(room, {}).get('owner', '')
    emit('userlist', {'users': users_in_room, 'owner': owner}, to=room)

def format_room_list():
    return [
        f"{name} {'[приват]' if info.get('private') else ''}"
        for name, info in rooms.items()
    ]

# ---------- Запуск ----------
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)










