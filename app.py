from flask import Flask, render_template, session, request
from flask_socketio import SocketIO, join_room, leave_room, send, emit
import random

app = Flask(__name__, template_folder='')
app.secret_key = "anonchat"
socketio = SocketIO(app)

rooms = {}         # room_name → {'owner': username, 'private': bool, 'password': str}
participants = {}  # room_name → set of usernames
bans = {}          # room_name → set of banned usernames
sid_to_name = {}   # sid → username

@app.route('/')
def index():
    username = f"Гость#{random.randint(1000,9999)}"
    session['username'] = username
    session['room'] = None
    return render_template('chat.html', username=username, rooms=rooms)

@socketio.on('connect')
def on_connect():
    sid_to_name[request.sid] = session['username']

@socketio.on('create_room')
def create_room(data):
    room = data['room'].strip()
    password = data.get('password', '').strip()
    private = bool(password)

    if room in rooms:
        emit('room_error', '❌ Комната уже существует.')
        return

    rooms[room] = {
        'owner': session['username'],
        'private': private,
        'password': password
    }
    participants[room] = set()
    bans[room] = set()
    emit('room_list', format_room_list(), broadcast=True)

@socketio.on('join_room')
def join_room_event(data):
    room = data['room'].strip()
    password = data.get('password', '').strip()
    username = session['username']

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

    if username in bans[room]:
        send("⛔ Вы забанены в этой комнате.", to=request.sid)
        return

    if msg.startswith("/ban "):
        target = msg.split("/ban ")[1].strip()
        if rooms[room]['owner'] == username:
            bans[room].add(target)
            send(f"🔒 {target} забанен владельцем {username}.", to=room)
        else:
            send("⚠️ Только владелец может банить.", to=request.sid)

    elif msg.startswith("/unban "):
        target = msg.split("/unban ")[1].strip()
        if rooms[room]['owner'] == username:
            bans[room].discard(target)
            send(f"🔓 {target} разбанен владельцем {username}.", to=room)
        else:
            send("⚠️ Только владелец может разбанивать.", to=request.sid)

    else:
        send(f"{username}: {msg}", to=room)

    update_userlist(room)

def update_userlist(room):
    userlist = list(participants.get(room, []))
    owner = rooms[room]['owner']
    emit('userlist', {'users': userlist, 'owner': owner}, to=room)

def format_room_list():
    return [
        f"{name} {'[приват]' if info['private'] else ''}"
        for name, info in rooms.items()
    ]

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)



