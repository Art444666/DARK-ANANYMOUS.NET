import os, time
from flask import Flask, session, request, redirect, jsonify, render_template_string

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tg_final_pro_94488'

# --- ХРАНИЛИЩА ---
rooms_db = {}     # { name: {owner, members: []} }
messages_db = {}  # { name: [ {user, msg, type} ] }
users_db = {}     # { username: {invites: []} }

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Telegram Absolute Pro</title>
    <style>
        :root { --bg: #0e1621; --side: #17212b; --acc: #5288c1; --msg-in: #182533; --msg-out: #2b5278; --text: #f5f5f5; }
        body, html { height: 100%; margin: 0; font-family: sans-serif; background: var(--bg); color: var(--text); overflow: hidden; }
        .app-wrap { display: flex; height: 100vh; position: relative; }
        
        /* SIDEBAR */
        .sidebar { width: 300px; background: var(--side); border-right: 1px solid #000; display: flex; flex-direction: column; z-index: 10; }
        .room-item { padding: 12px 15px; border-bottom: 1px solid #0e1621; cursor: pointer; display: flex; align-items: center; gap: 10px; position: relative; }
        .room-item.active { background: var(--acc); }
        .avatar { width: 40px; height: 40px; border-radius: 50%; background: #4b7db1; display: flex; align-items: center; justify-content: center; font-weight: bold; }
        
        /* ИНДИКАТОР НОВЫХ ИНВАЙТОВ */
        .dot { position: absolute; top: 12px; right: 12px; width: 10px; height: 10px; background: #ff4b4b; border-radius: 50%; display: none; border: 2px solid var(--side); }

        /* ЧАТ */
        .main { flex: 1; display: flex; flex-direction: column; background: #0e1621; z-index: 5; }
        .header { background: var(--side); padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #000; }
        #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 10px; }
        .bubble { max-width: 75%; padding: 10px; border-radius: 12px; word-wrap: break-word; }
        .mine { align-self: flex-end; background: var(--msg-out); }
        .other { align-self: flex-start; background: var(--msg-in); }
        .invite-card { background: #242f3d; padding: 10px; border-radius: 8px; border: 1px solid var(--acc); margin-top: 5px; }

        /* НАСТРОЙКИ (СКРЫТЫ НА 100%) */
        #drawer { 
            position: fixed; top: 0; left: 0; width: 280px; height: 100%; 
            background: var(--side); z-index: 1000; padding: 25px; 
            box-shadow: 10px 0 20px #000; box-sizing: border-box;
            transform: translateX(-105%); transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        #drawer.open { transform: translateX(0); }
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
        <label style="font-size:12px; color:gray;">ВАШ НИК</label>
        <input name="new_nick" value="{{ username }}" class="inp" style="width:100%; margin-top:5px;">
        <button type="submit" style="width:100%; margin-top:15px; background:var(--acc); border:none; color:white; padding:10px; border-radius:8px; cursor:pointer;">Сохранить</button>
    </form>
    <button onclick="toggleMenu()" style="margin-top:20px; color:gray; background:none; border:none; cursor:pointer;">Закрыть</button>
</div>

<div class="app-wrap">
    <div class="sidebar">
        <div style="padding:15px; display:flex; gap:15px; align-items:center;">
            <div onclick="toggleMenu()" style="cursor:pointer; font-size:22px;">☰</div>
            <b>Telegram Pro</b>
        </div>
        <div style="flex:1; overflow-y:auto;">
            <div class="room-item {{ 'active' if current == 'BOT' else '' }}" onclick="location.href='/?room=BOT'">
                <div class="avatar">🤖</div>
                <div id="bot-dot" class="dot"></div>
                <div><b>Бот</b><br><small id="bot-status">Уведомления</small></div>
            </div>
            {% for r_name in my_rooms %}
            <div class="room-item {{ 'active' if r_name == current else '' }}" onclick="location.href='/?room={{ r_name }}'">
                <div class="avatar">{{ r_name[:1].upper() }}</div>
                <div><b>{{ r_name }}</b></div>
            </div>
            {% endfor %}
        </div>
        <button onclick="createRoom()" style="margin:10px; padding:12px; background:var(--acc); border:none; color:white; border-radius:8px; cursor:pointer; font-weight:bold;">+ СОЗДАТЬ ЧАТ</button>
    </div>

    <div class="main">
        {% if current %}
        <div class="header">
            <b>{{ current }}</b>
            <div>
                {% if current != 'BOT' %}
                <button onclick="inviteFriend()" class="btn-acc">➕ Инвайт</button>
                {% endif %}
            </div>
        </div>
        <div id="chat"></div>
        {% if current != 'BOT' %}
        <div class="input-bar">
            <input type="file" id="imgInp" hidden onchange="sendPhoto(this)">
            <button onclick="document.getElementById('imgInp').click()" class="btn-acc">📎</button>
            <input id="msg" class="inp" placeholder="Написать..." onkeypress="if(event.key==='Enter') sendText()">
            <button onclick="sendText()" class="btn-acc">➤</button>
        </div>
        {% endif %}
        {% endif %}
    </div>
</div>

<script>
    const me = "{{ username }}";
    const activeRoom = "{{ current }}";

    function toggleMenu() {
        const d = document.getElementById('drawer');
        const o = document.getElementById('overlay');
        d.classList.toggle('open');
        o.style.display = d.classList.contains('open') ? 'block' : 'none';
    }

    async function sendText() {
        const i = document.getElementById("msg");
        if(!i.value.trim()) return;
        const text = i.value; i.value = "";
        await fetch('/send_msg', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({room: activeRoom, msg: text, type: 'text'})
        });
        loadData();
    }

    async function sendPhoto(input) {
        const reader = new FileReader();
        reader.onload = async (e) => {
            await fetch('/send_msg', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({room: activeRoom, msg: e.target.result, type: 'img'})
            });
            loadData();
        };
        reader.readAsDataURL(input.files);
    }

    async function loadData() {
        if(!activeRoom) return;
        const res = await fetch(`/sync?room=${activeRoom}`);
        const data = await res.json();
        const box = document.getElementById("chat");
        if(!box) return;

        // Показываем точку на боте если есть инвайты
        if(data.has_invites) { document.getElementById('bot-dot').style.display = 'block'; }
        else { document.getElementById('bot-dot').style.display = 'none'; }

        if(activeRoom === 'BOT') {
            if(data.invites.length !== box.childElementCount) {
                box.innerHTML = "";
                data.invites.forEach(inv => {
                    const div = document.createElement("div");
                    div.className = "bubble other";
                    div.innerHTML = `
                        <div class="invite-card">
                            📩 <b>${inv.from}</b> приглашает в <b>${inv.room}</b><br><br>
                            <button onclick="acceptInvite('${inv.room}')" style="background:var(--acc); border:none; color:white; padding:5px; border-radius:5px; cursor:pointer;">Принять</button>
                        </div>`;
                    box.appendChild(div);
                });
            }
        } else {
            if(data.messages.length !== box.childElementCount) {
                box.innerHTML = "";
                data.messages.forEach(m => {
                    const div = document.createElement("div");
                    div.className = "bubble " + (m.user === me ? "mine" : "other");
                    if(m.type === 'img') div.innerHTML = `<small style="color:var(--acc)">${m.user}</small><br><img src="${m.msg}" style="max-width:100%; border-radius:8px;">`;
                    else div.innerHTML = `<small style="color:var(--acc)">${m.user}</small><br>${m.msg}`;
                    box.appendChild(div);
                });
                box.scrollTop = box.scrollHeight;
            }
        }
    }

    function createRoom() {
        const n = prompt("Имя чата:");
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

    if(activeRoom) {
        loadData();
        setInterval(loadData, 2000);
    } else {
        // Если чат не выбран, всё равно проверяем инвайты для точки
        setInterval(async () => {
            const r = await fetch('/sync?room=CHECK');
            const d = await r.json();
            if(d.has_invites) document.getElementById('bot-dot').style.display = 'block';
            else document.getElementById('bot-dot').style.display = 'none';
        }, 3000);
    }
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
        session['user'] = u
        if u not in users_db: users_db[u] = {'invites': []}
        return redirect('/')
    return '<body style="background:#0e1621;color:white;display:flex;justify-content:center;align-items:center;height:100vh;"><form method="POST"><input name="nick" placeholder="Ник" required><button>Войти</button></form></body>'

@app.route('/sync')
def sync():
    room, user = request.args.get('room'), session.get('user')
    invites = users_db.get(user, {}).get('invites', [])
    has_invites = len(invites) > 0
    
    if room == 'BOT':
        return jsonify({'invites': invites, 'has_invites': has_invites})
    return jsonify({'messages': messages_db.get(room, []), 'has_invites': has_invites})

@app.route('/send_msg', methods=['POST'])
def send_msg():
    data = request.json
    room, user = data['room'], session.get('user')
    if room in messages_db:
        messages_db[room].append({'user': user, 'msg': data['msg'], 'type': data['type']})
    return jsonify(success=True)

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
        if not any(i['room'] == room for i in users_db[target]['invites']):
            users_db[target]['invites'].append({'from': session['user'], 'room': room})
            return jsonify(msg="Приглашение отправлено!")
        return jsonify(msg="Уже приглашен.")
    return jsonify(msg="Юзер не найден.")

@app.route('/accept', methods=['POST'])
def accept():
    room, user = request.json.get('room'), session['user']
    if room in rooms_db:
        if user not in rooms_db[room]['members']:
            rooms_db[room]['members'].append(user)
        users_db[user]['invites'] = [i for i in users_db[user]['invites'] if i['room'] != room]
    return jsonify(success=True)

@app.route('/change_nick', methods=['POST'])
def change_nick():
    session['user'] = request.form.get('new_nick')
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))


