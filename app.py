import os, time
from flask import Flask, session, request, redirect, jsonify, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tg_ultra_secure_94488'

# --- ХРАНИЛИЩА ---
rooms_db = {}     
messages_db = {}  
users_auth = {}   # { nick: hash_password }
users_data = {}   # { nick: {invites: []} }

HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Telegram Secure X</title>
    <style>
        :root { --bg: #0e1621; --side: #17212b; --acc: #5288c1; --msg-in: #182533; --msg-out: #2b5278; --text: #f5f5f5; }
        
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        body, html { height: 100%; margin: 0; font-family: -apple-system, system-ui, sans-serif; background: var(--bg); color: var(--text); overflow: hidden; }

        /* АНИМАЦИИ */
        @keyframes msgSlide { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes blurIn { from { backdrop-filter: blur(0px); } to { backdrop-filter: blur(8px); } }

        .app-wrap { display: flex; height: 100vh; position: relative; transition: 0.3s; }
        
        /* SIDEBAR */
        .sidebar { width: 300px; background: var(--side); border-right: 1px solid #000; display: flex; flex-direction: column; z-index: 10; transition: 0.3s; }
        .room-item { padding: 14px 18px; border-bottom: 1px solid #0e1621; cursor: pointer; display: flex; align-items: center; gap: 12px; position: relative; transition: 0.2s; }
        .room-item:active { background: rgba(255,255,255,0.1); }
        .room-item.active { background: var(--acc); }
        .avatar { width: 45px; height: 45px; border-radius: 50%; background: linear-gradient(45deg, #5288c1, #2b5278); display: flex; align-items: center; justify-content: center; font-weight: bold; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }
        
        /* MAIN CHAT */
        .main { flex: 1; display: flex; flex-direction: column; background: var(--bg); z-index: 5; position: relative; transition: 0.3s; }
        .main.blur-mode { filter: blur(5px); pointer-events: none; }
        
        .header { background: var(--side); padding: 10px 15px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #000; min-height: 60px; }
        
        #chat { flex: 1; overflow-y: auto; padding: 15px; display: flex; flex-direction: column; gap: 10px; background-image: url('https://www.transparenttextures.com'); }
        .bubble { max-width: 85%; padding: 10px 14px; border-radius: 16px; word-wrap: break-word; animation: msgSlide 0.3s ease-out; position: relative; box-shadow: 0 1px 2px rgba(0,0,0,0.3); }
        .mine { align-self: flex-end; background: var(--msg-out); border-bottom-right-radius: 4px; }
        .other { align-self: flex-start; background: var(--msg-in); border-bottom-left-radius: 4px; }

        /* DRAWER (100% HIDDEN) */
        #drawer { 
            position: fixed; top: 0; left: 0; width: 280px; height: 100%; 
            background: var(--side); z-index: 1000; padding: 30px 20px; 
            box-shadow: 10px 0 30px #000; box-sizing: border-box;
            transform: translateX(-110%); transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }
        #drawer.open { transform: translateX(0); }
        .overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: none; z-index: 999; backdrop-filter: blur(4px); animation: fadeIn 0.3s; }

        /* ИНПУТЫ */
        .inp { background: #242f3d; border: none; padding: 12px 16px; border-radius: 25px; color: white; outline: none; font-size: 16px; width: 100%; }
        .input-bar { padding: 10px 15px; background: var(--side); display: flex; gap: 10px; align-items: center; }
        
        /* МОБИЛЬНАЯ АДАПТАЦИЯ */
        @media (max-width: 768px) {
    .sidebar { 
        display: none; /* Скрываем боковую панель совсем */
    }

    .main { 
        display: flex !important;
        flex-direction: column; /* Элементы идут сверху вниз */
        width: 100vw !important; 
        height: 100dvh !important; /* Высота ровно под экран */
        position: fixed;
        top: 0; 
        left: 0;
    }

    #chat {
        flex: 1; /* Чат забирает всё свободное место сверху */
        overflow-y: auto;
        -webkit-overflow-scrolling: touch;
    }

    .input-bar {
        position: relative; /* Панель всегда идет сразу после чата */
        background: var(--side);
        padding: 10px 15px;
        /* Учет безопасной зоны внизу (для iPhone с полоской) */
        padding-bottom: calc(10px + env(safe-area-inset-bottom));
        border-top: 1px solid #000;
        width: 100%;
        display: flex;
        z-index: 10;
    }

    .mobile-kb-btn {
        display: flex;
        position: fixed;
        right: 20px;
        bottom: 100px; /* Чуть выше панели ввода */
        z-index: 1001;
    }
}





        .btn-gear { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--acc); margin-top: 20px; transition: transform 0.5s; }
    </style>
</head>
<body>

<div class="overlay" id="overlay" onclick="toggleMenu()"></div>

<div id="drawer">
    <h3 style="color:var(--acc); margin-top:0;">Настройки</h3>
    <label style="font-size:12px; color:gray;">ВАШ ID (Защищен)</label>
    <input value="{{ username }}" class="inp" style="background:#1c252f; color:#8e959b; margin-top:5px;" readonly>
    
    <button class="btn-gear" onclick="toggleCustom()">Настройка вида</button>
    <div id="customPanel" style="display:none; margin-top:15px; padding:15px; background:#242f3d; border-radius:12px;">
        <button onclick="setTheme('default')" style="width:100%; padding:10px; margin-bottom:10px; border-radius:8px; border:none; background:#1c252f; color:white; cursor:pointer;">Оригинал</button>
        <button onclick="setTheme('gradient')" style="width:100%; padding:10px; border-radius:8px; border:none; background:linear-gradient(45deg, #5288c1, #2b5278); color:white; cursor:pointer;">Градиент</button>
    </div>
    <button onclick="location.href='/logout'" style="margin-top:40px; color:#ff4b4b; background:none; border:none; cursor:pointer; width:100%; text-align:left; padding:0;">Выйти из аккаунта</button>
</div>

<div class="app-wrap">
    <div class="sidebar" id="sidebar">
        <div style="padding:15px; display:flex; gap:15px; align-items:center; border-bottom:1px solid #0e1621;">
            <div onclick="toggleMenu()" style="cursor:pointer; font-size:22px;">☰</div>
            <b style="color:var(--acc); font-size:18px;">F-TOP</b>
        </div>
        <div style="flex:1; overflow-y:auto;">
            <div class="room-item {{ 'active' if current == 'BOT' else '' }}" onclick="location.href='/?room=BOT'">
                <div class="avatar">🤖</div>
                <div id="bot-dot" style="position:absolute; top:12px; right:12px; width:10px; height:10px; background:#ff4b4b; border-radius:50%; display:none; border:2px solid var(--side);"></div>
                <div><b>Бот</b><br><small>Инвайты</small></div>
            </div>
            {% for r_name in my_rooms %}
            <div class="room-item {{ 'active' if r_name == current else '' }}" onclick="location.href='/?room={{ r_name }}'">
                <div class="avatar">{{ r_name[:1].upper() }}</div>
                <div><b>{{ r_name }}</b></div>
            </div>
            {% endfor %}
        </div>
        <button onclick="createRoom()" style="margin:15px; padding:15px; background:var(--acc); border:none; color:white; border-radius:12px; cursor:pointer; font-weight:bold; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">+ СОЗДАТЬ ЧАТ</button>
    </div>

    <div class="main" id="mainChat">
        {% if current %}
        <div class="header">
            <div style="display:flex; align-items:center; gap:10px;">
                <div onclick="toggleMobileSidebar()" class="mobile-only" style="cursor:pointer; font-size:20px; display:none;">⬅️</div>
                <b>{{ current }}</b>
            </div>
            {% if current != 'BOT' %}<button onclick="inviteFriend()" style="background:none; border:none; color:var(--acc); cursor:pointer; font-weight:bold; font-size:14px;">➕ ИНВАЙТ</button>{% endif %}
        </div>
        <div id="chat"></div>
        {% if current != 'BOT' %}
        <div class="input-bar">
            <input type="file" id="imgInp" hidden onchange="sendPhoto(this)">
            <button onclick="document.getElementById('imgInp').click()" style="background:none; border:none; color:var(--acc); cursor:pointer; font-size:22px;">📎</button>
            <input id="msg" class="inp" placeholder="Сообщение..." onkeypress="if(event.key==='Enter') sendText()">
            <button onclick="sendText()" style="background:none; border:none; color:var(--acc); font-weight:bold; font-size:24px;">➤</button>
        </div>
        {% endif %}
        {% endif %}
    </div>
</div>

<script>
    const me = "{{ username }}";
    const activeRoom = "{{ current }}";

    // Плавное открытие меню
    function toggleMenu() {
        const d = document.getElementById('drawer');
        const o = document.getElementById('overlay');
        const m = document.getElementById('mainChat');
        d.classList.toggle('open');
        const isOpen = d.classList.contains('open');
        o.style.display = isOpen ? 'block' : 'none';
        if(isOpen) m.classList.add('blur-mode');
        else m.classList.remove('blur-mode');
    }

    function toggleMobileSidebar() {
        document.getElementById('sidebar').classList.toggle('mobile-open');
    }

    // Темы
    function setTheme(t) {
        const chat = document.getElementById("mainChat");
        if(t === 'gradient') {
            chat.style.background = "linear-gradient(135deg, #0e1621 0%, #1a2a3a 50%, #2b5278 100%)";
            localStorage.setItem("chatTheme", "gradient");
        } else {
            chat.style.background = "var(--bg)";
            localStorage.setItem("chatTheme", "default");
        }
    }

    async function loadData() {
        if(!activeRoom) return;
        const res = await fetch(`/sync?room=${activeRoom}`);
        const data = await res.json();
        
        if(data.has_invites) document.getElementById('bot-dot').style.display = 'block';
        else document.getElementById('bot-dot').style.display = 'none';

        const box = document.getElementById("chat");
        if(!box) return;

        if(activeRoom === 'BOT') {
            if(data.invites.length !== box.childElementCount) {
                box.innerHTML = "";
                data.invites.forEach(inv => {
                    const d = document.createElement("div"); d.className = "bubble other";
                    d.innerHTML = `<div class="invite-card" style="background:#242f3d; padding:10px; border-radius:10px; border:1px solid var(--acc);">
                        📩 <b>${inv.from}</b> приглашает в <b>${inv.room}</b><br><br>
                        <button onclick="acceptInvite('${inv.room}')" style="background:var(--acc); border:none; color:white; padding:8px; border-radius:8px; width:100%; cursor:pointer;">Принять вход</button>
                    </div>`;
                    box.appendChild(d);
                });
            }
        } else {
            if(data.messages.length !== box.childElementCount) {
                box.innerHTML = "";
                data.messages.forEach(m => {
                    const d = document.createElement("div");
                    d.className = "bubble " + (m.user === me ? "mine" : "other");
                    if(m.type === 'img') d.innerHTML = `<small style="color:var(--acc); font-size:10px;">${m.user}</small><br><img src="${m.msg}" style="max-width:100%; border-radius:10px;">`;
                    else d.innerHTML = `<small style="color:var(--acc); font-size:10px;">${m.user}</small><br>${m.msg}`;
                    box.appendChild(d);
                });
                box.scrollTop = box.scrollHeight;
            }
        }
    }

    async function sendText() {
        const i = document.getElementById("msg"); if(!i.value.trim()) return;
        const text = i.value; i.value = "";
        await fetch('/send_msg', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({room: activeRoom, msg: text, type: 'text'}) });
        loadData();
    }

    function sendPhoto(input) {
        const reader = new FileReader();
        reader.onload = async (e) => {
            await fetch('/send_msg', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({room: activeRoom, msg: e.target.result, type: 'img'}) });
            loadData();
        };
        reader.readAsDataURL(input.files);
    }

    function createRoom() {
        const n = prompt("Имя чата:");
        if(n) fetch('/create', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:n})}).then(() => location.href='/?room='+encodeURIComponent(n));
    }

    function inviteFriend() {
        const who = prompt("Ник друга:");
        if(who) fetch('/send_invite', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({to:who, room:activeRoom})}).then(r=>r.json()).then(d => alert(d.msg));
    }

    function acceptInvite(r) {
        fetch('/accept', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({room:r})}).then(() => location.href='/?room='+encodeURIComponent(r));
    }

    function toggleCustom() {
        const p = document.getElementById("customPanel");
        p.style.display = p.style.display === 'block' ? 'none' : 'block';
    }

    if(window.innerWidth <= 768) {
        document.querySelectorAll('.mobile-only').forEach(el => el.style.display = 'block');
    }

    if(activeRoom) { loadData(); setInterval(loadData, 2500); }
    if(localStorage.getItem("chatTheme") === 'gradient') setTheme('gradient');
</script>
</body>
</html>
"""

@app.route('/')
def index():
    if 'user' not in session: return redirect('/login')
    user, room = session['user'], request.args.get('room')
    my_rooms = [n for n, v in rooms_db.items() if user in v['members']]
    return render_template_string(HTML, username=user, my_rooms=my_rooms, current=room)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('nick').strip()
        p = request.form.get('pass').strip()
        if u in users_auth:
            if check_password_hash(users_auth[u], p):
                session['user'] = u
                return redirect('/')
            return '<body style="background:#0e1621;color:white;padding:20px;"><h2>Ошибка: Неверный пароль</h2><a href="/login" style="color:#5288c1">Назад</a></body>'
        else:
            users_auth[u] = generate_password_hash(p)
            users_data[u] = {'invites': []}
            session['user'] = u
            return redirect('/')
    return '''<body style="background:#0e1621;color:white;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;">
        <form method="POST" style="background:#17212b;padding:30px;border-radius:20px;display:flex;flex-direction:column;gap:15px;width:90%;max-width:350px;box-shadow:0 10px 30px rgba(0,0,0,0.5);">
            <h2 style="margin:0;color:#5288c1">Вход / Регистрация</h2>
            <input name="nick" placeholder="Никнейм" required style="padding:12px;border-radius:10px;border:none;background:#242f3d;color:white;outline:none;">
            <input name="pass" type="password" placeholder="Пароль" required style="padding:12px;border-radius:10px;border:none;background:#242f3d;color:white;outline:none;">
            <button style="padding:12px;border-radius:10px;border:none;background:#5288c1;color:white;font-weight:bold;cursor:pointer;">ВОЙТИ</button>
        </form></body>'''

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/sync')
def sync():
    room, user = request.args.get('room'), session.get('user')
    invites = users_data.get(user, {}).get('invites', [])
    if room == 'BOT': return jsonify({'invites': invites, 'has_invites': len(invites) > 0})
    return jsonify({'messages': messages_db.get(room, []), 'has_invites': len(invites) > 0})

@app.route('/send_msg', methods=['POST'])
def send_msg():
    data = request.json
    room, user = data['room'], session.get('user')
    if room in messages_db: messages_db[room].append({'user': user, 'msg': data['msg'], 'type': data['type']})
    return jsonify(success=True)

@app.route('/create', methods=['POST'])
def create():
    name = request.json.get('name').strip()
    if name and name not in rooms_db:
        rooms_db[name], messages_db[name] = {'members': [session['user']]}, []
    return jsonify(success=True)

@app.route('/send_invite', methods=['POST'])
def send_invite():
    target, room = request.json.get('to').strip(), request.json.get('room')
    if target in users_data:
        users_data[target]['invites'].append({'from': session['user'], 'room': room})
        return jsonify(msg="Инвайт отправлен!")
    return jsonify(msg="Юзер не найден.")

@app.route('/accept', methods=['POST'])
def accept():
    room, user = request.json.get('room'), session['user']
    if room in rooms_db and user not in rooms_db[room]['members']:
        rooms_db[room]['members'].append(user)
        users_data[user]['invites'] = [i for i in users_data[user]['invites'] if i['room'] != room]
    return jsonify(success=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))












