import os, time, random
from flask import Flask, session, request, redirect, jsonify, render_template_string
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tg_fixed_94488'
# Настройка для работы с фото и стабильных сокетов
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=15 * 1024 * 1024)

# Глобальное хранилище комнат
rooms_db = {} 

HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Telegram Fixed Edition</title>
    <script src="https://cdn.socket.io"></script>
    <style>
        :root {
            --bg: #0e1621; --side: #17212b; --acc: #5288c1; 
            --msg-in: #182533; --msg-out: #2b5278; --text: #f5f5f5;
        }
        
        * { box-sizing: border-box; }
        body, html { height: 100%; margin: 0; font-family: -apple-system, sans-serif; background: var(--bg); color: var(--text); overflow: hidden; }

        /* ОСНОВНОЙ КОНТЕЙНЕР */
        .app-wrap { display: flex; height: 100vh; width: 100vw; position: relative; }

        /* ВЫДВИЖНОЕ МЕНЮ (Абсолютно скрыто за краем) */
        #drawer {
            position: fixed; left: -320px; top: 0; width: 300px; height: 100%;
            background: var(--side); z-index: 2000; transition: transform 0.3s cubic-bezier(0, 0, 0.2, 1);
            padding: 30px 20px; box-shadow: 5px 0 15px rgba(0,0,0,0.5);
        }
        #drawer.open { transform: translateX(320px); }
        .overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: none; z-index: 1500; backdrop-filter: blur(2px); }

        /* ЛЕВАЯ ПАНЕЛЬ */
        .sidebar { width: 320px; background: var(--side); border-right: 1px solid #080a0d; display: flex; flex-direction: column; flex-shrink: 0; }
        .sb-header { padding: 15px; display: flex; align-items: center; gap: 15px; border-bottom: 1px solid #0e1621; }
        .rooms-list { flex: 1; overflow-y: auto; }
        
        .room-item { 
            padding: 12px 15px; display: flex; align-items: center; gap: 12px; 
            cursor: pointer; transition: 0.2s; border-bottom: 1px solid #0e1621;
        }
        .room-item:hover { background: rgba(255,255,255,0.05); }
        .room-item.active { background: var(--acc); }
        
        .avatar { 
            width: 48px; height: 48px; border-radius: 50%; background: #4b7db1; 
            display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 18px;
        }

        /* ПРАВАЯ ПАНЕЛЬ (ЧАТ) */
        .chat-main { flex: 1; display: flex; flex-direction: column; background: #0e1621 url('https://www.transparenttextures.com'); }
        .chat-header { background: var(--side); padding: 10px 20px; display: flex; align-items: center; gap: 15px; border-bottom: 1px solid #000; height: 60px; }
        
        #messages { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 8px; }
        .msg { max-width: 75%; padding: 8px 14px; border-radius: 12px; font-size: 15px; line-height: 1.4; position: relative; word-wrap: break-word; }
        .mine { align-self: flex-end; background: var(--msg-out); border-bottom-right-radius: 2px; }
        .other { align-self: flex-start; background: var(--msg-in); border-bottom-left-radius: 2px; }

        /* ИНПУТЫ */
        .input-bar { background: var(--side); padding: 12px 15px; display: flex; align-items: center; gap: 12px; }
        .inp { flex: 1; background: #242f3d; border: none; padding: 10px 15px; border-radius: 20px; color: white; outline: none; }
        .btn-tg { background: none; border: none; color: var(--acc); cursor: pointer; font-weight: bold; font-size: 16px; }
        
        .fab { 
            position: absolute; bottom: 25px; left: 250px; width: 50px; height: 50px; 
            border-radius: 50%; background: var(--acc); border: none; color: white; 
            font-size: 24px; cursor: pointer; box-shadow: 0 4px 10px #000; z-index: 100;
        }
    </style>
</head>
<body>

<div class="overlay" id="overlay" onclick="toggleDrawer()"></div>

<div id="drawer">
    <h2 style="color: var(--acc); margin-top: 0;">Настройки</h2>
    <p style="font-size: 13px; color: #8e959b;">Вы зашли как: <b>{{ username }}</b></p>
    <form action="/change_nick" method="POST">
        <label style="font-size: 11px; color: gray;">ИЗМЕНИТЬ НИК</label>
        <input name="new_nick" class="inp" style="width:100%; margin-top:5px;" value="{{ username }}" required>
        <button type="submit" style="width:100%; margin-top:15px; background:var(--acc); border:none; padding:10px; border-radius:8px; color:white; cursor:pointer;">СОХРАНИТЬ</button>
    </form>
    <hr style="border: 0.5px solid #242f3d; margin: 30px 0;">
    <button onclick="adminLogin()" class="btn-tg" style="color: #ff6b6b;">🔑 ПАНЕЛЬ УПРАВЛЕНИЯ</button>
</div>

<div class="app-wrap">
    <!-- БОКОВАЯ ПАНЕЛЬ -->
    <div class="sidebar">
        <div class="sb-header">
            <div onclick="toggleDrawer()" style="cursor:pointer; font-size: 22px;">☰</div>
            <b style="font-size: 18px; color: var(--acc);">Telegram</b>
        </div>
        <div class="rooms-list">
            {% for r_name, r_info in rooms.items() %}
            <div class="room-item {{ 'active' if r_name == current_room else '' }}" 
                 onclick="forceJoin('{{ r_name }}', {{ 'true' if r_info.password else 'false' }})">
                <div class="avatar">{{ r_name[:1].upper() }}</div>
                <div style="flex:1">
                    <div style="font-weight: 600;">{{ r_name }} {{ '🔐' if r_info.password else '' }}</div>
                    <div style="font-size: 12px; color: #8e959b;">нажмите, чтобы войти</div>
                </div>
            </div>
            {% endfor %}
        </div>
        <button class="fab" onclick="forceCreate()">+</button>
    </div>

    <!-- ЧАТ -->
    <div class="chat-main">
        {% if current_room %}
        <div class="chat-header">
            <div class="avatar" style="width:35px; height:35px; font-size: 14px;">{{ current_room[:1].upper() }}</div>
            <b style="font-size: 16px;">{{ current_room }}</b>
        </div>
        <div id="messages"></div>
        <div class="input-bar">
            <input type="file" id="f-inp" hidden onchange="forceFile(this)">
            <button onclick="document.getElementById('f-inp').click()" class="btn-tg" style="font-size: 20px;">📎</button>
            <input type="text" id="msgInp" class="inp" placeholder="Сообщение..." onkeypress="if(event.key==='Enter') sendForce()">
            <button onclick="sendForce()" class="btn-tg" style="font-size: 24px;">➤</button>
        </div>
        {% else %}
        <div style="flex:1; display:flex; align-items:center; justify-content:center; color: #505a64; font-size: 14px;">
            Выберите чат, чтобы начать переписку
        </div>
        {% endif %}
    </div>
</div>

<script>
    const socket = io();
    const myName = "{{ username }}";
    const activeRoom = "{{ current_room }}";

    // ПРИНУДИТЕЛЬНОЕ ПОДКЛЮЧЕНИЕ
    if(activeRoom) {
        socket.emit('join_forced', {room: activeRoom});
    }

    function toggleDrawer() {
        const d = document.getElementById('drawer');
        const o = document.getElementById('overlay');
        d.classList.toggle('open');
        o.style.display = d.classList.contains('open') ? 'block' : 'none';
    }

    function forceJoin(name, isPrivate) {
        let pass = "";
        if(isPrivate) {
            pass = prompt("Введите пароль для чата:");
            if(pass === null) return;
        }
        // Принудительная перезагрузка страницы с новыми параметрами
        window.location.href = "/?room=" + encodeURIComponent(name) + "&pw=" + encodeURIComponent(pass);
    }

    function forceCreate() {
        const n = prompt("Название чата:");
        if(!n) return;
        const p = prompt("Придумайте пароль (оставьте пустым для открытого):");
        
        fetch('/create_room_forced', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: n, password: p})
        }).then(res => {
            if(res.ok) window.location.href = "/?room=" + encodeURIComponent(n);
            else alert("Ошибка создания чата");
        });
    }

    function sendForce() {
        const i = document.getElementById("msgInp");
        if(i.value.trim()) {
            socket.emit('message_forced', {room: activeRoom, msg: i.value});
            i.value = "";
        }
    }

    function forceFile(input) {
        const reader = new FileReader();
        reader.onload = (e) => socket.emit('message_forced', {room: activeRoom, msg: 'PHOTO:' + e.target.result});
        reader.readAsDataURL(input.files[0]);
    }

    socket.on('chat_update', (data) => {
        const box = document.getElementById("messages");
        const div = document.createElement("div");
        const isMine = data.user === myName;
        div.className = "msg " + (isMine ? "mine" : "other");
        
        if(data.msg.startsWith('PHOTO:')) {
            const src = data.msg.replace('PHOTO:', '');
            div.innerHTML = `<small style="color:var(--acc)">${data.user}</small><br><img src="${src}" style="max-width:100%; border-radius:8px; margin-top:5px;">`;
        } else {
            div.innerHTML = `<small style="color:var(--acc)">${data.user}</small><br>${data.msg}`;
        }
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
    });

    function adminLogin() {
        const p = prompt("Пароль:");
        if(p === "94488") alert("Админ-режим включен!");
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

    # ПРИНУДИТЕЛЬНАЯ ПРОВЕРКА ПАРОЛЯ
    if room_name in rooms_db:
        info = rooms_db[room_name]
        if info['password'] and info['password'] != password:
            return "<script>alert('Неверный пароль!'); window.location.href='/';</script>"
    else:
        room_name = None

    return render_template_string(HTML_LAYOUT, 
                                username=session['user'], 
                                rooms=rooms_db, 
                                current_room=room_name)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['user'] = request.form.get('nick')
        return redirect('/')
    return '<body style="background:#0e1621; color:white; display:flex; align-items:center; justify-content:center; height:100vh;"><form method="POST" style="text-align:center;"><h2>Вход в чат</h2><input name="nick" required placeholder="Ваш ник" style="padding:10px; border-radius:8px; border:none;"><br><button style="margin-top:10px; background:#5288c1; color:white; border:none; padding:10px 20px; border-radius:8px; cursor:pointer;">Войти</button></form></body>'

@app.route('/create_room_forced', methods=['POST'])
def create_room():
    data = request.json
    name = data.get('name', '').strip()
    if name and name not in rooms_db:
        rooms_db[name] = {'password': data.get('password', ''), 'owner': session.get('user')}
        return jsonify(success=True)
    return jsonify(success=False), 400

@app.route('/change_nick', methods=['POST'])
def change_nick():
    new_nick = request.form.get('new_nick')
    if new_nick: session['user'] = new_nick
    return redirect('/')

@socketio.on('join_forced')
def on_join(data):
    join_room(data['room'])

@socketio.on('message_forced')
def handle_msg(data):
    # Принудительная отправка только в указанную комнату
    emit('chat_update', {'user': session['user'], 'msg': data['msg']}, to=data['room'])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)












