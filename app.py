import os, time, eventlet
eventlet.monkey_patch()

from flask import Flask, session, request, redirect, jsonify, render_template_string
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tg_ultra_94488_safe'
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*", max_http_buffer_size=25*1024*1024)

# --- РАЗДЕЛЬНЫЕ ХРАНИЛИЩА ---
rooms_db = {}     # { name: {owner, members: []} }
messages_db = {}  # { name: [ {user, msg, type} ] }
users_db = {}     # { username: {sid, invites: []} }

HTML_LAYOUT = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Telegram Private Pro</title>
    <script src="https://cdn.socket.io"></script>
    <style>
        :root { --bg: #0e1621; --side: #17212b; --acc: #5288c1; --msg-in: #182533; --msg-out: #2b5278; --text: #f5f5f5; }
        body, html { height: 100%; margin: 0; font-family: sans-serif; background: var(--bg); color: var(--text); overflow: hidden; }
        .app { display: flex; height: 100vh; }
        
        /* SIDEBAR */
        .sidebar { width: 300px; background: var(--side); border-right: 1px solid #000; display: flex; flex-direction: column; }
        .room-item { padding: 12px 15px; border-bottom: 1px solid #0e1621; cursor: pointer; display: flex; align-items: center; gap: 10px; }
        .room-item.active { background: var(--acc); }
        .avatar { width: 40px; height: 40px; border-radius: 50%; background: #4b7db1; display: flex; align-items: center; justify-content: center; font-weight: bold; }
        
        /* CHAT */
        .main { flex: 1; display: flex; flex-direction: column; background: #0e1621; }
        .header { background: var(--side); padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #000; }
        #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 10px; }
        .bubble { max-width: 70%; padding: 10px; border-radius: 12px; }
        .mine { align-self: flex-end; background: var(--msg-out); }
        .other { align-self: flex-start; background: var(--msg-in); }
        
        /* DRAWER */
        #drawer { position: fixed; left: -310px; top: 0; width: 300px; height: 100%; background: var(--side); transition: 0.3s; z-index: 1000; padding: 20px; box-shadow: 5px 0 15px #000; }
        #drawer.open { left: 0; }
        
        .input-bar { padding: 15px; background: var(--side); display: flex; gap: 10px; }
        .inp { flex: 1; background: #242f3d; border: none; padding: 10px; border-radius: 20px; color: white; outline: none; }
        .btn-acc { color: var(--acc); cursor: pointer; background: none; border: none; font-weight: bold; }
    </style>
</head>
<body>

<div id="drawer">
    <h3>Настройки</h3>
    <form action="/change_nick" method="POST">
        <input name="new_nick" value="{{ username }}" class="inp" style="width:100%">
        <button type="submit" style="width:100%; margin-top:10px; background:var(--acc); border:none; color:white; padding:10px; border-radius:8px;">Сохранить</button>
    </form>
    <button onclick="toggleMenu()" style="margin-top:20px; background:none; border:none; color:gray;">Закрыть</button>
</div>

<div class="app">
    <div class="sidebar">
        <div style="padding:15px; display:flex; gap:10px; align-items:center;">
            <div onclick="toggleMenu()" style="cursor:pointer">☰</div>
            <b>Telegram Private</b>
        </div>
        <div style="flex:1; overflow-y:auto;">
            <div class="room-item {{ 'active' if current == 'BOT' else '' }}" onclick="location.href='/?room=BOT'">
                <div class="avatar">🤖</div>
                <div><b>Бот-Ассистент</b><br><small>Уведомления</small></div>
            </div>
            {% for r_name in my_rooms %}
            <div class="room-item {{ 'active' if r_name == current else '' }}" onclick="location.href='/?room={{ r_name }}'">
                <div class="avatar">{{ r_name[:1].upper() }}</div>
                <div><b>{{ r_name }}</b></div>
            </div>
            {% endfor %}
        </div>
        <button onclick="createRoom()" style="margin:10px; padding:10px; background:var(--acc); border:none; color:white; border-radius:8px;">+ Новая беседа</button>
    </div>

    <div class="main">
        {% if current %}
        <div class="header">
            <b>{{ '🤖 Бот' if current == 'BOT' else current }}</b>
            <div>
                {% if current != 'BOT' %}
                <button onclick="showMembers()" class="btn-acc">👥 Участники</button>
                <button onclick="inviteFriend()" class="btn-acc" style="margin-left:10px;">➕ Пригласить</button>
                {% endif %}
            </div>
        </div>
        <div id="chat">
            {% if current == 'BOT' %}
                {% for inv in my_invites %}
                <div class="bubble other">
                    📩 <b>{{ inv.from }}</b> пригласил тебя в <b>{{ inv.room }}</b><br><br>
                    <button onclick="acceptInvite('{{ inv.room }}')" style="background:var(--acc); border:none; color:white; padding:5px; border-radius:5px;">Принять</button>
                </div>
                {% endfor %}
            {% else %}
                {% for m in history %}
                <div class="bubble {{ 'mine' if m.user == username else 'other' }}">
                    <small style="color:var(--acc)">{{ m.user }}</small><br>
                    {% if m.type == 'img' %}
                    <img src="{{ m.msg }}" style="max-width:100%; border-radius:8px;">
                    {% else %}
                    {{ m.msg }}
                    {% endif %}
                </div>
                {% endfor %}
            {% endif %}
        </div>
        {% if current != 'BOT' %}
        <div class="input-bar">
            <input type="file" id="img" hidden onchange="sendPhoto(this)">
            <button onclick="document.getElementById('img').click()" class="btn-acc">📎</button>
            <input id="msg" class="inp" placeholder="Сообщение..." onkeypress="if(event.key==='Enter') sendText()">
            <button onclick="sendText()" class="btn-acc">➤</button>
        </div>
        {% endif %}
        {% endif %}
    </div>
</div>

<script>
    const socket = io();
    const me = "{{ username }}";
    const room = "{{ current }}";

    if(room && room !== 'BOT') { socket.emit('join', {room: room}); }

    function toggleMenu() { document.getElementById('drawer').classList.toggle('open'); }

    function sendText() {
        const i = document.getElementById("msg");
        if(i.value.trim()) {
            socket.emit('msg', {room: room, user: me, msg: i.value, type: 'text'});
            i.value = "";
        }
    }

    function sendPhoto(input) {
        const reader = new FileReader();
        reader.onload = (e) => socket.emit('msg', {room: room, user: me, msg: e.target.result, type: 'img'});
        reader.readAsDataURL(input.files[0]);
    }

    function createRoom() {
        const n = prompt("Название приватной комнаты:");
        if(n) fetch('/create', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:n})})
              .then(() => location.href='/?room='+n);
    }

    function inviteFriend() {
        const who = prompt("Ник друга:");
        if(who) socket.emit('invite', {to: who, room: room, from: me});
    }

    function acceptInvite(r) {
        fetch('/accept', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({room:r})})
        .then(() => location.href='/?room='+r);
    }

    function showMembers() {
        fetch('/members?room='+room).then(r=>r.json()).then(data => alert("Участники: " + data.join(", ")));
    }

    socket.on('update', (data) => {
        const box = document.getElementById("chat");
        const div = document.createElement("div");
        div.className = "bubble " + (data.user === me ? "mine" : "other");
        if(data.type === 'img') div.innerHTML = `<small>${data.user}</small><br><img src="${data.msg}" style="max-width:100%; border-radius:8px;">`;
        else div.innerHTML = `<small>${data.user}</small><br>${data.msg}`;
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
    });

    socket.on('notify', () => { if(room === 'BOT') location.reload(); });
</script>
</body>
</html>
"""

@app.route('/')
def index():
    if 'user' not in session: return redirect('/login')
    user = session['user']
    room = request.args.get('room')
    
    # Загружаем комнаты, где юзер состоит
    my_rooms = [n for n, v in rooms_db.items() if user in v['members']]
    
    # История сообщений
    history = messages_db.get(room, [])
    
    # Приглашения для бота
    my_invites = users_db.get(user, {}).get('invites', [])

    return render_template_string(HTML_LAYOUT, username=user, my_rooms=my_rooms, 
                                 current=room, history=history, my_invites=my_invites)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('nick')
        session['user'] = u
        if u not in users_db: users_db[u] = {'invites': []}
        return redirect('/')
    return '<body style="background:#0e1621;color:white;display:flex;justify-content:center;align-items:center;height:100vh;"><form method="POST"><input name="nick" placeholder="Ник" required><button>Войти</button></form></body>'

@app.route('/create', methods=['POST'])
def create():
    name = request.json.get('name')
    if name not in rooms_db:
        rooms_db[name] = {'owner': session['user'], 'members': [session['user']]}
        messages_db[name] = []
    return "ok"

@app.route('/accept', methods=['POST'])
def accept():
    room = request.json.get('room')
    user = session['user']
    if room in rooms_db and user not in rooms_db[room]['members']:
        rooms_db[room]['members'].append(user)
        # Удаляем инвайт после принятия
        users_db[user]['invites'] = [i for i in users_db[user]['invites'] if i['room'] != room]
    return "ok"

@app.route('/members')
def get_members():
    room = request.args.get('room')
    return jsonify(rooms_db.get(room, {}).get('members', []))

@app.route('/change_nick', methods=['POST'])
def change_nick():
    session['user'] = request.form.get('new_nick')
    return redirect('/')

@socketio.on('join')
def on_join(data):
    join_room(data['room'])

@socketio.on('msg')
def handle_msg(data):
    # Сохраняем в историю (хранилище сообщений)
    if data['room'] in messages_db:
        messages_db[data['room']].append({'user': data['user'], 'msg': data['msg'], 'type': data['type']})
    emit('update', data, to=data['room'])

@socketio.on('invite')
def handle_invite(data):
    target = data['to']
    if target in users_db:
        users_db[target]['invites'].append({'from': data['from'], 'room': data['room']})
        emit('notify', to=target) # Сигнал боту цели

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)

















