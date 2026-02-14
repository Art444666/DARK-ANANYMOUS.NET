import os, time
from flask import Flask, session, request, redirect, jsonify, render_template_string
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tg_94488_forced'
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=20 * 1024 * 1024)

# Глобальная база
rooms_db = {} # { name: { password: '...', owner: '...' } }

HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Telegram Forced Beta</title>
    <script src="https://cdn.socket.io"></script>
    <style>
        :root { --bg: #0e1621; --side: #17212b; --acc: #5288c1; --msg-in: #182533; --msg-out: #2b5278; --text: #f5f5f5; }
        body, html { height: 100%; margin: 0; font-family: sans-serif; background: var(--bg); color: var(--text); overflow: hidden; }
        .app-container { display: flex; height: 100vh; }
        
        /* МЕНЮ */
        #drawer { position: fixed; left: -320px; top: 0; width: 300px; height: 100%; background: var(--side); z-index: 1001; transition: 0.3s; padding: 25px; box-sizing: border-box; box-shadow: 10px 0 20px #000; }
        #drawer.open { left: 0; }
        .overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: none; z-index: 1000; }

        /* САЙДБАР */
        .sidebar { width: 320px; background: var(--side); border-right: 1px solid #080a0d; display: flex; flex-direction: column; }
        .rooms-list { flex: 1; overflow-y: auto; }
        .room-item { padding: 12px 15px; border-bottom: 1px solid #0e1621; cursor: pointer; display: flex; align-items: center; gap: 12px; }
        .room-item.active { background: var(--acc); }
        .avatar { width: 45px; height: 45px; border-radius: 50%; background: var(--acc); display: flex; align-items: center; justify-content: center; font-weight: bold; }

        /* ЧАТ */
        .chat-window { flex: 1; display: flex; flex-direction: column; background: #0e1621; }
        .chat-header { background: var(--side); padding: 15px 20px; font-weight: bold; border-bottom: 1px solid #000; }
        #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 10px; }
        .bubble { max-width: 75%; padding: 10px; border-radius: 12px; }
        .mine { align-self: flex-end; background: var(--msg-out); }
        .other { align-self: flex-start; background: var(--msg-in); }

        .input-area { padding: 15px; background: var(--side); display: flex; gap: 10px; }
        .inp { flex: 1; background: #242f3d; border: none; padding: 10px; border-radius: 20px; color: white; outline: none; }
        .btn { background: none; border: none; color: var(--acc); cursor: pointer; font-weight: bold; font-size: 20px; }
    </style>
</head>
<body>

<div class="overlay" id="overlay" onclick="toggleMenu()"></div>
<div id="drawer">
    <h3>Настройки</h3>
    <form action="/change_nick" method="POST">
        <input name="new_nick" class="inp" value="{{ username }}" style="width:100%">
        <button type="submit" style="width:100%; margin-top:10px; background:var(--acc); border:none; color:white; padding:10px; border-radius:8px;">Сохранить</button>
    </form>
</div>

<div class="app-container">
    <div class="sidebar">
        <div style="padding:15px; display:flex; gap:15px;">
            <div onclick="toggleMenu()" style="cursor:pointer">☰</div>
            <b>Telegram</b>
        </div>
        <div class="rooms-list">
            {% for r_name, r_info in rooms.items() %}
            <div class="room-item {{ 'active' if r_name == current_room else '' }}" 
                 onclick="enterRoom('{{ r_name }}', {{ 'true' if r_info.password else 'false' }})">
                <div class="avatar">{{ r_name[:1].upper() }}</div>
                <div><b>{{ r_name }} {{ '🔐' if r_info.password else '' }}</b></div>
            </div>
            {% endfor %}
        </div>
        <button onclick="createRoom()" style="margin:10px; padding:10px; background:var(--acc); border:none; color:white; border-radius:8px;">+ Создать беседу</button>
    </div>

    <div class="chat-window">
        {% if current_room %}
        <div class="chat-header">{{ current_room }}</div>
        <div id="chat"></div>
        <div class="input-area">
            <input type="text" id="msg" class="inp" placeholder="Сообщение..." onkeypress="if(event.key==='Enter') send()">
            <button onclick="send()" class="btn">➤</button>
        </div>
        {% else %}
        <div style="flex:1; display:flex; align-items:center; justify-content:center; color:gray;">Выберите чат, чтобы начать общение</div>
        {% endif %}
    </div>
</div>

<script>
    const socket = io();
    const me = "{{ username }}";
    const room = "{{ current_room }}";

    if(room) {
        socket.emit('join', {room: room});
    }

    function toggleMenu() {
        const d = document.getElementById('drawer');
        d.classList.toggle('open');
        document.getElementById('overlay').style.display = d.classList.contains('open') ? 'block' : 'none';
    }

    function enterRoom(name, isPrivate) {
        let pass = isPrivate ? prompt("Введите пароль:") : "";
        if(isPrivate && pass === null) return;
        window.location.href = "/?room=" + encodeURIComponent(name) + "&pass=" + encodeURIComponent(pass);
    }

    async function createRoom() {
        const n = prompt("Имя беседы:");
        if(!n) return;
        const p = prompt("Пароль (ок если не нужен):");
        const res = await fetch('/create_room', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: n, password: p})
        });
        if(res.ok) window.location.href = "/?room=" + n;
    }

    function send() {
        const i = document.getElementById("msg");
        if(i.value.trim()) {
            socket.emit('message', {room: room, msg: i.value});
            i.value = "";
        }
    }

    socket.on('chat_msg', (data) => {
        const chat = document.getElementById("chat");
        const b = document.createElement("div");
        b.className = "bubble " + (data.user === me ? "mine" : "other");
        b.innerHTML = `<b>${data.user}:</b><br>${data.msg}`;
        chat.appendChild(b);
        chat.scrollTop = chat.scrollHeight;
    });
</script>
</body>
</html>
"""

@app.route('/')
def index():
    if 'user' not in session: return redirect('/login')
    
    current_room = request.args.get('room')
    password = request.args.get('pass', '')

    # Принудительная проверка пароля при входе
    if current_room in rooms_db:
        r_info = rooms_db[current_room]
        if r_info['password'] and r_info['password'] != password:
            return "<script>alert('Неверный пароль!'); window.location.href='/';</script>"
    else:
        current_room = None

    return render_template_string(HTML_LAYOUT, 
                                username=session['user'], 
                                rooms=rooms_db, 
                                current_room=current_room)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['user'] = request.form.get('nick')
        return redirect('/')
    return '<body style="background:#0e1621; color:white; display:flex; align-items:center; justify-content:center; height:100vh;"><form method="POST"><input name="nick" required placeholder="Ник"><button>Войти</button></form></body>'

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
    session['user'] = request.form.get('new_nick')
    return redirect('/')

@socketio.on('join')
def on_join(data):
    join_room(data['room'])

@socketio.on('message')
def handle_msg(data):
    emit('chat_msg', {'user': session['user'], 'msg': data['msg']}, to=data['room'])

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))










