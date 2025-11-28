import os
import csv
import json
import telebot
from telebot import types
from pathlib import Path

# ---------------- ENV ----------------
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
SUPPORT_USER = os.environ.get("SUPPORT_USER", "")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN missing!")

bot = telebot.TeleBot(TOKEN, threaded=False)

BASE = Path(__file__).parent
ACCOUNTS_FILE = BASE / "accounts.csv"
PENDING_FILE = BASE / "pending_tasks.csv"
USERS_FILE = BASE / "users.json"

# ---------- Load DB ----------
def load_json(p):
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

def save_json(p, data):
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

users = load_json(USERS_FILE)

def ensure_user(uid):
    uid = str(uid)
    if uid not in users:
        users[uid] = {"balance":0, "ref":None}
        save_json(USERS_FILE, users)

def add_balance(uid, amount):
    uid = str(uid)
    ensure_user(uid)
    users[uid]["balance"] += amount
    save_json(USERS_FILE, users)

# ---------- Accounts ----------
def read_accounts():
    if not ACCOUNTS_FILE.exists(): 
        return []
    rows=[]
    with open(ACCOUNTS_FILE, newline='', encoding="utf-8") as f:
        r = list(csv.reader(f))
    if not r:
        return []
    if r[0][0].lower()=="first":
        r = r[1:]
    for row in r:
        if len(row)>=4:
            rows.append({
                "first":row[0],
                "last":row[1],
                "email":row[2],
                "password":row[3]
            })
    return rows

def pop_account():
    accs = read_accounts()
    if not accs:
        return None
    first = accs.pop(0)
    with open(ACCOUNTS_FILE,"w",newline='',encoding="utf-8") as f:
        w=csv.writer(f)
        w.writerow(["first","last","email","password"])
        for a in accs:
            w.writerow([a["first"],a["last"],a["email"],a["password"]])
    return first

def save_pending(uid, acc):
    with open(PENDING_FILE,"a",newline='',encoding="utf-8") as f:
        w=csv.writer(f)
        w.writerow([uid, acc["first"], acc["last"], acc["email"], acc["password"]])

# ---------------- Multi-Language ----------------
LANG = {
    "ar": {
        "start":"أهلاً! اختر من القائمة:",
        "task_btn":"📝 تنفيذ مهمة",
        "balance_btn":"💰 رصيدي",
        "ref_btn":"🔗 رابط الإحالة",
        "withdraw_btn":"💵 سحب",
        "support_btn":"🆘 دعم",
        "no_task":"لا توجد مهام الآن.",
        "task_sent":"تم إرسال حساب للعمل. أرسل الإثبات نصياً فقط.",
        "send_wallet":"أرسل عنوان محفظة USDT TRC20:",
        "min_withdraw":"الحد الأدنى للسحب 1$",
        "withdraw_sent":"تم إرسال طلب السحب للإدارة ✔",
        "paid_msg":"تم إرسال المال إلى محفظتك ✔"
    },
    "en":{
        "start":"Welcome! Choose from menu:",
        "task_btn":"📝 Task",
        "balance_btn":"💰 Balance",
        "ref_btn":"🔗 Referral Link",
        "withdraw_btn":"💵 Withdraw",
        "support_btn":"🆘 Support",
        "no_task":"No tasks available.",
        "task_sent":"Your task account was sent. Send proof as TEXT only.",
        "send_wallet":"Send your USDT TRC20 wallet:",
        "min_withdraw":"Minimum withdrawal is 1$",
        "withdraw_sent":"Withdrawal request sent to admin ✔",
        "paid_msg":"Funds sent to your wallet ✔"
    },
    "ru":{}, "es":{}, "fr":{}, "de":{}, "it":{}
}

# لو اللغة مش موجودة ناخد إنجليزي
def get_lang(user):
    code = (getattr(user, "language_code", None) or "en").split("-")[0]
    return code if code in ["ar","en","ru","es","de","fr","it"] else "en"

def menu(user):
    L = LANG[get_lang(user)]
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(L["task_btn"])
    kb.row(L["balance_btn"], L["ref_btn"])
    kb.row(L["withdraw_btn"])
    kb.row(L["support_btn"])
    return kb

# --------------- Start ----------------
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.from_user.id
    ensure_user(uid)

    L = LANG[get_lang(msg.from_user)]
    bot.send_message(msg.chat.id, L["start"], reply_markup=menu(msg.from_user))

# ---------------- Text Handler ----------------
@bot.message_handler(func=lambda m: True)
def handler(m):
    uid = m.from_user.id
    ensure_user(uid)
    L = LANG[get_lang(m.from_user)]
    text = m.text.strip()

    # ---- Task ----
    if text == L["task_btn"]:
        acc = pop_account()
        if not acc:
            return bot.send_message(m.chat.id, L["no_task"])

        msg_task = f"""
Your task:

First: {acc['first']}
Last: {acc['last']}
Email: {acc['email']}
Password: {acc['password']}

Open:
(https://shorturl.at/omjU5)

Complete the task
Send proof here (TEXT ONLY)
"""

        save_pending(uid, acc)
        return bot.send_message(m.chat.id, msg_task)

    # ---- Balance ----
    if text == L["balance_btn"]:
        bal = users[str(uid)]["balance"]
        return bot.send_message(m.chat.id, f"{L['balance_btn']}: {bal}$")

    # ---- Referral ----
  if text == L["btn_ref"]:
    uid = m.from_user.id
    link = f"https://t.me/{bot.get_me().username}?start=ref{uid}"
    
    lang = get_lang(m.from_user)

    msgs = {
        "en": f"🔗 Your referral link:\n{link}\n\n🎁 You earn 0.02$ for the first task completed by your referral.",
        "ar": f"🔗 رابط الإحالة الخاص بك:\n{link}\n\n🎁 تربح 0.02$ عند تنفيذ أول مهمة من الشخص الذي دعوته.",
        "ru": f"🔗 Ваша реферальная ссылка:\n{link}\n\n🎁 Вы получаете 0.02$ за первую выполненную задачу приглашённого пользователя.",
        "es": f"🔗 Tu enlace de referido:\n{link}\n\n🎁 Ganas 0.02$ cuando tu referido completa su primera tarea.",
        "de": f"🔗 Dein Einladungslink:\n{link}\n\n🎁 Du verdienst 0.02$, wenn dein geworbener Nutzer seine erste Aufgabe abschließt.",
        "fr": f"🔗 Votre lien de parrainage :\n{link}\n\n🎁 Vous gagnez 0.02$ lorsque votre filleul réalise sa première tâche.",
        "it": f"🔗 Il tuo link di referral:\n{link}\n\n🎁 Guadagni 0.02$ quando il tuo invitato completa il suo primo compito."
    }

    msg = msgs.get(lang, msgs["en"])
    bot.send_message(m.chat.id, msg)
    return



    # ---- Withdraw ----
    if text == L["withdraw_btn"]:
        bal = users[str(uid)]["balance"]
        if bal < 1:
            return bot.send_message(m.chat.id, L["min_withdraw"])
        bot.send_message(m.chat.id, L["send_wallet"])
        bot.register_next_step_handler(m, receive_wallet)
        return

    # ---- Support ----
    if text == L["support_btn"]:
        return bot.send_message(m.chat.id, f"Contact: @{SUPPORT_USER}")

    # ---- Proof Handling ----
    if uid != ADMIN_ID:   # مستخدم عادي
        bot.send_message(
            ADMIN_ID,
            f"New proof from user {uid}:\n\n{text}"
        )
        return bot.send_message(m.chat.id, "Proof received. Waiting admin review ✔")

    # ADMIN receives normal messages silently


def receive_wallet(m):
    uid = m.from_user.id
    wallet = m.text.strip()
    L = LANG[get_lang(m.from_user)]

    bot.send_message(
        ADMIN_ID,
        f"Withdrawal request:\nUser: {uid}\nBalance: {users[str(uid)]['balance']}\nWallet: {wallet}"
    )

    bot.send_message(m.chat.id, L["withdraw_sent"])

# ----------- Admin Commands ----------
@bot.message_handler(commands=['accept'])
def accept(m):
    if m.from_user.id != ADMIN_ID: return
    parts = m.text.split()
    if len(parts)!=2: return
    uid = parts[1]
    add_balance(uid, 0.05)
    bot.send_message(int(uid),"Task accepted ✔ +0.05$")
    bot.reply_to(m,"Accepted ✔")

@bot.message_handler(commands=['reject'])
def reject(m):
    if m.from_user.id != ADMIN_ID: return
    parts = m.text.split()
    if len(parts)!=2: return
    uid = parts[1]
    bot.send_message(int(uid),"Task rejected ❌")
    bot.reply_to(m,"Rejected ❌")

@bot.message_handler(commands=['paid'])
def paid(m):
    if m.from_user.id != ADMIN_ID: return
    parts = m.text.split()
    if len(parts)!=3: return
    uid = parts[1]
    bot.send_message(int(uid),"Funds sent ✔")
    bot.reply_to(m,"Done ✔")

# ---------- Run ----------
bot.infinity_polling()
