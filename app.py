import os, time
from flask import Flask, session, request, redirect, jsonify, render_template_string, render_template
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__, template_folder=".")
socketio = SocketIO(app, cors_allowed_origins="*")
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
    <title>F-TOP</title>
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





        .btn-gear { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--acc); margin-top: 20px; transition: transform 0.5s; }

       /* Оверлей для большого окна */
.modal-overlay {
    display: none;
    position: fixed;
    top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0, 0, 0, 0.7);
    backdrop-filter: blur(5px);
    z-index: 2000;
    justify-content: center;
    align-items: center;
}

/* Контент большого окна */
.modal-content {
    background: var(--side);
    padding: 25px;
    border-radius: 20px;
    width: 90%;
    max-width: 400px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    border: 1px solid var(--acc);
    animation: zoomIn 0.3s ease;
}

@keyframes zoomIn {
    from { transform: scale(0.8); opacity: 0; }
    to { transform: scale(1); opacity: 1; }
}

.btn-theme-opt {
    width: 100%; padding: 12px; border-radius: 8px; border: none;
    color: white; cursor: pointer; font-weight: bold; transition: 0.2s;
}
.btn-theme-opt:hover { transform: translateY(-2px); filter: brightness(1.2); }


/* КНОПКИ МЕНЮ */
.btn-gear {
    width: 100%;
    padding: 12px;
    background: #242f3d;
    border: 1px solid transparent;
    color: white;
    border-radius: 10px;
    cursor: pointer;
    font-weight: bold;
    display: flex;
    align-items: center;
    gap: 10px;
    transition: 0.3s;
}

.btn-gear:hover {
    border-color: var(--acc);
    background: #2b394a;
}

/* Иконки в кнопках */
.btn-gear .icon {
    display: inline-block;
    transition: 0.5s;
}

.btn-gear:hover .spin-icon {
    transform: rotate(90deg);
}

/* Опции тем */
.btn-theme-opt {
    width: 100%;
    padding: 10px;
    border-radius: 8px;
    border: none;
    color: white;
    cursor: pointer;
    font-weight: 500;
    transition: transform 0.2s;
}

.btn-theme-opt:active {
    transform: scale(0.95);
}

.separator {
    border: none;
    border-top: 1px solid #242f3d;
    margin: 15px 0;
}

    </style>
<style>
.separator {
    border: none;               /* Убираем стандартную рамку */
    border-top: 1px solid #1c252f; /* Цвет линии (чуть светлее фона) */
    margin: 20px 0;             /* Отступы сверху и снизу */
    width: 100%;                /* Растягиваем на всю ширину */
    opacity: 1;               /* Делаем чуть прозрачной */
}

/* АНИМАЦИЯ КРЕСТИКА */
.close-btn-spin {
    background: none;
    border: none;
    color: #8e959b;
    cursor: pointer;
    font-size: 26px;
    line-height: 1;
    transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    width: 32px; height: 32px;
    display: flex; align-items: center; justify-content: center;
}

.close-btn-spin:hover {
    color: #ff4b4b !important;
    transform: rotate(90deg) scale(1.2);
}
</style>

<style>
.cta {
  position: relative;
  margin: auto;
  padding: 12px 18px;
  transition: all 0.2s ease;
  border: none;
  background: none;
  cursor: pointer;
}

.cta:before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  border-radius: 50px;
  background: #234567;
  width: 45px;
  height: 45px;
  transition: all 0.3s ease;
  display: block;
  overflow: hidden;
  z-index: 1;
}

.cta::after {
  content: "Пользователи";
  position: absolute;
  top: 0;
  left: 0;
  border-radius: 50px;
  background: #fff;
  width: 9px;
  height: 21px;
  transition: all 0.3s ease;
  font-family: "Ubuntu", sans-serif;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.05em;
  white-space: nowrap;
  padding: 12px 18px;
  z-index: 2;
  color: transparent;
  -webkit-background-clip: text;
  background-clip: text;
  text-align: left;
}

.cta span {
  position: relative;
  font-family: "Ubuntu", sans-serif;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: #234567;
}

.cta svg {
  position: relative;
  top: 0;
  margin-left: 10px;
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke: #234567;
  stroke-width: 2;
  transform: translateX(-5px);
  transition: all 0.3s ease;
  z-index: 2;
}

.cta:hover:before {
  width: 100%;
}
.cta:hover::after {
  width: 100%;
}

.cta:hover svg {
  transform: translateX(0);
  stroke: #fff;
}

.cta:active {
  transform: scale(0.95);
}
</style>

<style>
    /* Панель эмодзи */
.emoji-picker {
    display: none;
    position: absolute;
    bottom: 70px;
    left: 15px;
    width: 250px;
    height: 150px;
    background: var(--side);
    border: 1px solid #000;
    border-radius: 12px;
    padding: 10px;
    z-index: 100;
    overflow-y: auto;
    box-shadow: 0 5px 20px rgba(0,0,0,0.5);
}
.emoji-picker span {
    font-size: 24px;
    cursor: pointer;
    padding: 5px;
    display: inline-block;
    transition: transform 0.1s;
}
.emoji-picker span:hover { transform: scale(1.2); }

.theme-panel {
    display: none; /* Скрыто по умолчанию */
    flex-direction: column;
    gap: 10px;
    margin-top: 15px;
    padding: 12px;
    background: #242f3d;
    border-radius: 14px;
    border: 1px solid rgba(82, 136, 193, 0.2);
    /* Анимация появления */
    animation: slideDown 0.3s ease-out;
}

/* Класс, который мы будем добавлять через JS */
.theme-panel.active {
    display: flex;
}

.btn-theme-opt {
    width: 100%;
    height: 40px;
    border-radius: 10px;
    border: 2px solid transparent;
    color: white;
    font-weight: bold;
    cursor: pointer;
    transition: all 0.2s ease;
    text-shadow: 0 1px 3px rgba(0,0,0,0.5);
}

.btn-theme-opt:hover {
    transform: scale(1.02);
    border-color: var(--acc);
}

.btn-theme-opt:active {
    transform: scale(0.98);
}

@keyframes slideDown {
    from { opacity: 0; transform: translateY(-10px); }
    to { opacity: 1; transform: translateY(0); }
}

</style>

<script src="https://unpkg.com"></script>
</head>
<body>

<div id="drawer">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h3 style="color:var(--acc); margin:0;">Настройки</h3>
        <button class="close-btn-spin" onclick="toggleMenu()">✕</button>
    </div>

    <label style="font-size:12px; color:gray;">ВАШ ID (Защищен)</label>
    <input value="{{ username }}" class="inp" style="background:#1c252f; color:#8e959b; margin: 5px 0 15px 0;" readonly>

    <hr class="separator">

    <!-- Твои кнопки настроек -->
    <button class="btn-gear" onclick="toggleCustom()">⚙️ Настройка вида</button>
    
    <div id="customPanel" class="theme-panel">
    <button onclick="setTheme('default')" class="btn-theme-opt" style="background:#1c252f;">Оригинал</button>
    <button onclick="setTheme('gradient')" class="btn-theme-opt" style="background:linear-gradient(135deg, #0e1621, #2b5278);">Классика</button>
    <button onclick="setTheme('sunset')" class="btn-theme-opt" style="background:linear-gradient(135deg, #42275a, #734b6d);">Закат</button>
    <button onclick="setTheme('ocean')" class="btn-theme-opt" style="background:linear-gradient(135deg, #000428, #004e92);">Океан</button>
    <button onclick="setTheme('emerald')" class="btn-theme-opt" style="background:linear-gradient(135deg, #093028, #237a57);">Изумруд</button>
    <button onclick="setTheme('midnight')" class="btn-theme-opt" style="background:linear-gradient(135deg, #0f2027, #2c5364);">Полночь</button>
    <button onclick="setTheme('neon')" class="btn-theme-opt" style="background:linear-gradient(135deg, #6441a5, #2a0845);">Неон</button>
</div>


    <hr class="separator">

     <button onclick="location.href='/logout'" style="margin-top:20px; color:#ff4b4b; background:none; border:none; cursor:pointer; width:100%; text-align:left; font-weight:bold; padding:0;">Выйти из аккаунта</button>

</div>


<style>
    .button {
  position: relative;
  width: 10rem;
  height: 3rem;
  cursor: pointer;
  border: none;
  background: none;
}

.button svg {
  width: 100%;
  height: 100%;
  overflow: visible;
}

.border {
  width: 100%;
  height: 100%;
  stroke: black;
  stroke-width: 2px;
  fill: #0000;
  rx: 1em;
  ry: 1em;
  stroke-dasharray: 25;
  transition: fill 0.25s;
  animation: 4s linear infinite stroke-animation;
}

.button:hover .border {
  fill: #0001;
}

.button:focus .border {
  transition: fill 0.25s 7.75s;
  fill: #0000;
}

@keyframes stroke-animation {
  0% {
    stroke-dashoffset: 100;
  }
  to {
    stroke-dashoffset: 0;
  }
}

.txt-upload {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.txt-upload::after {
  content: "";
}

.button:focus .rect {
  stroke-dasharray: 50;
}
.button:focus .border {
  stroke: #0000;
}

.button:focus .txt-upload {
  opacity: 0;
  transition: opacity 0.25s 8s;
}

.button:focus .txt-upload::after {
  animation: 0.66666s anim step-end forwards,
    1.33333s 0.6666s anim2 linear infinite alternate;
}

@keyframes anim {
  0% {
    content: "i";
  }
  50% {
    content: "in";
  }
  to {
    content: "ing";
  }
}

@keyframes anim2 {
  0% {
    content: "ing";
  }
  33% {
    content: "ing.";
  }
  66% {
    content: "ing..";
  }
  to {
    content: "ing...";
  }
}

.loading {
  width: 100%;
  height: 100%;
  stroke: #0055d4;
  stroke-width: 2px;
  fill: none;
  rx: 1em;
  ry: 1em;
  stroke-dasharray: 0 100;
}

.button:focus .loading {
  transition: stroke 0.5s 7.5s, stroke-dasharray 8s 0.5s ease-out;
  stroke: #08ca08;
  stroke-dasharray: 100 0;
}

.done {
  fill: none;
  stroke: #000;
  stroke-dasharray: 0 100;
}

.button:focus .done-cloud {
  transition: stroke-dasharray 0.75s 8.5s ease-out;
  stroke-dasharray: 100 0;
}

.button:focus .done-check {
  transition: stroke-dasharray 0.5s 9.2s ease-out;
  stroke: #08ca08;
  stroke-dasharray: 100 0;
}
.btn-spin {
    transition: all 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275); /* Пружинистый эффект */
}

.btn-spin:hover {
    transform: rotate(360deg) scale(1.1); /* Прокрутка на 360 градусов и увеличение */
    box-shadow: 0 0 20px var(--acc); /* Свечение в цвет темы */
}

.btn-spin:active {
    transform: scale(0.9) rotate(0deg); /* Сжатие при клике */
}

/* Чтобы плюс внутри тоже вращался ровно */
.btn-spin span {
    display: block;
    line-height: 0;
}
</style>

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
        <button class="btn-spin" onclick="createRoom()" style="margin:15px; width:55px; height:55px; background:var(--acc); border:none; color:white; border-radius:50%; cursor:pointer; font-weight:bold; box-shadow: 0 4px 15px rgba(0,0,0,0.4); display: flex; align-items:center; justify-content:center; font-size: 24px;">
        <span>+</span>
        </button>

    </div>

    <div class="main" id="mainChat">
        {% if current %}
        <div class="header">
            <div style="display:flex; align-items:center; gap:10px;">
                <div onclick="toggleMobileSidebar()" class="mobile-only" style="cursor:pointer; font-size:20px; display:none;">⬅️</div>
                <b>{{ current }}</b>
            </div>

            <button onclick="openRoomCall()" style="background:none; border:none; color:var(--acc); cursor:pointer; font-size:22px;">📞</button>

            
<!-- Окно звонка -->
<div id="callInterface" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.9); z-index:2000; flex-direction:column; align-items:center; justify-content:center; gap:20px;">
    <div style="display:flex; gap:10px;">
        <video id="remoteVideo" autoplay style="width:300px; border-radius:15px; background:#000;"></video>
        <video id="localVideo" autoplay muted style="width:100px; border-radius:10px; background:#222;"></video>
    </div>
    <button onclick="endCall()" style="background:#ff4b4b; color:white; border:none; padding:15px 30px; border-radius:30px; cursor:pointer; font-weight:bold;">Завершить</button>
</div>
            
            {% if current != 'BOT' %}<button onclick="inviteFriend()" style="background:none; border:none; color:var(--acc); cursor:pointer; font-weight:bold; font-size:14px;">➕ ИНВАЙТ</button>{% endif %}<!-- Кнопка в хедере -->
            


        </div>
        <div id="chat"></div>
        {% if current != 'BOT' %}
        <div class="input-bar">
            <input type="file" id="imgInp" hidden onchange="sendPhoto(this)">
            <div style="position: relative; display: flex; align-items: center; gap: 10px;">
    <!-- Кнопка смайлов -->
    <button onclick="toggleEmoji()" style="background:none; border:none; color:var(--acc); cursor:pointer; font-size:22px;">😊</button>
    
    <!-- Сама панель (добавь свои любимые смайлы сюда) -->
    <div id="emojiPicker" class="emoji-picker">
        <span onclick="addEmoji('😀')">😀</span>
        <span onclick="addEmoji('😂')">😂</span>
        <span onclick="addEmoji('😍')">😍</span>
        <span onclick="addEmoji('👍')">👍</span>
        <span onclick="addEmoji('🔥')">🔥</span>
        <span onclick="addEmoji('🚀')">🚀</span>
        <span onclick="addEmoji('❤️')">❤️</span>
        <span onclick="addEmoji('😎')">😎</span>
        <span onclick="addEmoji('🎉')">🎉</span>
        <span onclick="addEmoji('🤔')">🤔</span>
        <span onclick="addEmoji('😢')">😢</span>
        <span onclick="addEmoji('🤙')">🤙</span>
    </div>
</div>

            <input type="file" id="imgInp" hidden accept="image/*,video/*" onchange="sendMedia(this)">
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

    // --- БЛОК УВЕДОМЛЕНИЙ ---
    // Запрос прав при входе
    if (Notification.permission !== 'granted' && Notification.permission !== 'denied') {
        Notification.requestPermission();
    }

    function showNotify(user, text) {
        // Показываем только если вкладка скрыта и есть права
        if (document.hidden && Notification.permission === 'granted') {
            const n = new Notification(`Secure X: ${user}`, {
                body: text.length > 50 ? text.substring(0, 47) + "..." : text,
                icon: 'https://cdn-icons-png.flaticon.com',
                tag: 'chat-msg'
            });
            n.onclick = () => { window.focus(); n.close(); };
            setTimeout(() => n.close(), 5000);
        }
        // Звук сообщения (работает всегда)
        const audio = new Audio('https://cdn.pixabay.com');
        audio.play().catch(() => {}); // Игнорим ошибку если браузер блокирует автозвук
    }
    // -----------------------

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

    function setTheme(t) {
        const chat = document.getElementById("mainChat");
        if (!chat) return;
        const themes = {
            'default': 'var(--bg)',
            'gradient': 'linear-gradient(135deg, #0e1621 0%, #1a2a3a 50%, #2b5278 100%)',
            'sunset': 'linear-gradient(135deg, #42275a 0%, #734b6d 100%)',
            'ocean': 'linear-gradient(135deg, #000428 0%, #004e92 100%)',
            'emerald': 'linear-gradient(135deg, #093028 0%, #237a57 100%)',
            'midnight': 'linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%)',
            'neon': 'linear-gradient(135deg, #6441a5 0%, #2a0845 100%)',
            'carbon': 'linear-gradient(135deg, #141e30 0%, #243b55 100%)'
        };
        chat.style.background = themes[t] || themes['default'];
        localStorage.setItem("chatTheme", t);
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
            // ПРОВЕРКА НА НОВЫЕ СООБЩЕНИЯ ДЛЯ УВЕДОМЛЕНИЙ
            if(data.messages.length > box.childElementCount) {
                const lastMsg = data.messages[data.messages.length - 1];
                // Если сообщение не наше — кидаем пуш
                if (lastMsg.user !== me && box.childElementCount !== 0) {
                    showNotify(lastMsg.user, lastMsg.msg);
                }

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
        // Удержание фокуса на мобилках
        if (window.innerWidth <= 768) i.focus();
        
        await fetch('/send_msg', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({room: activeRoom, msg: text, type: 'text'}) });
        loadData();
    }

    function sendPhoto(input) {
        if (!input.files || !input.files[0]) return;
        const reader = new FileReader();
        reader.onload = async (e) => {
            await fetch('/send_msg', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({room: activeRoom, msg: e.target.result, type: 'img'}) });
            loadData();
        };
        reader.readAsDataURL(input.files[0]);
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
    if(localStorage.getItem("chatTheme")) setTheme(localStorage.getItem("chatTheme"));

    function toggleEmoji() {
        const picker = document.getElementById('emojiPicker');
        picker.style.display = (picker.style.display === 'grid') ? 'none' : 'grid';
    }

    function addEmoji(emoji) {
        const msgInput = document.getElementById('msg');
        msgInput.value += emoji;
        msgInput.focus(); 
    }

    document.addEventListener('mousedown', function(e) {
        const picker = document.getElementById('emojiPicker');
        const emojiBtn = e.target.closest('button');
        if (picker && !picker.contains(e.target) && (!emojiBtn || emojiBtn.innerText !== '😊')) {
            picker.style.display = 'none';
        }
    });

    function getRoomHash(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            hash = ((hash << 5) - hash) + str.charCodeAt(i);
            hash |= 0; 
        }
        return Math.abs(hash).toString(36);
    }

    function openRoomCall() {
        const room = activeRoom || "Global";
        const roomSecret = getRoomHash(room + "SecureX_Salt_2024");
        const callUrl = "https://meet.jit.si/" + roomSecret;
        window.open(callUrl, '_blank');
        const i = document.getElementById("msg");
        const oldVal = i.value;
        i.value = "📞 Я в звонке этой комнаты! Залетайте: " + callUrl;
        sendText();
        i.value = oldVal;
    }

    const msgInput = document.getElementById('msg');
    const chatBox = document.getElementById('chat');
    function scrollToBottom() { if(chatBox) chatBox.scrollTop = chatBox.scrollHeight; }

    if(msgInput) {
        msgInput.addEventListener('focus', () => { setTimeout(scrollToBottom, 300); });
    }
    function toggleCustom() {
    const p = document.getElementById("customPanel");
    const isHidden = p.style.display === 'none' || p.style.display === '';
    p.style.display = isHidden ? 'flex' : 'none';
}

function openSettings() {
    // Закрываем мини-меню
    toggleMenu();
    // Открываем большое окно
    document.getElementById('settingsModal').style.display = 'flex';
}

function closeSettings(event) {
    // Закрываем только если нажали на крестик или на темный фон
    if (!event || event.target.id === 'settingsModal') {
        document.getElementById('settingsModal').style.display = 'none';
    }
}

function manualScrollDown() {
    const chat = document.getElementById("chat");
    if(chat) {
        chat.scrollTo({ top: chat.scrollHeight, behavior: 'smooth' });
        closeSettings(null); // Закрываем настройки после промотки
    }
}

function toggleCustom() {
    const p = document.getElementById("customPanel");
    // Переключаем класс active вместо прямой правки стилей
    p.classList.toggle('active');
}

function setTheme(t) {
    const chat = document.getElementById("mainChat");
    const themes = {
        'default': 'var(--bg)',
        'gradient': 'linear-gradient(135deg, #0e1621, #2b5278)',
        'sunset': 'linear-gradient(135deg, #42275a, #734b6d)',
        'ocean': 'linear-gradient(135deg, #000428, #004e92)',
        'emerald': 'linear-gradient(135deg, #093028, #237a57)',
        'midnight': 'linear-gradient(135deg, #0f2027, #2c5364)',
        'neon': 'linear-gradient(135deg, #6441a5, #2a0845)'
    };

    if(chat) {
        chat.style.background = themes[t] || themes['default'];
        // Добавляем плавность смены фона
        chat.style.transition = "background 0.5s ease";
    }
    
    localStorage.setItem("chatTheme", t);
    
    // Закрываем меню после выбора (как в нормальных приложениях)
    setTimeout(toggleCustom, 200); 
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
        p = request.form.get('pass').strip()
        steam_link = request.form.get('steam', '').strip() # Получаем ссылку

        if u in users_auth:
            if check_password_hash(users_auth[u], p):
                session['user'] = u
                return redirect('/')
            return '<body style="background:#0e1621;color:white;padding:20px;"><h2>Ошибка: Неверный пароль</h2><a href="/login" style="color:#5288c1">Назад</a></body>'
        else:
            # РЕГИСТРАЦИЯ НОВОГО ЮЗЕРА
            users_auth[u] = generate_password_hash(p)
            # СОХРАНЯЕМ ССЫЛКУ В СЛОВАРЬ ДАННЫХ
            users_data[u] = {'invites': [], 'steam': steam_link} 
            session['user'] = u
            return redirect('/')
            
    # Твой HTML формы ниже без изменений...
    return '''<body style="background:#0e1621;color:white;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;margin:0;">
    <form method="POST" style="background:#17212b;padding:30px;border-radius:20px;display:flex;flex-direction:column;gap:15px;width:90%;max-width:350px;box-shadow:0 10px 30px rgba(0,0,0,0.5);">
        <h2 style="margin:0;color:#5288c1;text-align:center;">Secure X</h2>
        <p style="margin:0;font-size:12px;color:gray;text-align:center;">Вход или создание аккаунта</p>
        
        <input name="nick" placeholder="Никнейм" required style="padding:12px;border-radius:10px;border:none;background:#242f3d;color:white;outline:none;">
        <input name="pass" type="password" placeholder="Пароль" required style="padding:12px;border-radius:10px;border:none;background:#242f3d;color:white;outline:none;">
        
        <!-- НОВОЕ ПОЛЕ -->
        <div style="display:flex; flex-direction:column; gap:5px;">
            <label style="font-size:11px; color:#5288c1; margin-left:5px;">Ссылка на Steam (необязательно)</label>
            <input name="steam" placeholder="https://steamcommunity.com..." style="padding:12px;border-radius:10px;border:none;background:#242f3d;color:white;outline:none;border:1px solid rgba(82, 136, 193, 0.2);">
        </div>

        <button style="padding:15px;border-radius:10px;border:none;background:#5288c1;color:white;font-weight:bold;cursor:pointer;transition:0.3s;margin-top:10px;" onmouseover="this.style.background='#6399d2'" onmouseout="this.style.background='#5288c1'">ВОЙТИ В СЕТЬ</button>
    </form>
</body>
'''

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

@app.route('/users')
def show_users():
    all_users = []
    for nick, data in users_data.items():
        all_users.append({
            'nick': nick,
            'steam': data.get('steam', ''),
            'created_at': data.get('created_at', '16.02.2026'), # твоя дата
            'online': nick in active_users # список ников в сети
        })
    return render_template('users.html', users=all_users)




if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))























































