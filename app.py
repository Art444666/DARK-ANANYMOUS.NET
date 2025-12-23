from flask import Flask, render_template, render_template_string, session, request, redirect, url_for
from flask_socketio import SocketIO
import random

app = Flask(__name__, template_folder='')
app.secret_key = "anonchat"
socketio = SocketIO(app)

# ---------- Глобальные структуры ----------
rooms = {}         # room_name → {'owner': username, 'private': bool, 'password': str}
participants = {}  # room_name → set of usernames
bans = {}          # room_name → set of banned usernames
sid_to_name = {}   # sid → username

users = {}         # ip → nickname

ADMIN_PASS = "1234"
blacklist_ips = set()
global_block = False
block_reason = "Глобальная блокировка"

# ---------- Шаблон регистрации ----------
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

# ---------- Маршруты ----------
@app.route('/')
def index():
    ip = request.remote_addr

    # Проверка блокировок
    if global_block or ip in blacklist_ips:
        return render_template('block.html', company="AnonChat", ip=ip, reason=block_reason)

    # Если админ уже вошёл
    if session.get('is_admin'):
        return render_template('admin.html', username="Админ")

    # Если IP зарегистрирован → подтягиваем ник
    if ip in users:
        username = users[ip]
        session['username'] = username
        session['room'] = None
        session['is_admin'] = False
        return render_template('chat.html', username=username, rooms=rooms)

    # Иначе → регистрация
    return render_template_string(REGISTER_TEMPLATE, ip=ip, error=None)

@app.route('/register', methods=['POST'])
def register():
    ip = request.remote_addr
    nickname = request.form.get('nickname', '').strip()

    # Валидация
    if not nickname or len(nickname) < 2:
        return render_template_string(REGISTER_TEMPLATE, ip=ip, error="Ник слишком короткий.")
    if len(nickname) > 24:
        return render_template_string(REGISTER_TEMPLATE, ip=ip, error="Ник превышает 24 символа.")
    if nickname in users.values():
        return render_template_string(REGISTER_TEMPLATE, ip=ip, error="Ник уже используется.")

    users[ip] = nickname
    session['username'] = nickname
    session['room'] = None
    session['is_admin'] = False
    return redirect(url_for('index'))

@app.route('/admin')
def admin_panel():
    ip = request.remote_addr
    if not session.get('is_admin'):
        return render_template('block.html', company="AnonChat", ip=ip, reason="Нет прав администратора")
    return render_template('admin.html', username="Админ")
    # ---------- Socket.IO события ----------

@socketio.on('connect')
def on_connect():
    # если у сессии нет ника — назначим гостя
    if not session.get('username'):
        ip = request.remote_addr
        session['username'] = users.get(ip, f"Гость#{random.randint(1000,9999)}")
    sid_to_name[request.sid] = session.get('username')

    # ⚡️ сразу отправляем список комнат при подключении
    emit('room_list', format_room_list())

@socketio.on('admin_login')
def admin_login(data):
    password = data.get('password', '')
    if password == ADMIN_PASS:
        session['is_admin'] = True
        emit('admin_success', '✅ Вход в режим админа выполнен.')
        # редирект на панель
        emit('redirect_admin', '/admin', to=request.sid)
    else:
        emit('admin_error', '❌ Неверный пароль.')

@socketio.on('admin_ban')
def admin_ban(data):
    if not session.get('is_admin'):
        emit('admin_error', '⚠️ Нет прав администратора.')
        return
    target_ip = data.get('ip')
    reason = data.get('reason', 'Нарушение правил')
    if target_ip:
        blacklist_ips.add(target_ip)
        emit('admin_success', f'⛔ IP {target_ip} добавлен в чёрный список.')
    else:
        emit('admin_error', '❌ Не указан IP.')

@socketio.on('admin_global_block')
def admin_global_block_evt(data):
    if not session.get('is_admin'):
        emit('admin_error', '⚠️ Нет прав администратора.')
        return
    global global_block, block_reason
    global_block = data.get('enabled', False)
    block_reason = data.get('reason', 'Глобальная блокировка')
    if global_block:
        emit('admin_success', '🌐 Включена глобальная блокировка сайта.')
    else:
        emit('admin_success', '🌐 Глобальная блокировка отключена.')

@socketio.on('create_room')
def create_room(data):
    room = data.get('room', '').strip()
    password = data.get('password', '').strip()
    private = bool(password)
    username = session.get('username')

    if not room:
        emit('room_error', '❌ Укажите название комнаты.')
        return
    if room in rooms:
        emit('room_error', '❌ Комната уже существует.')
        return

    rooms[room] = {
        'owner': username,
        'private': private,
        'password': password
    }
    participants[room] = set()
    bans[room] = set()
    emit('room_list', format_room_list(), broadcast=True)

@socketio.on('join_room')
def join_room_event(data):
    room = data.get('room', '').strip()
    password = data.get('password', '').strip()
    username = session.get('username')

    if room not in rooms:
        emit('room_error', '❌ Комната не найдена.')
        return
    if rooms[room]['private'] and rooms[room]['password'] != password:
        emit('room_error', '🔐 Неверный пароль.')
        return

    session['room'] = room
    join_room(room)
    participants[room].add(username)
    send(f"🚪 {username} вошёл в комнату {room}.", to=room)
    update_userlist(room)
    emit('room_joined', room)

@socketio.on('message')
def handle_message(msg):
    username = session.get('username')
    room = session.get('room')

    if not room:
        emit('room_error', '⚠️ Вы не в комнате.')
        return

    if username in bans.get(room, set()):
        send("⛔ Вы забанены в этой комнате.", to=request.sid)
        return

    if isinstance(msg, str) and msg.startswith("/ban "):
        target = msg.split("/ban ", 1)[1].strip()
        if rooms[room]['owner'] == username:
            bans[room].add(target)
            send(f"🔒 {target} забанен владельцем {username}.", to=room)
        else:
            send("⚠️ Только владелец может банить.", to=request.sid)

    elif isinstance(msg, str) and msg.startswith("/unban "):
        target = msg.split("/unban ", 1)[1].strip()
        if rooms[room]['owner'] == username:
            bans[room].discard(target)
            send(f"🔓 {target} разбанен владельцем {username}.", to=room)
        else:
            send("⚠️ Только владелец может разбанивать.", to=request.sid)

    else:
        send(f"{username}: {msg}", to=room)

    update_userlist(room)

# ---------- Утилиты ----------
def update_userlist(room):
    userlist = list(participants.get(room, []))
    owner = rooms[room]['owner']
    emit('userlist', {'users': userlist, 'owner': owner}, to=room)

def format_room_list():
    return [
        f"{name} {'[приват]' if info['private'] else ''}"
        for name, info in rooms.items()
    ]

# ---------- Запуск ----------
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)





