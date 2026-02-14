import os
from flask import Flask, session, request, redirect, jsonify, render_template_string
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tg_94488_ultra'
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=10*1024*1024)

# Глобальное хранилище (сохраняется пока сервер не перезагружен)
# Для вечного хранения на Render нужна БД, но словарь держит данные сессии билда.
rooms_db = {} 

HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Telegram X Beta</title>
    <script src="https://cdn.socket.io"></script>
    <style>
        :root { --bg: #0e1621; --side: #17212b; --acc: #5288c1; --msg: #182533; --my: #2b5278; }
        body, html { height: 100%; margin: 0; font-family: sans-serif; background: var(--bg); color: white; overflow: hidden; }
        
        .app { display: flex; height: 100vh; position: relative; }

        /* ВЫДВИЖНОЕ МЕНЮ */
        #drawer {
            position: fixed; left: -300px; top: 0; width: 280px; height: 100%;
            background: var(--side); z-index: 1000; transition: 0.3s;
            box-shadow: 5px 0 15px rgba(0,0,0,0.5); padding: 20px;
        }
        #drawer.open { left: 0; }
        .overlay { 
            position: fixed; inset: 0; background: rgba(0,0,0,0.5); 
            display: none; z-index: 900; 
        }

        /* САЙДБАР */
        .side { width: 300px; background: var(--side); border-right: 1px solid #000; display: flex; flex-direction: column; }
        .room-item { padding: 15px; border-bottom: 1px solid #0e1621; cursor: pointer; transition: 0.2s; }
        .room-item:hover { background: #232e3c; }

        /* ЧАТ */
        .main { flex: 1; display: flex; flex-direction: column; background: #0e1621; }
        #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 10px; }
        .bubble { max-width: 80%; padding: 10px; border-radius: 12px; }
        .my { align-self: flex-end; background: var(--my); }
        .other { align-self: flex-start; background: var(--msg); }

        .input-area { padding: 15px; background: var(--side); display: flex; gap: 10px; }
        .inp { flex: 1; background: #242f3d; border: none; padding: 10px; border-radius: 10px; color: white; outline: none; }
        
        .btn { background: var(--acc); border: none; color: white; padding: 10px; border-radius: 8px; cursor: pointer; }
    </style>
</head>
<body>

<div class="overlay" id="overlay" onclick="toggleMenu()"></div>

<!-- ВЫДВИЖНОЕ МЕНЮ НАСТРОЕК -->
<div id="drawer">
    <h3>Настройки</h3>
    <form action="/change_nick" method="POST">
        <label style="font-size: 12px; color: var(--acc)">ВАШ НИК</label><br>
        <input name="new_nick" class="inp" style="width: 90%; margin-top: 5px;" value="{{ username }}">
        <button type="submit" class="btn" style="margin-top: 10px; width: 100%;">Сохранить</button>
    </form>
    <hr style="border: 0.5px solid #242f3d; margin: 20px 0;">
    <button onclick="adminLogin()" class="btn" style="background: #ff6b6b; width: 100%;">Админ-панель</button>
</div>

<div class="app">
    <div class="side">
        <div style="padding: 15px; display: flex; align-items: center; gap: 10px;">
            <div onclick="toggleMenu()" style="cursor:pointer; font-size: 20px;">☰</div>
            <b style="color: var(--acc)">TELEGRAM</b>
        </div>
        <div id="roomList" style="flex:1; overflow-y:auto;">
            <!-- Сюда сервер принудительно отдает комнаты -->
            {% for r_name in rooms %}
            <div class="room-item" onclick="joinRoom('{{ r_name }}')">
                <b>{{ r_name }}</b><br><small style="color:gray">нажмите, чтобы войти</small>
            </div>
            {% endfor %}
        </div>
        <div style="padding: 10px;">
            <button onclick="createRoom()" class="btn" style="width:100%">+ Создать беседу</button>
        </div>
    </div>

    <div class="main">
        <div id="chat-h" style="padding: 15px; background: var(--side); font-weight: bold; border-bottom: 1px solid #000;">Выберите чат</div>
        <div id="chat"></div>
        <div class="input-area" id="i-box" style="display:none">
            <input type="text" id="msg" class="inp" placeholder="Сообщение..." onkeypress="if(event.key==='Enter') send()">
            <button onclick="send()" class="btn">➤</button>
        </div>
    </div>
</div>

<script>
    const socket = io();
    const me = "{{ username }}";
    let currentRoom = "";

    function toggleMenu() {
        const d = document.getElementById('drawer');
        const o = document.getElementById('overlay');
        d.classList.toggle('open');
        o.style.display = d.classList.contains('open') ? 'block' : 'none';
    }

    async function createRoom() {
        const name = prompt("Название беседы:");
        if(!name) return;
        const res = await fetch('/create_room', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: name})
        });
        if(res.ok) location.reload(); // Принудительно обновляем, чтобы сервер отдал список
    }

    function joinRoom(name) {
        currentRoom = name;
        document.getElementById("chat-h").innerText = name;
        document.getElementById("i-box").style.display = "flex";
        document.getElementById("chat").innerHTML = "";
        socket.emit('join', {room: name});
    }

    function send() {
        const i = document.getElementById("msg");
        if(i.value.trim()) {
            socket.emit('message', {room: currentRoom, msg: i.value});
            i.value = "";
        }
    }

    socket.on('chat_msg', (data) => {
        const chat = document.getElementById("chat");
        const b = document.createElement("div");
        b.className = "bubble " + (data.user === me ? "my" : "other");
        b.innerHTML = `<b>${data.user}:</b><br>${data.msg}`;
        chat.appendChild(b);
        chat.scrollTop = chat.scrollHeight;
    });

    function adminLogin() {
        const p = prompt("Пароль:");
        if(p === "94488") alert("Доступ разрешен");
    }
</script>
</body>
</html>
"""

@app.route('/')
def index():
    if 'user' not in session: return redirect('/login')
    # Принудительно отдаем список комнат из словаря rooms_db
    return render_template_string(HTML_LAYOUT, username=session['user'], rooms=rooms_db)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['user'] = request.form.get('nick')
        return redirect('/')
    return '<body style="background:#0e1621; color:white; display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh;"><form method="POST"><h2>Вход</h2><input name="nick" required placeholder="Ваш ник"><br><button style="margin-top:10px">Войти</button></form></body>'

@app.route('/change_nick', methods=['POST'])
def change_nick():
    new_nick = request.form.get('new_nick')
    if new_nick: session['user'] = new_nick
    return redirect('/')

@app.route('/create_room', methods=['POST'])
def create():
    data = request.json
    name = data.get('name', '').strip()
    if name:
        rooms_db[name] = {'owner': session.get('user')}
        return jsonify(success=True)
    return jsonify(success=False), 400

@socketio.on('join')
def on_join(data):
    join_room(data['room'])

@socketio.on('message')
def handle_msg(data):
    emit('chat_msg', {'user': session['user'], 'msg': data['msg']}, to=data['room'])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)




