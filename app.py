import os, time
from flask import Flask, session, request, redirect, jsonify, render_template_string
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tg_ultra_94488'
# Поддержка фото до 15МБ
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=15 * 1024 * 1024)

# База данных в памяти
rooms_db = {} # { name: { password: '...', owner: '...' } }

HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Telegram Clone Pro</title>
    <script src="https://cdn.socket.io"></script>
    <style>
        :root { --bg: #0e1621; --side: #17212b; --acc: #5288c1; --msg-in: #182533; --msg-out: #2b5278; --text: #f5f5f5; }
        body, html { height: 100%; margin: 0; font-family: -apple-system, system-ui, sans-serif; background: var(--bg); color: var(--text); overflow: hidden; }
        
        .app-container { display: flex; height: 100vh; width: 100vw; position: relative; }

        /* ВЫДВИЖНОЕ МЕНЮ (ПОЛНОСТЬЮ СКРЫТО) */
        #drawer {
            position: fixed; left: -320px; top: 0; width: 300px; height: 100%;
            background: var(--side); z-index: 1001; transition: 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 10px 0 20px rgba(0,0,0,0.5); padding: 25px; box-sizing: border-box;
        }
        #drawer.open { left: 0; }
        .overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: none; z-index: 1000; backdrop-filter: blur(2px); }

        /* САЙДБАР */
        .sidebar { width: 320px; background: var(--side); border-right: 1px solid #080a0d; display: flex; flex-direction: column; position: relative; }
        .sb-header { padding: 15px; display: flex; align-items: center; gap: 15px; border-bottom: 1px solid #0e1621; }
        .rooms-list { flex: 1; overflow-y: auto; }
        .room-item { padding: 12px 15px; display: flex; align-items: center; gap: 12px; cursor: pointer; transition: 0.2s; border-bottom: 1px solid #0e1621; }
        .room-item:hover { background: rgba(255,255,255,0.05); }
        .room-item.active { background: var(--acc); }
        .avatar { width: 45px; height: 45px; border-radius: 50%; background: var(--acc); display: flex; align-items: center; justify-content: center; font-weight: bold; }

        /* ЧАТ */
        .chat-window { flex: 1; display: flex; flex-direction: column; background: #0e1621 url('https://www.transparenttextures.com'); }
        .chat-header { background: var(--side); padding: 10px 20px; display: flex; align-items: center; gap: 15px; border-bottom: 1px solid #000; }
        #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 10px; }
        
        .bubble { max-width: 75%; padding: 8px 14px; border-radius: 12px; animation: slideUp 0.2s; position: relative; word-wrap: break-word; }
        .mine { align-self: flex-end; background: var(--msg-out); border-bottom-right-radius: 2px; }
        .other { align-self: flex-start; background: var(--msg-in); border-bottom-left-radius: 2px; }
        
        .input-area { background: var(--side); padding: 12px 20px; display: flex; align-items: center; gap: 12px; }
        .inp { flex: 1; background: #242f3d; border: none; padding: 10px 15px; border-radius: 20px; color: white; outline: none; }
        
        .btn-tg { background: none; border: none; color: var(--acc); cursor: pointer; font-weight: bold; font-size: 16px; }
        .fab { position: absolute; bottom: 25px; right: 20px; width: 50px; height: 50px; border-radius: 50%; background: var(--acc); border: none; color: white; font-size: 24px; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.5); z-index: 10; }

        @keyframes slideUp { from { opacity: 0; transform: translateY(10px); } }
    </style>
</head>
<body>

<div class="overlay" id="overlay" onclick="toggleMenu()"></div>

<div id="drawer">
    <h2 style="color: var(--acc); margin-top: 0;">Настройки</h2>
    <form action="/change_nick" method="POST">
        <label style="font-size: 12px; color: #8e959b;">ВАШ НИК</label>
        <input name="new_nick" class="inp" style="width: 100%; margin-top: 8px; box-sizing: border-box;" value="{{ username }}">
        <button type="submit" style="width: 100%; margin-top: 15px; background: var(--acc); border: none; padding: 10px; border-radius: 8px; color: white; cursor: pointer;">Сохранить</button>
    </form>
    <hr style="border: 0.5px solid #242f3d; margin: 30px 0;">
    <button onclick="adminLogin()" class="btn-tg" style="color: #ff6b6b;">🔑 Админ-панель</button>
</div>

<div class="app-container">
    <div class="sidebar">
        <div class="sb-header">
            <div onclick="toggleMenu()" style="cursor:pointer; font-size: 22px;">☰</div>
            <b style="color:var(--acc)">Telegram</b>
        </div>
        <div class="rooms-list">
            {% for r_name, r_info in rooms.items() %}
            <div class="room-item" id="item-{{ r_name }}" onclick="requestJoin('{{ r_name }}', {{ 'true' if r_info.password else 'false' }})">
                <div class="avatar">{{ r_name[:1] | upper }}</div>
                <div style="flex:1">
                    <div style="font-weight: bold;">{{ r_name }} {{ '🔐' if r_info.password else '' }}</div>
                    <div style="font-size: 12px; color: #8e959b;">нажмите, чтобы войти</div>
                </div>
            </div>
            {% endfor %}
        </div>
        <button class="fab" onclick="createRoom()">+</button>
    </div>

    <div class="chat-window">
        <div class="chat-header">
            <div class="avatar" id="h-av" style="width: 35px; height: 35px; font-size: 14px;">?</div>
            <div id="h-name" style="font-weight: bold;">Выберите чат</div>
        </div>
        <div id="chat"></div>
        <div class="input-area" id="inputBox" style="display: none;">
            <input type="file" id="f-inp" hidden onchange="uploadPhoto(this)">
            <button onclick="document.getElementById('f-inp').click()" class="btn-tg" style="font-size: 20px;">📎</button>
            <input type="text" id="msg" class="inp" placeholder="Написать сообщение..." onkeypress="if(event.key==='Enter') send()">
            <button onclick="send()" class="btn-tg" style="font-size: 24px;">➤</button>
        </div>
    </div>
</div>

<script>
    const socket = io();
    const myNick = "{{ username }}";
    let currentRoom = "";

    function toggleMenu() {
        document.getElementById('drawer').classList.toggle('open');
        document.getElementById('overlay').style.display = 
            document.getElementById('drawer').classList.contains('open') ? 'block' : 'none';
    }

    async function createRoom() {
        const name = prompt("Название беседы:");
        if(!name) return;
        const pass = prompt("Пароль (пусто, если не нужен):");
        
        const res = await fetch('/create_room', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: name, password: pass})
        });
        if(res.ok) location.reload();
        else alert("Ошибка при создании");
    }

    function requestJoin(name, isPrivate) {
        let pass = "";
        if(isPrivate) {
            pass = prompt("Введите пароль для входа:");
            if(pass === null) return;
        }
        socket.emit('join', {room: name, password: pass});
    }

    socket.on('join_status', (data) => {
        if(data.success) {
            currentRoom = data.room;
            document.getElementById("h-name").innerText = data.room;
            document.getElementById("h-av").innerText = data.room.substring(0,1).toUpperCase();
            document.getElementById("inputBox").style.display = "flex";
            document.getElementById("chat").innerHTML = "";
            
            document.querySelectorAll('.room-item').forEach(i => i.classList.remove('active'));
            document.getElementById("item-" + data.room).classList.add('active');
        } else {
            alert(data.message);
        }
    });

    function send() {
        const i = document.getElementById("msg");
        if(i.value.trim() && currentRoom) {
            socket.emit('message', {room: currentRoom, msg: i.value});
            i.value = "";
        }
    }

    function uploadPhoto(input) {
        const reader = new FileReader();
        reader.onload = (e) => socket.emit('message', {room: currentRoom, msg: 'PHOTO:' + e.target.result});
        reader.readAsDataURL(input.files[0]);
    }

    socket.on('chat_msg', (data) => {
        const chat = document.getElementById("chat");
        const b = document.createElement("div");
        b.className = "bubble " + (data.user === myNick ? "mine" : "other");
        
        if(data.msg.startsWith('PHOTO:')) {
            const src = data.msg.replace('PHOTO:', '');
            b.innerHTML = `<small style="color:var(--acc)">${data.user}</small><br><img src="${src}" style="max-width:100%; border-radius:8px; margin-top:5px;">`;
        } else {
            b.innerHTML = `<small style="color:var(--acc)">${data.user}</small><br>${data.msg}`;
        }
        chat.appendChild(b);
        chat.scrollTop = chat.scrollHeight;
    });

    function adminLogin() {
        if(prompt("Пароль админа:") === "94488") alert("Режим админа!");
    }
</script>
</body>
</html>
"""

@app.route('/')
def index():
    if 'user' not in session: return redirect('/login')
    return render_template_string(HTML_LAYOUT, username=session['user'], rooms=rooms_db)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['user'] = request.form.get('nick')
        return redirect('/')
    return '<body style="background:#0e1621; color:white; display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh; font-family:sans-serif;"><form method="POST"><h2>Вход в Telegram Beta</h2><input name="nick" required placeholder="Ваш ник" style="padding:10px; border-radius:8px; border:none;"><br><button style="margin-top:10px; background:#5288c1; color:white; border:none; padding:10px 20px; border-radius:8px; cursor:pointer;">Войти</button></form></body>'

@app.route('/change_nick', methods=['POST'])
def change_nick():
    new = request.form.get('new_nick')
    if new: session['user'] = new
    return redirect('/')

@app.route('/create_room', methods=['POST'])
def create():
    data = request.json
    name = data.get('name', '').strip()
    password = data.get('password', '').strip()
    if name and name not in rooms_db:
        rooms_db[name] = {'owner': session.get('user'), 'password': password}
        return jsonify(success=True)
    return jsonify(success=False), 400

@socketio.on('join')
def on_join(data):
    room = data.get('room')
    password = data.get('password')
    
    if room in rooms_db:
        # Проверка пароля
        correct_pass = rooms_db[room]['password']
        if correct_pass and correct_pass != password:
            emit('join_status', {'success': False, 'message': '❌ Неверный пароль!'})
            return
        
        # Переключение комнат
        old_room = session.get('current_room')
        if old_room: leave_room(old_room)
        
        join_room(room)
        session['current_room'] = room
        emit('join_status', {'success': True, 'room': room})
    else:
        emit('join_status', {'success': False, 'message': '❌ Комната не найдена'})

@socketio.on('message')
def handle_msg(data):
    room = data.get('room')
    msg = data.get('msg')
    if room == session.get('current_room'):
        emit('chat_msg', {'user': session['user'], 'msg': msg}, to=room)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)








