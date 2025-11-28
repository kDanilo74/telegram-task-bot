# bot.py — final consolidated version
import os
import csv
import json
import logging
from pathlib import Path
import telebot
from telebot import types

# ---------------- ENV / CONFIG ----------------
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

# --------------- logging ------------------
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# ------------- helpers (JSON) --------------
def load_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

users_db = load_json(USERS_FILE)  # { user_id: {"balance": float, "ref": ref_id_or_none, "first_task_done": bool} }

# ------------- accounts CSV helpers -------------
def read_accounts():
    if not ACCOUNTS_FILE.exists():
        return []
    rows = []
    with ACCOUNTS_FILE.open(newline='', encoding='utf-8') as f:
        r = list(csv.reader(f))
    if not r:
        return []
    # detect header
    firstrow = r[0]
    if any(cell.lower().startswith(k) for cell in firstrow for k in ("first","last","email","password")):
        r = r[1:]
    for row in r:
        if len(row) >= 4:
            rows.append({"first": row[0].strip(), "last": row[1].strip(), "email": row[2].strip(), "password": row[3].strip()})
    return rows

def pop_account():
    accounts = read_accounts()
    if not accounts:
        return None
    acc = accounts.pop(0)
    # write back remaining with header
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
    users_db[uid]["balance"] = float(users_db[uid].get("balance", 0.0)) + float(amount)
    save_json(USERS_FILE, users_db)

def sub_balance(uid, amount):
    uid = str(uid)
    ensure_user(uid)
    users_db[uid]["balance"] = float(users_db[uid].get("balance", 0.0)) - float(amount)
    save_json(USERS_FILE, users_db)

def register_referral(new_uid, ref_token):
    try:
        ref_id = str(ref_token)
        if ref_id.startswith("ref"):
            ref_id = ref_id[3:]
        if str(new_uid) == ref_id:
            return
        ensure_user(new_uid)
        if users_db[str(new_uid)].get("ref"):
            return
        users_db[str(new_uid)]["ref"] = ref_id
        save_json(USERS_FILE, users_db)
    except Exception as e:
        logging.exception("register_referral error: %s", e)

def handle_first_task_bonus(user_id):
    uid = str(user_id)
    rec = users_db.get(uid)
    if not rec:
        return
    if rec.get("first_task_done"):
        return
    rec["first_task_done"] = True
    save_json(USERS_FILE, users_db)
    ref = rec.get("ref")
    if ref:
        try:
            add_balance(ref, 0.02)
            logging.info("Referrer %s rewarded 0.02 for user %s", ref, uid)
        except Exception as e:
            logging.exception("reward referrer error: %s", e)

# ------------- pending proofs (CSV) -------------
def append_pending_proof(user_id, text):
    # store uid and proof text (for admin review)
    with PENDING_FILE.open("a", newline='', encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([str(user_id), text])

# ------------- LANGUAGE system -------------
LANG = {
    "ar": {
        "start": "أهلاً! اختر من القائمة:",
        "task_btn": "📝 تنفيذ مهمة",
        "balance_btn": "💰 رصيدي",
        "ref_btn": "🔗 رابط الإحالة",
        "withdraw_btn": "💵 سحب",
        "support_btn": "🆘 دعم",
        "no_task": "لا توجد مهام متاحة الآن.",
        "task_sent": "تم إرسال بيانات الحساب. أرسل الإثبات نصاً فقط.",
        "proof_received_user": "تم استلام الإثبات. في انتظار مراجعة الإدارة.",
        "admin_new_proof": "وصل إثبات جديد من المستخدم",
        "send_wallet": "أرسل عنوان محفظة USDT (TRC20):",
        "min_withdraw": "الحد الأدنى للسحب هو 1$.",
        "withdraw_sent": "تم إرسال طلب السحب للإدارة.",
        "paid_msg": "✅ تم إرسال المبلغ إلى محفظتك."
    },
    "en": {
        "start": "Welcome! Choose from the menu:",
        "task_btn": "📝 Task",
        "balance_btn": "💰 Balance",
        "ref_btn": "🔗 Referral Link",
        "withdraw_btn": "💵 Withdraw",
        "support_btn": "🆘 Support",
        "no_task": "No tasks available now.",
        "task_sent": "Your account was sent. Send proof as TEXT only.",
        "proof_received_user": "Proof received. Waiting for admin review.",
        "admin_new_proof": "New proof received from user",
        "send_wallet": "Send your USDT (TRC20) wallet address:",
        "min_withdraw": "Minimum withdrawal is 1$.",
        "withdraw_sent": "Withdrawal request sent to admin.",
        "paid_msg": "✅ Funds have been sent to your wallet."
    },
    "ru": {
        "ref_msg": "🔗 Ваша реферальная ссылка:",
        "ref_bonus": "🎁 Вы получаете 0.02$ за первую задачу приглашённого."
    },
    "es": {
        "ref_msg": "🔗 Tu enlace de referido:",
        "ref_bonus": "🎁 Ganas 0.02$ cuando tu referido completa su primera tarea."
    },
    "de": {
        "ref_msg": "🔗 Dein Einladungslink:",
        "ref_bonus": "🎁 Du verdienst 0.02$, wenn dein Geworbener seine erste Aufgabe abschließt."
    },
    "fr": {
        "ref_msg": "🔗 Votre lien de parrainage :",
        "ref_bonus": "🎁 Vous gagnez 0.02$ lorsque votre filleul réalise sa première tâche."
    },
    "it": {
        "ref_msg": "🔗 Il tuo link di referral:",
        "ref_bonus": "🎁 Guadagni 0.02$ quando il tuo invitato completa il suo primo compito."
    }
}

def get_lang(user):
    code = (getattr(user, "language_code", None) or "en").split("-")[0]
    return code if code in ("ar","en","ru","es","de","fr","it") else "en"

def menu(user):
    lang = get_lang(user)
    L = LANG.get(lang, LANG["en"])
    # fallback labels for languages that don't define full dict
    if lang in ("ru","es","de","fr","it"):
        # use English buttons labels but translated ref text will use LANG[lang]
        labels = {
            "task_btn": "📝 Task",
            "balance_btn": "💰 Balance",
            "ref_btn": "🔗 Referral Link",
            "withdraw_btn": "💵 Withdraw",
            "support_btn": "🆘 Support"
        }
    else:
        labels = L
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(labels["task_btn"])
    kb.row(labels["balance_btn"], labels["ref_btn"])
    kb.row(labels["withdraw_btn"])
    kb.row(labels["support_btn"])
    return kb

# ---------------- Handlers -----------------
@bot.message_handler(commands=['start'])
def start_handler(m):
    uid = m.from_user.id
    ensure_user(uid)
    # check referral code in /start
    parts = m.text.split()
    if len(parts) > 1:
        register_referral(uid, parts[1])
    lang = get_lang(m.from_user)
    L = LANG.get(lang, LANG["en"])
    referral_link = f"https://t.me/{bot.get_me().username}?start=ref{uid}"
    # Compose referral message per language
    if lang == "ar":
        ref_msg = f"🔗 رابط الإحالة الخاص بك:\n{referral_link}\n\n🎁 تربح 0.02$ عند تنفيذ أول مهمة من الشخص الذي دعوته."
        start_text = L["start"]
    elif lang == "en":
        ref_msg = f"🔗 Your referral link:\n{referral_link}\n\n🎁 You earn 0.02$ for the first task completed by your referral."
        start_text = L["start"]
    else:
        # languages with limited keys
        ref_msg = f"{LANG.get(lang).get('ref_msg')}\n{referral_link}\n\n{LANG.get(lang).get('ref_bonus')}"
        start_text = LANG["en"]["start"]
    bot.send_message(m.chat.id, f"{start_text}\n\n{ref_msg}", reply_markup=menu(m.from_user))

@bot.message_handler(func=lambda m: True)
def generic_handler(m):
    text = (m.text or "").strip()
    uid = m.from_user.id
    ensure_user(uid)
    lang = get_lang(m.from_user)
    L = LANG.get(lang, LANG["en"])

    # TASK
    if text == L.get("task_btn", "📝 Task"):
        acc = pop_account()
        if not acc:
            return bot.send_message(m.chat.id, L.get("no_task"))
        msg_task = (
f"Your task:\n\n"
f"First: {acc['first']}\n"
f"Last: {acc['last']}\n"
f"Email: {acc['email']}\n"
f"Password: {acc['password']}\n\n"
f"Open:\n"  https://shorturl.at/UV7OC
f"Complete the task\n"
f"Send proof here (TEXT ONLY)\n"
        )
        append_pending_proof(uid, f"SENT_TASK_FOR:{acc['email']}")  # log assignment
        bot.send_message(m.chat.id, msg_task)
        return

    # BALANCE
    if text == L.get("balance_btn", "💰 Balance"):
        bal = users_db.get(str(uid), {}).get("balance", 0.0)
        return bot.send_message(m.chat.id, f"{L.get('balance_btn','Balance')}: {bal}$")

    # REFERRAL
    if text == L.get("ref_btn", "🔗 Referral Link"):
        referral_link = f"https://t.me/{bot.get_me().username}?start=ref{uid}"
        if lang == "ar":
            msg = f"🔗 رابط الإحالة الخاص بك:\n{referral_link}\n\n🎁 تربح 0.02$ عند تنفيذ أول مهمة من الشخص الذي دعوته."
        elif lang == "en":
            msg = f"🔗 Your referral link:\n{referral_link}\n\n🎁 You earn 0.02$ for the first task completed by your referral."
        else:
            msg = f"{LANG.get(lang).get('ref_msg')}\n{referral_link}\n\n{LANG.get(lang).get('ref_bonus')}"
        return bot.send_message(m.chat.id, msg)

    # WITHDRAW
    if text == L.get("withdraw_btn", "💵 Withdraw"):
        bal = users_db.get(str(uid), {}).get("balance", 0.0)
        if bal < 1:
            return bot.send_message(m.chat.id, L.get("min_withdraw", "Minimum withdrawal is 1$."))
        bot.send_message(m.chat.id, L.get("send_wallet", "Send your USDT (TRC20) wallet address:"))
        bot.register_next_step_handler(m, receive_wallet)
        return

    # SUPPORT
    if text == L.get("support_btn", "🆘 Support"):
        sup = SUPPORT_USER if SUPPORT_USER else "support"
        return bot.send_message(m.chat.id, f"Contact support: @{sup}")

    # PROOF HANDLING (any text from normal users is treated as proof and forwarded to admin)
    if uid != ADMIN_ID:
        # save proof and forward to admin
        append_pending_proof(uid, text)
        # forward the proof to admin with user id
        try:
            bot.send_message(ADMIN_ID, f"New proof from user {uid}:\n\n{text}")
            bot.send_message(uid, L.get("proof_received_user", "Proof received. Waiting for admin review."))
        except Exception as e:
            logging.exception("forward proof error: %s", e)
        return

    # If ADMIN_ID sends messages (admin), ignore here (admin uses commands /accept /reject /paid)
    return

def receive_wallet(m):
    uid = m.from_user.id
    wallet = (m.text or "").strip()
    ensure_user(uid)
    bal = users_db.get(str(uid), {}).get("balance", 0.0)
    # send to admin
    try:
        bot.send_message(ADMIN_ID, f"Withdrawal request:\nUser: {uid}\nBalance: {bal}$\nWallet: {wallet}")
        bot.send_message(uid, LANG.get(get_lang(m.from_user), LANG["en"]).get("withdraw_sent", "Withdrawal request sent to admin."))
    except Exception as e:
        logging.exception("withdraw request error: %s", e)

# ---------------- Admin commands ----------------
@bot.message_handler(commands=['accept'])
def cmd_accept(m):
    if m.from_user.id != ADMIN_ID:
        return
    parts = m.text.split()
    if len(parts) != 2:
        return bot.reply_to(m, "Usage: /accept USERID")
    target = parts[1]
    try:
        add_balance(target, 0.05)
        handle_first_task_bonus(target)  # reward ref 0.02 if applicable and not given before
        bot.send_message(int(target), "✔ Your task was accepted. +0.05$")
        bot.reply_to(m, "Accepted and user notified.")
    except Exception as e:
        logging.exception("accept error: %s", e)
        bot.reply_to(m, "Error processing accept.")

@bot.message_handler(commands=['reject'])
def cmd_reject(m):
    if m.from_user.id != ADMIN_ID:
        return
    parts = m.text.split()
    if len(parts) != 2:
        return bot.reply_to(m, "Usage: /reject USERID")
    target = parts[1]
    try:
        bot.send_message(int(target), "❌ Your task was rejected.")
        bot.reply_to(m, "Rejected.")
    except Exception as e:
        logging.exception("reject error: %s", e)
        bot.reply_to(m, "Error processing reject.")

@bot.message_handler(commands=['paid'])
def cmd_paid(m):
    if m.from_user.id != ADMIN_ID:
        return
    parts = m.text.split()
    if len(parts) != 3:
        return bot.reply_to(m, "Usage: /paid USERID AMOUNT")
    target = parts[1]
    try:
        amount = float(parts[2])
    except:
        return bot.reply_to(m, "Amount must be a number")
    try:
        sub_balance(target, amount)
        bot.send_message(int(target), LANG.get("en").get("paid_msg"))
        bot.reply_to(m, "Paid and user notified.")
    except Exception as e:
        logging.exception("paid error: %s", e)
        bot.reply_to(m, "Error processing payment.")

# ----------------- start -----------------
if __name__ == "__main__":
    logging.info("Bot starting...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
