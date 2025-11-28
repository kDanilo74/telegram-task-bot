
import os
import csv
import json
import logging
from pathlib import Path
import telebot
from telebot import types

# ---------------- CONFIG ----------------
# Read sensitive values from environment (set these in Railway: BOT_TOKEN, ADMIN_ID, SUPPORT_USER)
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
SUPPORT_USER = os.environ.get("SUPPORT_USER", "")


if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable missing!")

bot = telebot.TeleBot(TOKEN, threaded=True)

BASE = Path(__file__).parent
ACCOUNTS_FILE = BASE / "accounts.csv"       # CSV with header: first,last,email,password
PENDING_FILE = BASE / "pending_tasks.csv"   # pending proofs
USERS_FILE = BASE / "users.json"            # stores balances and refs

# --------------- logging ------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

# ------------- helpers (JSON) --------------
def load_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except:
        return {}

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

users_db = load_json(USERS_FILE)

# ------------- accounts CSV helpers -------------
def read_accounts():
    if not ACCOUNTS_FILE.exists():
        return []
    rows = []
    with ACCOUNTS_FILE.open(newline='', encoding='utf-8') as f:
        r = csv.reader(f)
        allrows = list(r)
        if not allrows:
            return []
        firstrow = allrows[0]
        if any(h.lower().startswith(k) for k in ["first", "email", "last"] for h in firstrow):
            allrows = allrows[1:]
        for row in allrows:
            if len(row) >= 4:
                rows.append({
                    "first": row[0].strip(),
                    "last": row[1].strip(),
                    "email": row[2].strip(),
                    "password": row[3].strip()
                })
    return rows

def pop_account():
    accounts = read_accounts()
    if not accounts:
        return None
    acc = accounts.pop(0)
    with ACCOUNTS_FILE.open("w", newline='', encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["first","last","email","password"])
        for a in accounts:
            w.writerow([a["first"], a["last"], a["email"], a["password"]])
    return acc

# ------------- referral & balance -------------
def ensure_user(uid):
    uid = str(uid)
    if uid not in users_db:
        users_db[uid] = {"balance": 0.0, "ref": None, "first_task_done": False}
        save_json(USERS_FILE, users_db)

def add_balance(uid, amount):
    uid = str(uid)
    ensure_user(uid)
    users_db[uid]["balance"] = float(users_db[uid]["balance"]) + float(amount)
    save_json(USERS_FILE, users_db)

def sub_balance(uid, amount):
    uid = str(uid)
    ensure_user(uid)
    users_db[uid]["balance"] = float(users_db[uid]["balance"]) - float(amount)
    save_json(USERS_FILE, users_db)

def register_referral(new_uid, ref_token):
    try:
        ref_id = ref_token.replace("ref", "")
        if str(new_uid) == ref_id:
            return
        ensure_user(new_uid)
        if users_db[str(new_uid)]["ref"]:
            return
        users_db[str(new_uid)]["ref"] = ref_id
        save_json(USERS_FILE, users_db)
    except:
        pass

def reward_referrer(user_id):
    user_id = str(user_id)
    u = users_db.get(user_id, {})
    if not u.get("first_task_done"):
        u["first_task_done"] = True
        save_json(USERS_FILE, users_db)
        if u.get("ref"):
            ref = u["ref"]
            add_balance(ref, 0.02)

# ------------- pending proofs (CSV) -------------
def append_pending(user_id, account):
    with PENDING_FILE.open("a", newline='', encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([str(user_id), account["first"], account["last"], account["email"], account["password"]])

# ------------- LANGUAGE SYSTEM -------------
LANG = {
    "ar": {
        "start": "أهلا! اختر من القائمة:",
        "btn_task": "📝 تنفيذ مهمة",
        "btn_balance": "💰 رصيدي",
        "btn_ref": "🔗 رابط الإحالة",
        "btn_support": "🆘 دعم",
        "task_msg": "مهمتك:\n1) افتح الرابط: {url}\n2) نفّذ المطلوب\n3) أرسل الإثبات هنا.",
        "no_task": "لا توجد مهام الآن.",
        "sent_task": "تم إرسال بيانات الحساب إليك.",
        "support_text": "للتواصل مع الدعم: @{admin}",
        "paid_notif": "✅ تم إرسال {amount}$ إليك."
    },
    "en": {
        "start": "Welcome! Choose from the menu:",
        "btn_task": "📝 Do Task",
        "btn_balance": "💰 My Balance",
        "btn_ref": "🔗 Referral Link",
        "btn_support": "🆘 Support",
        "task_msg": "Your task:\n1) Open: {url}\n2) Complete it\n3) Send proof here.",
        "no_task": "No tasks available.",
        "sent_task": "Your account details were sent.",
        "support_text": "Support: @{admin}",
        "paid_notif": "✅ {amount}$ sent to you."
    }
}

def user_lang(user):
    code = (getattr(user, "language_code", "en") or "en").split("-")[0]
    return code if code in LANG else "en"

# -------------- keyboards ----------------
def main_menu(user):
    L = LANG[user_lang(user)]
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(L["btn_task"])
    kb.row(L["btn_balance"], L["btn_ref"])
    kb.row(L["btn_support"])
    return kb

# ---------------- handlers ----------------
@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    ensure_user(uid)
    parts = m.text.split()
    if len(parts) > 1:
        register_referral(uid, parts[1])
    L = LANG[user_lang(m.from_user)]
    ref = f"https://t.me/{bot.get_me().username}?start=ref{uid}"
    msg = f"{L['start']}\n\n{L['btn_ref']}: {ref}\n(You earn $0.02 from first task)"
    bot.send_message(m.chat.id, msg, reply_markup=main_menu(m.from_user))

@bot.message_handler(func=lambda m: True)
def handler(m):
    uid = m.from_user.id
    ensure_user(uid)
    L = LANG[user_lang(m.from_user)]
    text = m.text.strip()

    # Task
    if text == L["btn_task"]:
        acc = pop_account()
        if not acc:
            bot.send_message(m.chat.id, L["no_task"])
            return
        append_pending(uid, acc)
        info = (
            f"First: {acc['first']}\n"
            f"Last: {acc['last']}\n"
            f"Email: {acc['email']}\n"
            f"Password: {acc['password']}\n\n"
            f"{L['task_msg'].format(url='https://example.com')}"
        )
        bot.send_message(m.chat.id, info)
        return

    # Balance
    if text == L["btn_balance"]:
        bal = users_db.get(str(uid), {}).get("balance", 0.0)
        bot.send_message(m.chat.id, f"{bal}$")
        return

    # Referral
    if text == L["btn_ref"]:
        link = f"https://t.me/{bot.get_me().username}?start=ref{uid}"
        bot.send_message(m.chat.id, link)
        return

    # Support
    if text == L["btn_support"]:
        bot.send_message(m.chat.id, L["support_text"].format(admin=SUPPORT_USER))
        return

    bot.send_message(m.chat.id, "Use the menu or /start")

# -------------------- admin -----------------------
@bot.message_handler(commands=['pay'])
def pay(m):
    if m.from_user.id != ADMIN_ID:
        return
    parts = m.text.split()
    if len(parts) != 3:
        bot.reply_to(m, "Usage: /pay USER AMOUNT")
        return
    uid = parts[1]
    amount = float(parts[2])
    sub_balance(uid, amount)
    bot.send_message(int(uid), LANG["en"]["paid_notif"].format(amount=amount))
    bot.reply_to(m, "Sent.")

@bot.message_handler(commands=['accept'])
def accept_task(m):
    if m.from_user.id != ADMIN_ID:
        return
    parts = m.text.split()
    if len(parts) != 2:
        bot.reply_to(m, "Usage: /accept USERID")
        return
    uid = parts[1]
    add_balance(uid, 0.05)
    reward_referrer(uid)
    bot.send_message(int(uid), "Task accepted +0.05$")
    bot.reply_to(m, "OK.")

# ----------------- run -----------------
if __name__ == "__main__":
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
