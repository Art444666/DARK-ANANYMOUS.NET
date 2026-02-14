import os, random
from flask import Flask, session, request, redirect, url_for, render_template_string
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tg_94488'
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# --- КОНСТРУКТОР ДИЗАЙНА (HTML + CSS) ---
INDEX_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Telegram Anonymous</title>
    <script src="https://cdn.socket.io"></script>
    <style>
        :root {
            --bg-dark: #0e1621; --bg-side: #17212b; --accent: #5288c1;
            --text: #f5f5f5; --msg-out: #2b5278; --msg-in: #182533;
        }
        body, html { height: 100%; margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto; background: var(--bg-dark); color: var(--text); overflow: hidden; }

        /* ОСНОВНАЯ СЕТКА */
        .app-container { display: flex; height: 100vh; width: 100vw; }

        /* САЙДБАР (ЛЕВО) */
        .sidebar { width: 300px; background: var(--bg-side); border-right: 1px solid #080a0d; display: flex; flex-direction: column; position: relative; }
        .sidebar-header { padding: 10px 15px; display: flex; align-items: center; gap: 10px; }
        .search-input { flex: 1; background: #242f3d; border: none; border-radius: 10px; padding: 8px 12px; color: white; outline: none; font-size: 14px; }
        
        /* СПИСОК ЧАТОВ */
        .chats-list { flex: 1; overflow-y: auto; }
        .chat-item { padding: 10px 15px; display: flex; align-items: center; gap: 12px; cursor: pointer; transition: 0.2s; }
        .chat-item:hover { background: #232e3c; }
        .chat-item.active { background: var(--accent); }
        .avatar { width: 45px; height: 45px; border-radius: 50%; background: #5288c1; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 18px; }

        /* ОКНО ЧАТА (ПРАВО) */
        .chat-window { flex: 1; display: flex; flex-direction: column; background: url('https://www.transparenttextures.com'); background-color: var(--bg-dark); }
        .chat-header { background: var(--bg-side); padding: 10px 20px; display: flex; align-items: center; gap: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.3); }
        
        #messages { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 8px; }
        
        /* ПУЗЫРИ СООБЩЕНИЙ */
        .message { max-width: 70%; padding: 8px 12px; border-radius: 12px; font-size: 15px; line-height: 1.4; position: relative; animation: slideUp 0.2s ease; }
        .message.mine { align-self: flex-end; background: var(--msg-out); border-bottom-right-radius: 2px; }
        .message.other { align-self: flex-start; background: var(--msg-in); border-bottom-left-radius: 2px; }
        
        /* ПАНЕЛЬ ВВОДА */
        .input-panel { padding: 10px 20px; background: var(--bg-side); display: flex; align-items: center; gap: 12px; }
        .msg-input { flex: 1; background: transparent; border: none; color: white; outline: none; font-size: 15px; }
        .btn-send { color: var(--accent); cursor: pointer; font-weight: bold; background: none; border: none; font-size: 18px; }

        /* КНОПКА СОЗДАНИЯ */
        .fab { position: absolute; bottom: 20px; right: 20px; width: 50px; height: 50px; border-radius: 50%; background: var(--accent); border: none; color: white; font-size: 24px; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.4); transition: 0.3s; }
        .fab:hover { transform: scale(1.1) rotate(90deg); }

        @keyframes slideUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body>

<div class="app-container">
    <div class="sidebar">
        <div class="sidebar-header">
            <div style="cursor:pointer; font-size: 20px;" onclick="alert('Меню Настроек')">☰</div>
            <input type="text" class="search-input" placeholder="Поиск" oninput="filterRooms(this.value)">
        </div>
        <div class="chats-list" id="roomList"></div>
        <button class="fab" onclick="createRoom()">+</button>
    </div>

    <div class="chat-window">
        <div class="chat-header">
            <div class="avatar" id="h-av" style="width:35px; height:35px; font-size:14px;">?</div>
            <div id="h-name" style="font-weight:bold">Выберите чат</div>
        </div>
        <div id="messages"></div>
        <div class="input-panel" id="inputSection" style="display:none">
            <div style="cursor:pointer; color:var(--accent); font-size: 20px;">📎</div>
            <input type="text" id="m-inp" class="msg-input" placeholder="Написать сообщение..." onkeypress="if(event.key==='Enter') sendMsg()">
            <button class="btn-send" onclick="sendMsg()">➤</button>
        </div>
    </div>
</div>

<script>
    const socket = io();
    const myName = "{{ username }}";
    let activeRoom = null;

    function createRoom() {
        const n = prompt("Название чата:");
        if(n) socket.emit('create_room', {room: n, password: ''});
    }

    function sendMsg() {
        const i = document.getElementById("m-inp");
        if(i.value.trim()) {
            socket.emit('message', i.value);
            i.value = "";
        }
    }

    socket.on('room_list', (rooms) => {
        const container = document.getElementById("roomList");
        container.innerHTML = "";
        rooms.forEach(r => {
            const name = r.replace(" [приват]", "");
            const div = document.createElement("div");
            div.className = "chat-item";
            div.onclick = () => socket.emit('join_room', {room: name});
            div.innerHTML = `<div class="avatar">${name[0].toUpperCase()}</div><div><b>${name}</b></div>`;
            container.appendChild(div);
        });
    });

    socket.on('room_joined', (name) => {
        activeRoom = name;
        document.getElementById("h-name").innerText = name;
        document.getElementById("h-av").innerText = name[0].toUpperCase();
        document.getElementById("inputSection").style.display = "flex";
        document.getElementById("messages").innerHTML = "";
    });

    socket.on('message', (data) => {
        const chat = document.getElementById("messages");
        const div = document.createElement("div");
        const isMine = data.startsWith(myName + ":");
        div.className = "message " + (isMine ? "mine" : "other");
        div.innerHTML = `<b>${data.split(':')[0]}</b><br>${data.split(':').slice(1).join(':')}`;
        chat.appendChild(div);
        chat.scrollTop = chat.scrollHeight;
    });

    function filterRooms(v) {
        document.querySelectorAll(".chat-item").forEach(i => {
            i.style.display = i.innerText.toLowerCase().includes(v.toLowerCase()) ? "flex" : "none";
        });
    }
</script>
</body>
</html>
"""

# --- СЕРВЕРНАЯ ЛОГИКА ---
rooms = {}

@app.route('/')
def index():
    if 'username' not in session: return redirect(url_for('reg'))
    return render_template_string(INDEX_HTML, username=session['username'])

@app.route('/reg', methods=['GET', 'POST'])
def reg():
    if request.method == 'POST':
        session['username'] = request.form.get('nick')
        return redirect(url_for('index'))
    return '<body style="background:#0e1621; color:white; display:flex; align-items:center; justify-content:center; height:100vh; font-family:sans-serif;"><form method="POST"><h2>Вход в чат</h2><input name="nick" placeholder="Никнейм" required style="padding:10px; border-radius:5px;"><button style="padding:10px; margin-left:5px; background:#5288c1; color:white; border:none; border-radius:5px;">Войти</button></form></body>'

@socketio.on('connect')
def connect():
    emit('room_list', list(rooms.keys()))

@socketio.on('create_room')
def create(data):
    name = data['room']
    rooms[name] = True
    emit('room_list', list(rooms.keys()), broadcast=True)

@socketio.on('join_room')
def join(data):
    room = data['room']
    join_room(room)
    session['room'] = room
    emit('room_joined', room)

@socketio.on('message')
def msg(val):
    room = session.get('room')
    if room: emit('message', f"{session['username']}: {val}", to=room)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)


