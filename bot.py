# bot.py
import os
import csv
import json
from pathlib import Path
import telebot
from telebot import types

# ---------------- CONFIG ----------------
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
SUPPORT_USER = os.environ.get("SUPPORT_USER", "")  # without @

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable missing!")

bot = telebot.TeleBot(TOKEN, threaded=False)

BASE = Path(__file__).parent
ACCOUNTS_FILE = BASE / "accounts.csv"       # CSV header: first,last,email,password
PENDING_FILE = BASE / "pending_tasks.csv"   # stores pending task proofs (uid, text)
USERS_FILE = BASE / "users.json"            # stores balances, refs, first_task_done
LOG_FILE = BASE / "bot.log"

# ------------- load/save users -------------
def load_json(file):
    if not file.exists(): return {}
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except:
        return {}

def save_json(file, data):
    file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

users = load_json(USERS_FILE)

def ensure_user(uid):
    uid = str(uid)
    if uid not in users:
        users[uid] = {"balance": 0.0, "ref": None, "first_task": False}
        save_json(USERS_FILE, users)

def add_balance(uid, amount):
    uid=str(uid)
    ensure_user(uid)
    users[uid]["balance"] += float(amount)
    save_json(USERS_FILE, users)

# ---------------- READ ACCOUNTS --------------
def read_accounts():
    if not ACCOUNTS_FILE.exists(): return []
    rows=[]
    with ACCOUNTS_FILE.open(encoding="utf-8") as f:
        r=csv.reader(f)
        for a in r:
            if len(a)>=4:
                rows.append({"first":a[0],"last":a[1],"email":a[2],"password":a[3]})
    return rows

def pop_account():
    accounts=read_accounts()
    if not accounts: return None
    acc=accounts.pop(0)
    with ACCOUNTS_FILE.open("w",encoding="utf-8",newline="") as f:
        w=csv.writer(f)
        for a in accounts:
            w.writerow([a["first"],a["last"],a["email"],a["password"]])
    return acc

def append_pending(uid,acc,proof):
    with PENDING_FILE.open("a",encoding="utf-8",newline="") as f:
        w=csv.writer(f)
        w.writerow([uid,acc["first"],acc["last"],acc["email"],acc["password"],proof])

# ---------------- MULTI LANGUAGE ----------------

LANG = {
    "ar": {
        "start": "أهلاً! اختر من القائمة:",
        "btn_task": "📝 المهام",
        "btn_balance": "💰 الرصيد",
        "btn_ref": "🔗 رابط الإحالة",
        "btn_support": "🆘 الدعم",
        "task_sent": "تم إرسال بيانات المهمة:",
        "send_proof": "\n⚠️ بعد التنفيذ أرسل رسالة نصية تؤكد إتمام المهمة.",
        "no_task": "لا توجد مهام متاحة الآن.",
        "ref_msg": "🔗 رابط الإحالة:\n{link}\n\n🎁 تحصل على 0.02$ عند تنفيذ الإحالة أول مهمة فقط.",
        "support_text": "للتواصل مع الدعم: @{admin}"
    },
    "en": {
        "start": "Welcome! Choose from menu:",
        "btn_task": "📝 Tasks",
        "btn_balance": "💰 Balance",
        "btn_ref": "🔗 Referral Link",
        "btn_support": "🆘 Support",
        "task_sent": "Task data sent:",
        "send_proof": "\n⚠️ After finishing, send a text message as proof.",
        "no_task": "No tasks available now.",
        "ref_msg": "🔗 Your referral link:\n{link}\n\n🎁 You earn $0.02 when your referral completes the first task.",
        "support_text": "Contact support: @{admin}"
    },
    "es": {
        "start": "¡Hola! Elige del menú:",
        "btn_task": "📝 Tareas",
        "btn_balance": "💰 Saldo",
        "btn_ref": "🔗 Enlace de referido",
        "btn_support": "🆘 Soporte",
        "task_sent": "Datos de la tarea enviados:",
        "send_proof": "\n⚠️ Después de terminar, envía un mensaje de texto como prueba.",
        "no_task": "No hay tareas disponibles.",
        "ref_msg": "🔗 Enlace de referido:\n{link}\n\n🎁 Ganas $0.02 cuando tu referido completa su primera tarea.",
        "support_text": "Soporte: @{admin}"
    },
    "fr": {
        "start": "Bienvenue ! Choisissez dans le menu :",
        "btn_task": "📝 Tâches",
        "btn_balance": "💰 Solde",
        "btn_ref": "🔗 Lien de parrainage",
        "btn_support": "🆘 Support",
        "task_sent": "Données de tâche envoyées :",
        "send_proof": "\n⚠️ Après avoir terminé, envoyez un message texte comme preuve.",
        "no_task": "Aucune tâche disponible.",
        "ref_msg": "🔗 Votre lien de parrainage :\n{link}\n\n🎁 Vous gagnez 0.02$ lorsque votre filleul termine sa première tâche.",
        "support_text": "Support : @{admin}"
    },
    "de": {
        "start": "Willkommen! Wähle aus dem Menü:",
        "btn_task": "📝 Aufgaben",
        "btn_balance": "💰 Guthaben",
        "btn_ref": "🔗 Empfehlungslink",
        "btn_support": "🆘 Support",
        "task_sent": "Aufgabendaten gesendet:",
        "send_proof": "\n⚠️ Nach Abschluss sende eine Textnachricht als Nachweis.",
        "no_task": "Keine Aufgaben verfügbar.",
        "ref_msg": "🔗 Dein Empfehlungslink:\n{link}\n\n🎁 Du verdienst 0,02$, wenn dein Referral die erste Aufgabe erledigt.",
        "support_text": "Support: @{admin}"
    },
    "it": {
        "start": "Benvenuto! Scegli dal menu:",
        "btn_task": "📝 Compiti",
        "btn_balance": "💰 Saldo",
        "btn_ref": "🔗 Link di riferimento",
        "btn_support": "🆘 Supporto",
        "task_sent": "Dati della missione inviati:",
        "send_proof": "\n⚠️ Dopo aver finito, invia un messaggio di testo come prova.",
        "no_task": "Nessuna missione disponibile.",
        "ref_msg": "🔗 Il tuo link referral:\n{link}\n\n🎁 Guadagni 0.02$ quando il referral completa la prima missione.",
        "support_text": "Supporto: @{admin}"
    },
    "ru": {
        "start": "Добро пожаловать! Выберите из меню:",
        "btn_task": "📝 Задания",
        "btn_balance": "💰 Баланс",
        "btn_ref": "🔗 Реферальная ссылка",
        "btn_support": "🆘 Поддержка",
        "task_sent": "Данные задания отправлены:",
        "send_proof": "\n⚠️ После выполнения отправьте текстовое сообщение как подтверждение.",
        "no_task": "Нет доступных заданий.",
        "ref_msg": "🔗 Ваша реферальная ссылка:\n{link}\n\n🎁 Вы получаете 0.02$, когда реферал выполнит первое задание.",
        "support_text": "Поддержка: @{admin}"
    }
}

def user_lang(m):
    code = (m.from_user.language_code or "en")[:2]
    return code if code in LANG else "en"

# -------------------- Keyboards --------------------
def menu(user):
    L = LANG[user_lang(user)]
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(L["btn_task"])
    kb.row(L["btn_balance"], L["btn_ref"])
    kb.row(L["btn_support"])
    return kb

# -------------------- Handlers ---------------------

@bot.message_handler(commands=['start'])
def start(m):
    ensure_user(m.from_user.id)
    L = LANG[user_lang(m.from_user)]

    ref_link = f"https://t.me/{bot.get_me().username}?start={m.from_user.id}"

    bot.send_message(
        m.chat.id,
        L["start"],
        reply_markup=menu(m.from_user)
    )

@bot.message_handler(func=lambda m: True)
def main_handler(m):
    uid = m.from_user.id
    ensure_user(uid)
    L = LANG[user_lang(m.from_user)]
    txt = m.text

    # ---------- طلب مهمة ----------
    if txt == L["btn_task"]:
        acc = pop_account()
        if not acc:
            bot.send_message(m.chat.id, L["no_task"])
            return

        mission = (
            f"🔷 **بيانات المهمة:**\n"
            f"الاسم: {acc['first']} {acc['last']}\n"
            f"الإيميل: {acc['email']}\n"
            f"كلمة المرور: {acc['password']}\n"
            f"رابط المهمة: {TASK_URL}\n"
            f"{L['send_proof']}"
        )

        bot.send_message(m.chat.id, mission, parse_mode="Markdown")
        users[str(uid)]["pending"] = acc
        save_json(USERS_FILE, users)
        return

    # ---------- الرصيد ----------
    if txt == L["btn_balance"]:
        balance = users[str(uid)]["balance"]
        bot.send_message(m.chat.id, f"💰 {balance}$")
        return

    # ---------- الإحالة ----------
    if txt == L["btn_ref"]:
        ref_link = f"https://t.me/{bot.get_me().username}?start={uid}"
        bot.send_message(m.chat.id, L["ref_msg"].format(link=ref_link))
        return

    # ---------- الدعم ----------
    if txt == L["btn_support"]:
        bot.send_message(m.chat.id, L["support_text"].format(admin=SUPPORT_USER))
        return

    # ---------- إرسال إثبات ----------
    if "pending" in users[str(uid)]:
        acc = users[str(uid)]["pending"]
        proof = txt

        # إرسال للإدارة للقبول / الرفض
        bot.send_message(
            ADMIN_ID,
            f"📥 مهمة جديدة بانتظار المراجعة:\n\n"
            f"👤 المستخدم: {uid}\n"
            f"الاسم: {acc['first']} {acc['last']}\n"
            f"الإيميل: {acc['email']}\n"
            f"الباسورد: {acc['password']}\n"
            f"الرابط: {TASK_URL}\n\n"
            f"الرسالة:\n{proof}\n\n"
            f"/accept_{uid} — قبول\n"
            f"/reject_{uid} — رفض"
        )

        bot.send_message(m.chat.id, "تم إرسال المهمة للمراجعة 👍")
        del users[str(uid)]["pending"]
        save_json(USERS_FILE, users)

# ------------ قبول أو رفض الإدارة --------------
@bot.message_handler(commands=['accept'])
def accept(m):
    if m.from_user.id != ADMIN_ID: return
    uid = m.text.replace("/accept_", "")
    add_balance(uid, 0.05)
    bot.send_message(uid, "✔ تم قبول المهمة وإضافة 0.05$ إلى رصيدك.")
    bot.reply_to(m, "✔ تم القبول.")

@bot.message_handler(commands=['reject'])
def reject(m):
    if m.from_user.id != ADMIN_ID: return
    uid = m.text.replace("/reject_", "")
    bot.send_message(uid, "❌ تم رفض المهمة.")
    bot.reply_to(m, "❌ تم الرفض.")

# ---------------- RUN ----------------
bot.infinity_polling()
