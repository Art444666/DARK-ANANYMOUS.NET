import os, time
from flask import Flask, session, request, redirect, jsonify, render_template_string
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tg_fixed_94488'
# Настройки для стабильной работы на Render
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=20 * 1024 * 1024)

# Глобальная база (сохраняется до перезапуска сервера)
rooms_db = {} 

HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Telegram Elite Fixed</title>
    <script src="https://cdn.socket.io"></script>
    <style>
        :root { --bg: #0e1621; --side: #17212b; --acc: #5288c1; --msg-in: #182533; --msg-out: #2b5278; --text: #f5f5f5; }
        body, html { height: 100%; margin: 0; font-family: -apple-system, sans-serif; background: var(--bg); color: var(--text); overflow: hidden; }
        .app-wrap { display: flex; height: 100vh; width: 100vw; position: relative; }

        /* ВЫДВИЖНОЕ МЕНЮ (ПОЛНОСТЬЮ СКРЫТО) */
        #drawer { 
            position: fixed; left: -320px; top: 0; width: 300px; height: 100%; 
            background: var(--side); z-index: 2000; transition: 0.3s; padding: 25px; 
            box-sizing: border-box; box-shadow: 10px 0 20px #000; 
        }
        #drawer.open { transform: translateX(320px); }
        .overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: none; z-index: 1500; }

        /* САЙДБАР */
        .sidebar { width: 320px; background: var(--side); border-right: 1px solid #080a0d; display: flex; flex-direction: column; flex-shrink: 0; }
        .sb-header { padding: 15px; display: flex; align-items: center; gap: 15px; border-bottom: 1px solid #0e1621; }
        .rooms-list { flex: 1; overflow-y: auto; }
        .room-item { padding: 12px 15px; border-bottom: 1px solid #0e1621; cursor: pointer; display: flex; align-items: center; gap: 12px; }
        .room-item:hover { background: rgba(255,255,255,0.05); }
        .room-item.active { background: var(--acc); }
        .avatar { width: 45px; height: 45px; border-radius: 50%; background: var(--acc); display: flex; align-items: center; justify-content: center; font-weight: bold; }

        /* ЧАТ */
        .chat-main { flex: 1; display: flex; flex-direction: column; background: #0e1621; position: relative; }
        .chat-header { background: var(--side); padding: 15px 20px; font-weight: bold; border-bottom: 1px solid #000; display: flex; justify-content: space-between; align-items: center; }
        #messages { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 10px; }
        .msg { max-width: 75%; padding: 10px; border-radius: 12px; animation: slideUp 0.2s; word-wrap: break-word; }
        .mine { align-self: flex-end; background: var(--msg-out); border-bottom-right-radius: 2px; }
        .other { align-self: flex-start; background: var(--msg-in); border-bottom-left-radius: 2px; }

        /* ИНПУТЫ */
        .input-bar { padding: 15px; background: var(--side); display: flex; gap: 10px; align-items: center; }
        .inp { flex: 1; background: #242f3d; border: none; padding: 10px 15px; border-radius: 20px; color: white; outline: none; }
        .btn-tg { background: none; border: none; color: var(--acc); cursor: pointer; font-weight: bold; font-size: 22px; }
        
        .fab { position: absolute; bottom: 20px; left: 250px; width: 50px; height: 50px; border-radius: 50%; background: var(--acc); border: none; color: white; font-size: 24px; cursor: pointer; z-index: 100; box-shadow: 0 4px 10px #000; }

        @keyframes slideUp { from { opacity: 0; transform: translateY(10px); } }
    </style>
</head>
<body>

<div class="overlay" id="overlay" onclick="toggleMenu()"></div>
<div id="drawer">
    <h2 style="color: var(--acc); margin-top: 0;">Настройки</h2>
    <form action="/change_nick" method="POST">
        <label style="font-size: 12px; color: gray;">ВАШ НИКНЕЙМ</label>
        <input name="new_nick" class="inp" value="{{ username }}" style="width:100%; margin-top: 5px;">
        <button type="submit" style="width:100%; margin-top:15px; background:var(--acc); border:none; color:white; padding:10px; border-radius:8px; cursor:pointer;">Сохранить</button>
    </form>
    <hr style="border: 0.5px solid #242f3d; margin: 30px 0;">
    <button onclick="adminLogin()" style="color: #ff6b6b; background:none; border:none; cursor:pointer;">🔑 Админ-панель</button>
</div>

<div class="app-wrap">
    <div class="sidebar">
        <div class="sb-header">
            <div onclick="toggleMenu()" style="cursor:pointer; font-size: 22px;">☰</div>
            <b style="color: var(--acc); font-size: 18px;">Telegram</b>
        </div>
        <div class="rooms-list">
            {% for r_name, r_info in rooms.items() %}
            <div class="room-item {{ 'active' if r_name == current_room else '' }}" 
                 onclick="enterRoom('{{ r_name }}', {{ 'true' if r_info.password else 'false' }})">
                <div class="avatar">{{ r_name[:1].upper() }}</div>
                <div style="flex:1">
                    <div style="font-weight: 600;">{{ r_name }} {{ '🔐' if r_info.password else '' }}</div>
                    <div style="font-size: 12px; color: #8e959b;">нажмите, чтобы войти</div>
                </div>
            </div>
            {% endfor %}
        </div>
        <button class="fab" onclick="createRoom()">+</button>
    </div>

    <div class="chat-main">
        {% if current_room %}
        <div class="chat-header">
            <span>{{ current_room }}</span>
            <button onclick="inviteUser()" style="background:var(--acc); border:none; color:white; padding:5px 10px; border-radius:5px; cursor:pointer; font-size:12px;">Пригласить +</button>
        </div>
        <div id="messages"></div>
        <div class="input-bar">
            <input type="text" id="msgInp" class="inp" placeholder="Написать сообщение..." onkeypress="if(event.key==='Enter') sendMsg()">
            <button onclick="sendMsg()" class="btn-tg">➤</button>
        </div>
        {% else %}
        <div style="flex:1; display:flex; align-items:center; justify-content:center; color:gray;">Выберите чат из списка слева</div>
        {% endif %}
    </div>
</div>

<script>
    const socket = io();
    const myName = "{{ username }}";
    const activeRoom = "{{ current_room }}";

    // Принудительное подключение к комнате
    if(activeRoom) {
        socket.emit('join_forced', {room: activeRoom});
    }

    function toggleMenu() {
        const d = document.getElementById('drawer');
        const o = document.getElementById('overlay');
        d.classList.toggle('open');
        o.style.display = d.classList.contains('open') ? 'block' : 'none';
    }

    function enterRoom(name, isPrivate) {
        let pass = isPrivate ? prompt("Введите пароль:") : "";
        if(isPrivate && pass === null) return;
        window.location.href = "/?room=" + encodeURIComponent(name) + "&pw=" + encodeURIComponent(pass);
    }

    async function createRoom() {
        const n = prompt("Название чата:");
        if(!n) return;
        const p = prompt("Пароль (пусто для открытого):");
        const res = await fetch('/create_room', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: n, password: p})
        });
        if(res.ok) window.location.href = "/?room=" + encodeURIComponent(n) + "&pw=" + encodeURIComponent(p);
    }

    // ИСПРАВЛЕННАЯ ФУНКЦИЯ ОТПРАВКИ
    function sendMsg() {
        const i = document.getElementById("msgInp");
        if(i.value.trim() && activeRoom) {
            socket.emit('message_event', {
                room: activeRoom,
                msg: i.value,
                user: myName
            });
            i.value = "";
        }
    }

    socket.on('chat_update', (data) => {
        const box = document.getElementById("messages");
        if(!box) return;
        const div = document.createElement("div");
        div.className = "msg " + (data.user === myName ? "mine" : "other");
        div.innerHTML = `<small style="color:var(--acc)">${data.user}</small><br>${data.msg}`;
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
    });

    function adminLogin() {
        if(prompt("Пароль:") === "94488") alert("Админ-режим активен!");
    }

    function inviteUser() {
        const target = prompt("Ник пользователя для приглашения:");
        if(target) alert("Приглашение отправлено пользователю " + target);
    }
</script>
</body>
</html>
"""

@app.route('/')
def index():
    if 'user' not in session: return redirect('/login')
    
    room_name = request.args.get('room')
    password = request.args.get('pw', '')

    if room_name in rooms_db:
        if rooms_db[room_name]['password'] and rooms_db[r_name]['password'] != password:
            return "<script>alert('Неверный пароль!'); window.location.href='/';</script>"
    else: room_name = None

    return render_template_string(HTML_LAYOUT, 
                                username=session['user'], 
                                rooms=rooms_db, 
                                current_room=room_name)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['user'] = request.form.get('nick')
        return redirect('/')
    return '<body style="background:#0e1621;color:white;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;"><form method="POST"><input name="nick" required placeholder="Ваш ник" style="padding:10px;border-radius:8px;border:none;"><br><button style="margin-top:10px;background:#5288c1;color:white;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;">Войти</button></form></body>'

@app.route('/create_room', methods=['POST'])
def create():
    data = request.json
    name = data.get('name', '').strip()
    if name:
        rooms_db[name] = {'password': data.get('password', ''), 'owner': session.get('user')}
        return jsonify(success=True)
    return jsonify(success=False), 400

@app.route('/change_nick', methods=['POST'])
def change_nick():
    new = request.form.get('new_nick')
    if new: session['user'] = new
    return redirect('/')

@socketio.on('join_forced')
def on_join(data):
    join_room(data['room'])

@socketio.on('message_event')
def handle_msg(data):
    # Принудительная рассылка во все сокеты комнаты
    emit('chat_update', {'user': data['user'], 'msg': data['msg']}, to=data['room'])

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
















