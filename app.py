import os, eventlet
eventlet.monkey_patch()

from flask import Flask, session, request, redirect, jsonify, render_template_string
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tg_final_fixed_94488'
# Настройки для Render: принудительный WebSocket и большой буфер
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*", max_http_buffer_size=25*1024*1024)

# --- ХРАНИЛИЩА ---
rooms_db = {}     
messages_db = {}  
users_db = {}     

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Telegram Hybrid Fixed</title>
    <script src="https://cdn.socket.io"></script>
    <style>
        :root { --bg: #0e1621; --side: #17212b; --acc: #5288c1; --msg-in: #182533; --msg-out: #2b5278; --text: #f5f5f5; }
        body, html { height: 100%; margin: 0; font-family: sans-serif; background: var(--bg); color: var(--text); overflow: hidden; }
        .app-wrap { display: flex; height: 100vh; position: relative; }
        .sidebar { width: 300px; background: var(--side); border-right: 1px solid #000; display: flex; flex-direction: column; z-index: 10; }
        .room-item { padding: 12px 15px; border-bottom: 1px solid #0e1621; cursor: pointer; display: flex; align-items: center; gap: 10px; }
        .room-item.active { background: var(--acc); }
        .avatar { width: 40px; height: 40px; border-radius: 50%; background: #4b7db1; display: flex; align-items: center; justify-content: center; font-weight: bold; }
        .main { flex: 1; display: flex; flex-direction: column; background: #0e1621; z-index: 5; }
        .header { background: var(--side); padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #000; }
        #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 10px; }
        .bubble { max-width: 75%; padding: 10px; border-radius: 12px; position: relative; }
        .mine { align-self: flex-end; background: var(--msg-out); }
        .other { align-self: flex-start; background: var(--msg-in); }
        #drawer { position: fixed; left: -320px; top: 0; width: 300px; height: 100%; background: var(--side); transition: 0.3s; z-index: 1000; padding: 25px; box-shadow: 10px 0 20px #000; }
        #drawer.open { left: 0; }
        .overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: none; z-index: 999; }
        .input-bar { padding: 15px; background: var(--side); display: flex; gap: 10px; }
        .inp { flex: 1; background: #242f3d; border: none; padding: 10px; border-radius: 20px; color: white; outline: none; }
        .btn-acc { background: none; border: none; color: var(--acc); cursor: pointer; font-weight: bold; }
    </style>
</head>
<body>
<div class="overlay" id="overlay" onclick="toggleMenu()"></div>
<div id="drawer">
    <h3 style="color:var(--acc)">Настройки</h3>
    <form action="/change_nick" method="POST">
        <input name="new_nick" value="{{ username }}" class="inp" style="width:100%">
        <button type="submit" style="width:100%; margin-top:15px; background:var(--acc); border:none; color:white; padding:10px; border-radius:8px; cursor:pointer;">Сохранить</button>
    </form>
    <button onclick="toggleMenu()" style="margin-top:20px; color:gray; background:none; border:none; cursor:pointer;">Закрыть</button>
</div>

<div class="app-wrap">
    <div class="sidebar">
        <div style="padding:15px; display:flex; gap:15px; align-items:center;">
            <div onclick="toggleMenu()" style="cursor:pointer; font-size:22px;">☰</div>
            <b>Telegram</b>
        </div>
        <div style="flex:1; overflow-y:auto;">
            <div class="room-item {{ 'active' if current == 'BOT' else '' }}" onclick="location.href='/?room=BOT'">
                <div class="avatar">🤖</div>
                <div><b>Бот</b><br><small>Уведомления</small></div>
            </div>
            {% for r_name in my_rooms %}
            <div class="room-item {{ 'active' if r_name == current else '' }}" onclick="location.href='/?room={{ r_name }}'">
                <div class="avatar">{{ r_name[:1].upper() }}</div>
                <div><b>{{ r_name }}</b></div>
            </div>
            {% endfor %}
        </div>
        <button onclick="createRoom()" style="margin:10px; padding:12px; background:var(--acc); border:none; color:white; border-radius:8px; cursor:pointer;">+ СОЗДАТЬ БЕСЕДУ</button>
    </div>

    <div class="main">
        {% if current %}
        <div class="header">
            <b>{{ current }}</b>
            <div>
                {% if current != 'BOT' %}
                <button onclick="showMembers()" class="btn-acc">👥 Участники</button>
                <button onclick="inviteFriend()" class="btn-acc" style="margin-left:10px;">➕ Инвайт</button>
                {% endif %}
            </div>
        </div>
        <div id="chat">
            {% if current == 'BOT' %}
                {% for inv in my_invites %}
                <div class="bubble other">📩 <b>{{ inv.from }}</b> зовет в <b>{{ inv.room }}</b><br><br>
                <button onclick="acceptInvite('{{ inv.room }}')" style="background:var(--acc); color:white; border:none; padding:5px; border-radius:5px; cursor:pointer;">Принять</button></div>
                {% endfor %}
            {% else %}
                {% for m in history %}
                <div class="bubble {{ 'mine' if m.user == username else 'other' }}">
                    <small style="color:var(--acc)">{{ m.user }}</small><br>
                    {% if m.type == 'img' %}<img src="{{ m.msg }}" style="max-width:100%; border-radius:8px;">{% else %}{{ m.msg }}{% endif %}
                </div>
                {% endfor %}
            {% endif %}
        </div>
        {% if current != 'BOT' %}
        <div class="input-bar">
            <input type="file" id="imgInp" hidden onchange="sendPhoto(this)">
            <button onclick="document.getElementById('imgInp').click()" class="btn-acc">📎</button>
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
    const activeRoom = "{{ current }}";

    // ПРИНУДИТЕЛЬНОЕ ПОДКЛЮЧЕНИЕ
    socket.on('connect', () => {
        if(activeRoom && activeRoom !== 'BOT') { 
            socket.emit('join_fixed', {room: activeRoom}); 
        }
    });

    function toggleMenu() {
        const d = document.getElementById('drawer');
        d.classList.toggle('open');
        document.getElementById('overlay').style.display = d.classList.contains('open') ? 'block' : 'none';
    }

    // ПРИНУДИТЕЛЬНАЯ ОТРИСОВКА (Изюминка)
    function addMsgToUI(user, msg, type) {
        const box = document.getElementById("chat");
        const div = document.createElement("div");
        div.className = "bubble " + (user === me ? "mine" : "other");
        if(type === 'img') div.innerHTML = `<small style="color:var(--acc)">${user}</small><br><img src="${msg}" style="max-width:100%; border-radius:8px;">`;
        else div.innerHTML = `<small style="color:var(--acc)">${user}</small><br>${msg}`;
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
    }

    function sendText() {
        const i = document.getElementById("msg");
        const text = i.value.trim();
        if(text && activeRoom) {
            // 1. Рисуем у себя сразу (принудительно)
            addMsgToUI(me, text, 'text');
            // 2. Шлем на сервер
            socket.emit('msg_fixed', {room: activeRoom, user: me, msg: text, type: 'text'});
            i.value = "";
        }
    }

    function sendPhoto(input) {
        const reader = new FileReader();
        reader.onload = (e) => {
            addMsgToUI(me, e.target.result, 'img');
            socket.emit('msg_fixed', {room: activeRoom, user: me, msg: e.target.result, type: 'img'});
        };
        reader.readAsDataURL(input.files[0]);
    }

    socket.on('update_chat', (data) => {
        if(data.user !== me) { addMsgToUI(data.user, data.msg, data.type); }
    });

    function createRoom() {
        const n = prompt("Имя комнаты:");
        if(n) fetch('/create', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:n})})
              .then(() => location.href='/?room='+encodeURIComponent(n));
    }

    function inviteFriend() {
        const who = prompt("Ник друга:");
        if(who) fetch('/send_invite', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({to:who, room:activeRoom})})
                .then(r=>r.json()).then(d => alert(d.msg));
    }

    function acceptInvite(r) {
        fetch('/accept', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({room:r})})
        .then(() => location.href='/?room='+encodeURIComponent(r));
    }

    function showMembers() {
        fetch('/members?room='+encodeURIComponent(activeRoom))
        .then(r=>r.json()).then(data => alert("В чате: " + data.join(", ")));
    }

    socket.on('new_notif', () => { if(activeRoom === 'BOT') location.reload(); });
</script>
</body>
</html>
"""

@app.route('/')
def index():
    if 'user' not in session: return redirect('/login')
    user, room = session['user'], request.args.get('room')
    my_rooms = [n for n, v in rooms_db.items() if user in v['members']]
    history, my_invites = messages_db.get(room, []), users_db.get(user, {}).get('invites', [])
    return render_template_string(HTML, username=user, my_rooms=my_rooms, current=room, history=history, my_invites=my_invites)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('nick').strip()
        session['user'] = u
        if u not in users_db: users_db[u] = {'invites': []}
        return redirect('/')
    return '<body style="background:#0e1621;color:white;display:flex;justify-content:center;align-items:center;height:100vh;"><form method="POST"><input name="nick" placeholder="Ник" required><button>Войти</button></form></body>'

@app.route('/create', methods=['POST'])
def create():
    name = request.json.get('name').strip()
    if name and name not in rooms_db:
        rooms_db[name], messages_db[name] = {'owner': session['user'], 'members': [session['user']]}, []
    return jsonify(success=True)

@app.route('/send_invite', methods=['POST'])
def send_invite():
    target, room = request.json.get('to').strip(), request.json.get('room')
    if target in users_db:
        users_db[target]['invites'].append({'from': session['user'], 'room': room})
        socketio.emit('new_notif', to=target)
        return jsonify(msg="Инвайт отправлен!")
    return jsonify(msg="Юзер не найден")

@app.route('/accept', methods=['POST'])
def accept():
    room, user = request.json.get('room'), session['user']
    if room in rooms_db and user not in rooms_db[room]['members']:
        rooms_db[room]['members'].append(user)
        users_db[user]['invites'] = [i for i in users_db[user]['invites'] if i['room'] != room]
    return jsonify(success=True)

@app.route('/members')
def get_members():
    room = request.args.get('room')
    return jsonify(rooms_db.get(room, {}).get('members', []))

@app.route('/change_nick', methods=['POST'])
def change_nick():
    session['user'] = request.form.get('new_nick')
    return redirect('/')

@socketio.on('join_fixed')
def on_join(data):
    join_room(data['room'])

@socketio.on('msg_fixed')
def handle_msg(data):
    room_name = data['room']
    if room_name in messages_db:
        messages_db[room_name].append({'user': data['user'], 'msg': data['msg'], 'type': data['type']})
        # Рассылаем всем в комнате КРОМЕ отправителя (потому что у него уже отрисовалось)
        emit('update_chat', data, to=room_name, include_self=False)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))





















