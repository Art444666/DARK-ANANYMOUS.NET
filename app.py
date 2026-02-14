from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room, send
import random, time
import os

app = Flask(__name__, template_folder='')
app.config['SECRET_KEY'] = 'tg_secret_key_94488'
# ИЗЮМИНКА: Увеличиваем буфер для передачи ФОТО (10МБ)
socketio = SocketIO(app, max_http_buffer_size=10 * 1024 * 1024)

# Хранилище данных
users = {}        # sid: {username, room, avatar}
rooms = {}        # name: {owner, private, password, created_at}
participants = {} # name: set(usernames)
bans = {}         # name: set(usernames)

def format_room_list():
    # Сортируем: новые комнаты всегда сверху
    sorted_rooms = sorted(rooms.items(), key=lambda x: x[1].get('created_at', 0), reverse=True)
    return [f"{name} {'[приват]' if info.get('private') else ''}".strip() for name, info in sorted_rooms]

def update_userlist(room):
    if room in participants:
        users_in_room = list(participants[room])
        owner = rooms.get(room, {}).get('owner', '')
        emit('userlist', {'users': users_info_get(room), 'owner': owner, 'count': len(users_in_room)}, to=room)

def users_info_get(room):
    # Собираем данные участников для аватарок
    return [data['username'] for sid, data in users.items() if data.get('room') == room]

@app.route('/')
def index():
    if not session.get('username'):
        return redirect(url_for('register'))
    return render_template('index.html', username=session['username'])

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nick = request.form.get('nickname', '').strip()
        if 2 <= len(nick) <= 20:
            session['username'] = nick
            return redirect(url_for('index'))
    return '''<form method="post" style="background:#17212b;color:white;height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;font-family:sans-serif;">
              <h2>Введите ник для чата</h2>
              <input name="nickname" placeholder="Никнейм" style="padding:10px;border-radius:8px;border:none;">
              <button type="submit" style="margin-top:10px;padding:10px 20px;background:#5288c1;color:white;border:none;border-radius:8px;cursor:pointer;">Войти</button>
              </form>'''

# --- SOCKET EVENTS ---

@socketio.on('connect')
def on_connect():
    sid = request.sid
    username = session.get('username', f"User_{random.randint(100,999)}")
    users[sid] = {'username': username, 'room': None}
    emit('room_list', format_room_list())

@socketio.on('create_room')
def on_create(data):
    name = data.get('room', '').strip()
    pw = data.get('password', '').strip()
    if name and name not in rooms:
        rooms[name] = {'owner': session['username'], 'private': bool(pw), 'password': pw, 'created_at': time.time()}
        participants[name] = set()
        bans[name] = set()
        # ГЛАВНОЕ: Рассылаем всем обновленный список сразу!
        emit('room_list', format_room_list(), broadcast=True)
        # Авто-вход создателя
        on_join({'room': name, 'password': pw})
    else:
        emit('room_error', 'Комната уже есть или имя пустое')

@socketio.on('join_room')
def on_join(data):
    room = data.get('room')
    pw = data.get('password')
    username = session['username']
    
    if room in rooms:
        if rooms[room]['private'] and rooms[room]['password'] != pw:
            emit('room_error', 'Неверный пароль')
            return
        
        # Выход из старой
        old = session.get('room')
        if old: 
            leave_room(old)
            participants[old].discard(username)
            update_userlist(old)

        join_room(room)
        session['room'] = room
        users[request.sid]['room'] = room
        participants[room].add(username)
        
        emit('room_joined', room)
        update_userlist(room)
        emit('message', f"📥 {username} вошел в чат", to=room)

@socketio.on('message')
def handle_msg(msg):
    room = session.get('room')
    username = session['username']
    if room:
        if str(msg).startswith("IMAGE_DATA:"):
            emit('message', f"{username}:{msg}", to=room)
        else:
            emit('message', f"{username}: {msg}", to=room)

@socketio.on('disconnect')
def on_disc():
    sid = request.sid
    if sid in users:
        room = users[sid].get('room')
        if room:
            participants[room].discard(users[sid]['username'])
            update_userlist(room)
        del users[sid]

if __name__ == '__main__':
    # Render передает порт в переменную окружения PORT
    port = int(os.environ.get('PORT', 5000))
    
    # КРИТИЧЕСКИ ВАЖНО: host='0.0.0.0'
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
















