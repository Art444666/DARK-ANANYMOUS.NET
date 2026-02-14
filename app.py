import os, random, time
from flask import Flask, session, request, redirect, url_for, render_template_string
from flask_socketio import SocketIO, emit, join_room, leave_room, send

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tg_94488_key'
# Увеличиваем буфер для фото и ставим правильный режим для Render
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*", max_http_buffer_size=10 * 1024 * 1024)

# Хранилище
users = {}        
rooms = {}        
participants = {} 

# Вставляем твой красивый HTML прямо сюда (это решит проблему с путями)
HTML_LAYOUT = """
<!-- Сюда вставь весь код своего index.html, который мы делали ранее -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Telegram X</title>
    <script src="https://cdn.socket.io"></script>
    <style>
        :root { --bg: #0e1621; --side: #17212b; --accent: #5288c1; --msg-in: #182533; --msg-out: #2b5278; }
        body { margin: 0; font-family: 'Segoe UI', sans-serif; background: var(--bg); color: white; overflow: hidden; }
        .app { display: flex; height: 100vh; }
        .sidebar { width: 320px; background: var(--side); border-right: 1px solid #000; display: flex; flex-direction: column; position: relative; }
        .search-input { flex: 1; background: #242f3d; border: none; padding: 10px; border-radius: 10px; color: white; outline: none; }
        .main { flex: 1; display: flex; flex-direction: column; background: #0e1621 url('https://www.transparenttextures.com'); }
        .header { background: rgba(23,33,43,0.8); backdrop-filter: blur(10px); padding: 10px 20px; display: flex; align-items: center; gap: 15px; }
        #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 10px; }
        .bubble { max-width: 75%; padding: 8px 12px; border-radius: 15px; position: relative; }
        .mine { align-self: flex-end; background: var(--msg-out); }
        .other { align-self: flex-start; background: var(--msg-in); }
        .input-bar { padding: 15px; background: var(--side); display: flex; gap: 10px; align-items: center; }
        .fab { position: absolute; bottom: 20px; right: 20px; width: 50px; height: 50px; border-radius: 50%; background: var(--accent); border: none; color: white; font-size: 24px; cursor: pointer; }
    </style>
</head>
<body>
<div class="app">
    <div class="sidebar">
        <div style="padding:15px; display:flex; gap:10px;">
            <div onclick="location.href='/register'" style="cursor:pointer">☰</div>
            <input type="text" class="search-input" placeholder="Поиск..." oninput="filterRooms(this.value)">
        </div>
        <div id="roomList" style="flex:1; overflow-y:auto;"></div>
        <button class="fab" onclick="createRoom()">+</button>
    </div>
    <div class="main">
        <div class="header">
            <div id="h-name" style="font-weight:bold">Выберите чат</div>
            <div id="h-count" style="font-size:12px; color:var(--accent)"></div>
        </div>
        <div id="chat"></div>
        <div class="input-bar" id="inputBox" style="display:none">
            <input type="file" id="f" hidden onchange="up(this)">
            <button onclick="document.getElementById('f').click()" style="background:none; border:none; color:var(--accent); cursor:pointer;">📎</button>
            <input type="text" id="m" class="search-input" placeholder="Сообщение..." onkeypress="if(event.key==='Enter') send()">
            <button onclick="send()" style="background:none; border:none; color:var(--accent); font-size:24px; cursor:pointer;">➤</button>
        </div>
    </div>
</div>
<script>
    const socket = io();
    const myName = "{{ username }}";
    function send() { const i = document.getElementById("m"); if(i.value.trim()){ socket.send(i.value); i.value=""; } }
    function up(input) {
        const reader = new FileReader();
        reader.onload = (e) => socket.emit("message", "IMAGE_DATA:" + e.target.result);
        reader.readAsDataURL(input.files[0]);
    }
    socket.on("room_list", (list) => {
        const cont = document.getElementById("roomList");
        cont.innerHTML = "";
        list.forEach(r => {
            const name = r.replace(" [приват]", "");
            const d = document.createElement("div");
            d.style.padding = "12px 15px"; d.style.cursor = "pointer";
            d.onclick = () => socket.emit("join_room", {room: name, password: r.includes("[приват]") ? prompt("Пароль:") : ""});
            d.innerHTML = `<b>${name}</b>`;
            cont.appendChild(d);
        });
    });
    socket.on("room_joined", (name) => {
        document.getElementById("h-name").innerText = name;
        document.getElementById("inputBox").style.display = "flex";
        document.getElementById("chat").innerHTML = "";
    });
    socket.on("message", (data) => {
        const chat = document.getElementById("chat");
        const div = document.createElement("div");
        const [author, ...text] = data.split(":");
        div.className = "bubble " + (author.trim() === myName ? "mine" : "other");
        const content = text.join(":");
        if(content.includes("IMAGE_DATA:")){
            div.innerHTML = `<img src="${content.split('IMAGE_DATA:')[1]}" style="max-width:100%; border-radius:10px;">`;
        } else { div.innerHTML = `<b>${author}:</b><br>${content}`; }
        chat.appendChild(div); chat.scrollTop = chat.scrollHeight;
    });
    function createRoom() {
        const n = prompt("Имя чата:");
        if(n) socket.emit("create_room", {room: n, password: prompt("Пароль (пусто для всех):")});
    }
</script>
</body>
</html>
"""

def format_room_list():
    return [f"{name} {'[приват]' if info.get('private') else ''}".strip() for name, info in rooms.items()]

@app.route('/')
def index():
    if not session.get('username'): return redirect(url_for('register'))
    # Используем render_template_string вместо файла!
    return render_template_string(HTML_LAYOUT, username=session['username'])

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nick = request.form.get('nickname', '').strip()
        if 2 <= len(nick) <= 20:
            session['username'] = nick
            return redirect(url_for('index'))
    return '<form method="post" style="background:#0e1621;color:white;height:100vh;display:flex;justify-content:center;align-items:center;"><input name="nickname" placeholder="Никнейм"><button>Войти</button></form>'

@socketio.on('connect')
def on_connect():
    emit('room_list', format_room_list())

@socketio.on('create_room')
def on_create(data):
    name = data.get('room', '').strip()
    if name and name not in rooms:
        rooms[name] = {'owner': session['username'], 'private': bool(data.get('password')), 'password': data.get('password')}
        emit('room_list', format_room_list(), broadcast=True)

@socketio.on('join_room')
def on_join(data):
    room = data.get('room')
    join_room(room)
    session['room'] = room
    emit('room_joined', room)

@socketio.on('message')
def handle_msg(msg):
    room = session.get('room')
    if room: emit('message', f"{session['username']}: {msg}", to=room)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
