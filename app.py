import os, time
from flask import Flask, session, request, redirect, jsonify, render_template_string
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tg_friends_94488'
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=20 * 1024 * 1024)

# Глобальная база данных в памяти
rooms_db = {} 
all_users = {} # { username: sid } для мгновенных уведомлений
notifications = {} # { username: [list of invites] }

HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Telegram Friends Edition</title>
    <script src="https://cdn.socket.io"></script>
    <style>
        :root { --bg: #0e1621; --side: #17212b; --acc: #5288c1; --msg-in: #182533; --msg-out: #2b5278; --text: #f5f5f5; }
        body, html { height: 100%; margin: 0; font-family: sans-serif; background: var(--bg); color: var(--text); overflow: hidden; }
        .app-wrap { display: flex; height: 100vh; width: 100vw; }

        /* САЙДБАР */
        .sidebar { width: 320px; background: var(--side); border-right: 1px solid #080a0d; display: flex; flex-direction: column; flex-shrink: 0; }
        .rooms-list { flex: 1; overflow-y: auto; }
        .room-item { padding: 12px 15px; border-bottom: 1px solid #0e1621; cursor: pointer; display: flex; align-items: center; gap: 12px; }
        .room-item.active { background: var(--acc); }
        .room-item.bot { background: #212d3b; border-left: 4px solid var(--acc); }
        .avatar { width: 45px; height: 45px; border-radius: 50%; background: var(--acc); display: flex; align-items: center; justify-content: center; font-weight: bold; }

        /* ЧАТ */
        .chat-main { flex: 1; display: flex; flex-direction: column; background: #0e1621; }
        .chat-header { background: var(--side); padding: 15px 20px; font-weight: bold; border-bottom: 1px solid #000; display: flex; justify-content: space-between; }
        #messages { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 10px; }
        .msg { max-width: 75%; padding: 10px; border-radius: 12px; }
        .mine { align-self: flex-end; background: var(--msg-out); }
        .other { align-self: flex-start; background: var(--msg-in); }
        .invite-card { background: #242f3d; padding: 10px; border-radius: 10px; border: 1px solid var(--acc); margin-top: 5px; }

        .input-bar { padding: 15px; background: var(--side); display: flex; gap: 10px; }
        .inp { flex: 1; background: #242f3d; border: none; padding: 10px; border-radius: 20px; color: white; outline: none; }
        .btn { background: none; border: none; color: var(--acc); cursor: pointer; font-weight: bold; font-size: 18px; }
    </style>
</head>
<body>

<div class="app-wrap">
    <div class="sidebar">
        <div style="padding:15px; font-weight:bold; color:var(--acc)">Telegram Pro</div>
        
        <div class="rooms-list">
            <!-- БОТ-УВЕДОМЛЕНИЯ -->
            <div class="room-item bot {{ 'active' if current_room == 'BOT' else '' }}" onclick="location.href='/?room=BOT'">
                <div class="avatar">🤖</div>
                <div><b>Уведомления</b><br><small id="notif-count">0 новых</small></div>
            </div>

            <div style="padding: 10px; font-size: 11px; color: gray; text-transform: uppercase;">Беседы</div>
            {% for r_name, r_info in rooms.items() %}
            <div class="room-item {{ 'active' if r_name == current_room else '' }}" onclick="enterRoom('{{ r_name }}', {{ 'true' if r_info.password else 'false' }})">
                <div class="avatar">{{ r_name[:1].upper() }}</div>
                <div><b>{{ r_name }} {{ '🔐' if r_info.password else '' }}</b></div>
            </div>
            {% endfor %}
        </div>
        <button onclick="createRoom()" style="margin:10px; padding:10px; background:var(--acc); border:none; color:white; border-radius:8px; cursor:pointer;">+ Создать беседу</button>
    </div>

    <div class="chat-main">
        {% if current_room %}
        <div class="chat-header">
            <span>{{ '🤖 Бот-помощник' if current_room == 'BOT' else current_room }}</span>
            {% if current_room != 'BOT' %}
            <button onclick="inviteFriend()" style="background:var(--acc); border:none; color:white; padding:5px 10px; border-radius:5px; cursor:pointer; font-size:12px;">Пригласить +</button>
            {% endif %}
        </div>
        <div id="messages">
            {% if current_room == 'BOT' %}
                <div class="msg other">Привет! Я буду присылать сюда приглашения в друзья и беседы.</div>
                {% for inv in my_notifs %}
                <div class="msg other">
                    <div class="invite-card">
                        🚀 <b>{{ inv.from }}</b> приглашает тебя в беседу <b>{{ inv.room }}</b>
                        <br><br>
                        <button onclick="enterRoom('{{ inv.room }}', false, '{{ inv.pass }}')" style="background:var(--acc); border:none; color:white; padding:5px; border-radius:5px; cursor:pointer;">Войти</button>
                    </div>
                </div>
                {% endfor %}
            {% endif %}
        </div>
        {% if current_room != 'BOT' %}
        <div class="input-bar">
            <input type="text" id="msgInp" class="inp" placeholder="Написать..." onkeypress="if(event.key==='Enter') send()">
            <button onclick="send()" class="btn">➤</button>
        </div>
        {% endif %}
        {% else %}
        <div style="flex:1; display:flex; align-items:center; justify-content:center; color:gray;">Выберите чат или проверьте уведомления</div>
        {% endif %}
    </div>
</div>

<script>
    const socket = io();
    const myName = "{{ username }}";
    const room = "{{ current_room }}";

    if(room && room !== 'BOT') {
        socket.emit('join_room_fixed', {room: room});
    }

    function enterRoom(name, isPrivate, pass = "") {
        let p = isPrivate ? prompt("Пароль:") : pass;
        if(isPrivate && p === null) return;
        window.location.href = "/?room=" + encodeURIComponent(name) + "&pass=" + encodeURIComponent(p);
    }

    async function inviteFriend() {
        const target = prompt("Введите ник пользователя для приглашения:");
        if(!target) return;
        const res = await fetch('/invite', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({target: target, room: room})
        });
        const data = await res.json();
        alert(data.msg);
    }

    async function createRoom() {
        const n = prompt("Название беседы:");
        if(!n) return;
        const p = prompt("Пароль (пусто если не нужен):");
        await fetch('/create_room', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: n, password: p})
        });
        window.location.href = "/?room=" + n + "&pass=" + p;
    }

    function send() {
        const i = document.getElementById("msgInp");
        if(i.value.trim() && room) {
            socket.emit('message_fixed', {room: room, msg: i.value, user: myName});
            i.value = "";
        }
    }

    socket.on('chat_update', (data) => {
        const box = document.getElementById("messages");
        const div = document.createElement("div");
        div.className = "msg " + (data.user === myName ? "mine" : "other");
        div.innerHTML = `<b>${data.user}:</b><br>${data.msg}`;
        box.appendChild(div); box.scrollTop = box.scrollHeight;
    });

    socket.on('new_invite', () => {
        document.getElementById('notif-count').innerText = "Есть новые!";
        document.getElementById('notif-count').style.color = "#5288c1";
    });
</script>
</body>
</html>
"""

@app.route('/')
def index():
    if 'user' not in session: return redirect('/login')
    user = session['user']
    r_name = request.args.get('room')
    password = request.args.get('pass', '')
    
    my_notifs = notifications.get(user, [])

    if r_name == 'BOT':
        return render_template_string(HTML_LAYOUT, username=user, rooms=rooms_db, current_room='BOT', my_notifs=my_notifs)

    if r_name in rooms_db:
        if rooms_db[r_name]['password'] and rooms_db[r_name]['password'] != password:
            return "<script>alert('Неверный пароль!'); window.location.href='/';</script>"
    else: r_name = None
    
    return render_template_string(HTML_LAYOUT, username=user, rooms=rooms_db, current_room=r_name)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nick = request.form.get('nick').strip()
        session['user'] = nick
        all_users[nick] = True # Регистрируем в системе
        return redirect('/')
    return '<body style="background:#0e1621;color:white;display:flex;align-items:center;justify-content:center;height:100vh;"><form method="POST"><input name="nick" required placeholder="Ник"><button>Войти</button></form></body>'

@app.route('/create_room', methods=['POST'])
def create():
    data = request.json
    name = data.get('name', '').strip()
    rooms_db[name] = {'password': data.get('password', ''), 'owner': session.get('user')}
    return jsonify(success=True)

@app.route('/invite', methods=['POST'])
def invite():
    data = request.json
    target = data.get('target')
    room = data.get('room')
    if target not in all_users:
        return jsonify(msg="Пользователь не найден (он должен быть онлайн хотя бы раз)")
    
    if target not in notifications: notifications[target] = []
    
    invite_data = {
        'from': session['user'],
        'room': room,
        'pass': rooms_db[room]['password']
    }
    notifications[target].append(invite_data)
    socketio.emit('new_invite', room=target) # Генерируем сигнал таргету
    return jsonify(msg="Приглашение отправлено!")

@socketio.on('join_room_fixed')
def on_join(data):
    join_room(data['room'])
    join_room(session['user']) # Личная комната для уведомлений бота

@socketio.on('message_fixed')
def handle_msg(data):
    emit('chat_update', {'user': data['user'], 'msg': data['msg']}, to=data['room'])

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))














