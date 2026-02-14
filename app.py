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
        return render_template('admin.html', username=session.get('username', 'Админ'))

    # Авторизация по IP
    if ip in users:
        username = users[ip]
        session['username'] = username
        session['room'] = None
        session['is_admin'] = (username == "Administrator")
        return render_template('chat.html', username=username, rooms=rooms)

    # Регистрация
    return render_template_string(REGISTER_TEMPLATE, ip=ip, error=None)

@app.route('/register', methods=['POST'])
def register():
    # Получаем IP и чистим ник
    ip = request.remote_addr or '0.0.0.0'
    nickname = (request.form.get('nickname') or '').strip()

    # 1. Валидация (стандартная)
    if len(nickname) < 2:
        return render_template_string(REGISTER_TEMPLATE, ip=ip, error="Ник слишком короткий.")
    if len(nickname) > 24:
        return render_template_string(REGISTER_TEMPLATE, ip=ip, error="Ник превышает 24 символа.")
    
    # Проверка на занятость ника (среди активных сессий)
    if any(u.get('username') == nickname for u in users.values()):
        return render_template_string(REGISTER_TEMPLATE, ip=ip, error="Ник уже занят.")

    # 2. Инициализация пользователя в стиле Telegram
    # Мы сохраняем не просто ник, а объект со статусом
    session['username'] = nickname
    session['room'] = None
    session['is_admin'] = (nickname == "Administrator")
    
    # Добавляем в глобальный словарь (sid будет добавлен позже при коннекте)
    # Но для отслеживания по IP можно оставить запись
    users[ip] = {
        'username': nickname,
        'room': None,
        'is_online': True
    }

    # 3. Изюминка: При регистрации перенаправляем на главную с красивым лоадером
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
    sid = request.sid
    # 1. Проверяем ник (изюминка: если ника нет, даем красивый "Аноним")
    if not session.get('username'):
        ip = request.remote_addr or '0.0.0.0'
        # Ищем ник в словаре по IP, если нет — генерим Anonymous#ID
        nickname = users.get(ip, {}).get('username') if isinstance(users.get(ip), dict) else f"User_{random.randint(100,999)}"
        session['username'] = nickname
        session['room'] = None
        session['is_admin'] = (nickname == "Administrator")

    # 2. Связываем SID с данными пользователя (Telegram Style)
    username = session['username']
    sid_to_name[sid] = username
    
    # Добавляем расширенные данные (для аватарок и онлайна)
    users[sid] = {
        'username': username,
        'room': session.get('room'),
        'status': 'online',
        'is_admin': session.get('is_admin', False)
    }

    # 3. Сразу отдаем список комнат (чтобы они появились мгновенно)
    emit('room_list', format_room_list())
    
    # Если юзер переподключился и уже был в комнате — обновляем список юзеров там
    if session.get('room'):
        room = session['room']
        join_room(room)
        # Отправляем обновленный список участников (счетчик "в сети")
        emit('userlist', get_userlist_data(room), to=room)

@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    if sid in sid_to_name:
        username = sid_to_name.get(sid)
        room = session.get('room')
        
        # 1. Убираем из активных соединений
        sid_to_name.pop(sid, None)
        if sid in users:
            del users[sid]
            
        # 2. Изюминка: Если юзер был в комнате, уведомляем остальных (счетчик уменьшится)
        if room:
            # Отправляем обновленный userlist, чтобы "в сети" обновилось у всех
            emit('userlist', get_userlist_data(room), to=room)
            # Можно отправить системное сообщение: "Юзер покинул чат"
            # send(f"ℹ️ {username} вышел из чата", to=room)


@socketio.on('admin_login')
def admin_login(data):
    password = (data or {}).get('password', '')
    if password == ADMIN_PASS:
        session['is_admin'] = True
        emit('admin_success', '✅ Вход в режим админа выполнен.')
        emit('redirect_admin', '/admin', to=request.sid)
    else:
        emit('admin_error', '❌ Неверный пароль.')

# --- Админ: бан IP ---
@socketio.on('admin_ban')
def admin_ban(data):
    if not session.get('is_admin'):
        emit('admin_error', '⚠️ Нет прав администратора.')
        return

    target_ip = (data or {}).get('ip', '').strip()
    reason = (data or {}).get('reason', 'Нарушение правил')

    if not target_ip:
        emit('admin_error', '❌ Не указан IP.')
        return

    blacklist_ips.add(target_ip)
    emit('admin_success', f'⛔ IP {target_ip} добавлен в чёрный список.')

# --- Админ: глобальная блокировка сайта ---
@socketio.on('admin_global_block')
def admin_global_block_evt(data):
    if not session.get('is_admin'):
        emit('admin_error', '⚠️ Нет прав администратора.')
        return

    enabled = bool((data or {}).get('enabled', False))
    reason = (data or {}).get('reason', 'Глобальная блокировка')

    global global_block, block_reason
    global_block = enabled
    block_reason = reason

    emit('admin_success', '🌐 Глобальная блокировка включена.' if enabled else '🌐 Глобальная блокировка отключена.')

# --- Админ: удалить комнату ---
@socketio.on('admin_ban_room')
def admin_ban_room(data):
    if not session.get('is_admin'):
        emit('admin_error', '⚠️ Нет прав администратора.')
        return

    room = (data or {}).get('room', '').strip()
    if not room or room not in rooms:
        emit('admin_error', '❌ Комната не найдена.')
        return

    # удаляем комнату и связанные структуры
    participants.pop(room, None)
    bans.pop(room, None)
    rooms.pop(room, None)

    emit('admin_success', f'⛔ Комната "{room}" удалена администратором.', broadcast=True)
    emit('room_list', format_room_list(), broadcast=True)

# --- Админ: получить список всех пользователей с IP ---
@socketio.on('get_all_users')
def get_all_users():
    if not session.get('is_admin'):
        emit('admin_error', '⚠️ Нет прав администратора.')
        return
    data = [{"ip": ip, "nickname": nick} for ip, nick in users.items()]
    emit('all_users', data, to=request.sid)

# --- Пользовательские события: комнаты и сообщения ---
@socketio.on('create_room')
def create_room(data):
    room_name = (data or {}).get('room', '').strip()
    password = (data or {}).get('password', '').strip()
    username = session.get('username', 'Anonymous')
    sid = request.sid

    # 1. Валидация (Telegram Style)
    if not room_name or len(room_name) > 30:
        emit('room_error', '❌ Название должно быть от 1 до 30 символов.')
        return
    
    if room_name in rooms:
        emit('room_error', '❌ Такая комната уже создана.')
        return

    # 2. Создание комнаты с меткой времени для сортировки
    rooms[room_name] = {
        'owner': username,
        'private': bool(password),
        'password': password,
        'created_at': time.time() 
    }
    
    participants[room_name] = set()
    bans[room_name] = set()

    # 3. Мгновенное появление у всех в списке (исправляет твой баг)
    emit('room_list', format_room_list(), broadcast=True)

    # 4. Авто-переход создателя в чат
    old_room = session.get('room')
    if old_room:
        leave_room(old_room)
        if old_room in participants:
            participants[old_room].discard(username)
        # Уведомляем старую комнату, что мы ушли (счетчик онлайна)
        update_userlist(old_room)
    
    join_room(room_name)
    session['room'] = room_name
    participants[room_name].add(username)
    
    # Обновляем данные текущего сеанса в глобальном словаре
    if sid in users:
        users[sid]['room'] = room_name

    # 5. Сигналы фронтенду (открываем окно чата)
    emit('room_joined', room_name)
    
    # Отправляем инфо об участниках (с аватарами и статусом короны 👑)
    update_userlist(room_name)
    
    # Изюминка: приветственное системное сообщение
    emit('message', f"✨ Комната '{room_name}' создана. Добро пожаловать!", to=room_name)



@socketio.on('join_room')
def on_join_room(data):
    username = session.get('username', 'Anonymous')
    room_name = (data or {}).get('room', '').strip()
    password = (data or {}).get('password', '').strip()
    sid = request.sid

    # 1. Проверки безопасности
    if room_name not in rooms:
        emit('room_error', '❌ Комната не найдена.')
        return

    if username in bans.get(room_name, set()):
        emit('room_error', '🚫 Вы забанены в этой комнате.')
        return

    # 2. Проверка пароля (если приватная)
    room_info = rooms[room_name]
    if room_info.get('private') and room_info.get('password') != password:
        emit('room_error', '🔑 Неверный пароль.')
        return

    # 3. Логика переключения комнат (Telegram Style)
    old_room = session.get('room')
    if old_room:
        leave_room(old_room)
        if old_room in participants:
            participants[old_room].discard(username)
        update_userlist(old_room) # Обновляем онлайн в старой комнате

    # Входим в новую
    join_room(room_name)
    session['room'] = room_name
    participants[room_name].add(username)
    
    # Обновляем глобальный статус юзера для аватарок
    if sid in users:
        users[sid]['room'] = room_name

    # 4. Ответ фронтенду
    emit('room_joined', room_name) # Это «включает» чат и поле ввода
    update_userlist(room_name)     # Это обновляет «в сети: X»
    
    # Системное уведомление о входе
    emit('message', f"📥 {username} вошел в чат", to=room_name)

@socketio.on('message')
def handle_message(msg):
    username = session.get('username', 'Гость')
    room = session.get('room')
    sid = request.sid

    if not room:
        emit('room_error', '⚠️ Вы не в комнате.')
        return

    if username in bans.get(room, set()):
        send("⛔ Вы забанены в этой комнате.", to=sid)
        return

    if not msg or not str(msg).strip():
        return

    # 1. ОБРАБОТКА КОМАНД (ТОЛЬКО ДЛЯ ТЕКСТА)
    if isinstance(msg, str) and not msg.startswith("IMAGE_DATA:"):
        if msg.startswith("/ban "):
            target = msg.split("/ban ", 1)[1].strip()
            if rooms.get(room, {}).get('owner') == username:
                bans[room].add(target)
                # Красивое системное сообщение в стиле ТГ
                emit('message', f"🔒 {target} забанен владельцем {username}.", to=room)
                update_userlist(room) # Обновляем список, чтобы пометить забаненного
            else:
                send("⚠️ Только владелец может банить.", to=sid)
            return # Выходим, чтобы не дублировать команду как сообщение

        elif msg.startswith("/unban "):
            target = msg.split("/unban ", 1)[1].strip()
            if rooms.get(room, {}).get('owner') == username:
                bans[room].discard(target)
                emit('message', f"🔓 {target} разбанен владельцем {username}.", to=room)
                update_userlist(room)
            else:
                send("⚠️ Только владелец может разбанивать.", to=sid)
            return

    # 2. ИЗЮМИНКА: РАССЫЛКА КОНТЕНТА (ФОТО ИЛИ ТЕКСТ)
    if str(msg).startswith("IMAGE_DATA:"):
        # Рассылаем фото с автором
        emit('message', f"{username}:{msg}", to=room)
    else:
        # Рассылаем обычный текст
        # Используем emit вместо send для единообразия формата "Имя: Сообщение"
        emit('message', f"{username}: {msg}", to=room)

    # 3. Обновляем онлайн-статус (микро-изюминка: подтверждаем активность)
    # Это заставит заголовок чата "в сети" обновиться, если кто-то вошел/вышел
    update_userlist(room)


# ---------- Утилиты ----------
def update_userlist(room):
    """
    Изюминка: Сервер теперь отдает не только список имен, 
    но и общее количество (для заголовка в ТГ)
    """
    users_in_room = list(participants.get(room, []))
    owner = rooms.get(room, {}).get('owner', '')
    
    # Отправляем данные, которые наш JS подхватит для обновления "в сети: X"
    emit('userlist', {
        'users': users_in_room, 
        'owner': owner,
        'online_count': len(users_in_room)
    }, to=room)

def format_room_list():
    """
    Изюминка: Сортируем комнаты так, чтобы новые/активные были вверху,
    и передаем данные в формате, который легко парсить фронтенду.
    """
    # Сортируем по времени создания (если оно есть в rooms[name]['created_at'])
    sorted_rooms = sorted(
        rooms.items(), 
        key=lambda x: x[1].get('created_at', 0), 
        reverse=True
    )

    formatted = []
    for name, info in sorted_rooms:
        suffix = " [приват]" if info.get('private') else ""
        # Мы возвращаем строку, как ожидает твой текущий JS: "Имя [приват]"
        formatted.append(f"{name}{suffix}")
    
    return formatted

@socketio.on('update_profile')
def on_update_profile(data):
    old_nickname = session.get('username')
    new_nickname = (data.get('nickname') or '').strip()
    new_avatar = data.get('avatar') # Base64 строка изображения
    room = session.get('room')

    # 1. Валидация ника
    if new_nickname and 2 <= len(new_nickname) <= 24:
        # Проверяем, не занят ли ник кем-то другим
        if not any(u.get('username') == new_nickname for u in users.values() if u.get('username') != old_nickname):
            session['username'] = new_nickname
            if request.sid in users:
                users[request.sid]['username'] = new_nickname
            
            # Уведомляем комнату о смене ника (системное сообщение)
            if room:
                emit('message', f"👤 {old_nickname} теперь известен как {new_nickname}", to=room)
                update_userlist(room)

    # 2. Обновление аватара
    if new_avatar:
        if request.sid in users:
            users[request.sid]['avatar'] = new_avatar
        # Рассылаем обновленный список юзеров с новыми авами
        if room:
            update_userlist(room)

    emit('admin_success', "Профиль обновлен!") # Уведомление в шторку




# ---------- Запуск ----------
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)












