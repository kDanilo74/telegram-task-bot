# app.py  (Webhook-ready)
import os
import csv
import json
import logging
from pathlib import Path
from flask import Flask, request, abort
import telebot
from telebot import types

# -------------- CONFIG from ENV ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
SUPPORT_USER = os.environ.get("SUPPORT_USER", "support")
TASK_URL = os.environ.get("TASK_URL", "https://example.com")  # editable from Railway vars
DOMAIN = os.environ.get("DOMAIN")  # e.g. https://bottelegram-production-ae3d.up.railway.app
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}" if BOT_TOKEN else "/webhook"

if not BOT_TOKEN or not DOMAIN:
    raise RuntimeError("BOT_TOKEN and DOMAIN env variables are required!")

WEBHOOK_URL = DOMAIN.rstrip("/") + WEBHOOK_PATH

# --------------- setup bot & flask ----------------
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

# base files
BASE = Path(__file__).parent
ACCOUNTS_FILE = BASE / "accounts.csv"
USERS_FILE = BASE / "users.json"
PENDING_FILE = BASE / "pending_tasks.csv"

# logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ------------ helpers (JSON) ----------------
def load_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except:
        return {}

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

users = load_json(USERS_FILE)  # structure: { uid: {"balance":float, "ref":id_or_none, "first_task_done":bool, "pending":{...}} }

def ensure_user(uid):
    uid = str(uid)
    if uid not in users:
        users[uid] = {"balance": 0.0, "ref": None, "first_task_done": False}
        save_json(USERS_FILE, users)

def add_balance(uid, amount):
    uid = str(uid)
    ensure_user(uid)
    users[uid]["balance"] = float(users[uid].get("balance", 0.0)) + float(amount)
    save_json(USERS_FILE, users)

def sub_balance(uid, amount):
    uid = str(uid)
    ensure_user(uid)
    users[uid]["balance"] = float(users[uid].get("balance", 0.0)) - float(amount)
    save_json(USERS_FILE, users)

def register_referral(new_uid, ref_token):
    try:
        ref_id = str(ref_token)
        if ref_id.startswith("ref"):
            ref_id = ref_id[3:]
        if str(new_uid) == ref_id:
            return
        ensure_user(new_uid)
        if users[str(new_uid)].get("ref"):
            return
        users[str(new_uid)]["ref"] = ref_id
        save_json(USERS_FILE, users)
    except Exception as e:
        logging.exception("register_referral error: %s", e)

def handle_first_task_bonus(user_id):
    uid = str(user_id)
    rec = users.get(uid)
    if not rec:
        return
    if rec.get("first_task_done"):
        return
    rec["first_task_done"] = True
    save_json(USERS_FILE, users)
    ref = rec.get("ref")
    if ref:
        try:
            add_balance(ref, 0.02)
            logging.info("Referrer %s rewarded 0.02 for user %s", ref, uid)
        except Exception as e:
            logging.exception("reward referrer error: %s", e)

# ------------- accounts CSV helpers -------------
def read_accounts():
    if not ACCOUNTS_FILE.exists():
        return []
    rows = []
    with ACCOUNTS_FILE.open(newline='', encoding='utf-8') as f:
        r = list(csv.reader(f))
    if not r:
        return []
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
    with ACCOUNTS_FILE.open("w", newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(["first","last","email","password"])
        for a in accounts:
            w.writerow([a["first"], a["last"], a["email"], a["password"]])
    return acc

def append_pending(uid, acc, proof_text=""):
    with PENDING_FILE.open("a", newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow([str(uid), acc.get("first",""), acc.get("last",""), acc.get("email",""), acc.get("password",""), proof_text])

# ------------------ Languages ------------------
LANG = {
    "ar": {
        "start":"أهلاً! اختر من القائمة:",
        "btn_task":"📝 المهام",
        "btn_balance":"💰 الرصيد",
        "btn_ref":"🔗 رابط الإحالة",
        "btn_withdraw":"💵 سحب",
        "btn_support":"🆘 الدعم",
        "no_task":"لا توجد مهام متاحة الآن.",
        "task_sent":"تم إرسال بيانات المهمة:",
        "send_proof":"⚠️ بعد التنفيذ أرسل رسالة نصية تؤكد إتمام المهمة.",
        "ref_msg":"🔗 رابط الإحالة:\n{link}\n\n🎁 تحصل على 0.02$ عند تنفيذ الإحالة أول مهمة فقط.",
        "support_text":"للتواصل مع الدعم: @{admin}",
        "min_withdraw":"الحد الأدنى للسحب هو 1$."
    },
    "en": {
        "start":"Welcome! Choose from menu:",
        "btn_task":"📝 Tasks",
        "btn_balance":"💰 Balance",
        "btn_ref":"🔗 Referral Link",
        "btn_withdraw":"💵 Withdraw",
        "btn_support":"🆘 Support",
        "no_task":"No tasks available now.",
        "task_sent":"Task data sent:",
        "send_proof":"⚠️ After finishing, send a text message as proof.",
        "ref_msg":"🔗 Your referral link:\n{link}\n\n🎁 You earn $0.02 when your referral completes the first task.",
        "support_text":"Contact support: @{admin}",
        "min_withdraw":"Minimum withdrawal is 1$."
    }
}
# for other languages we'll reuse english text for buttons; referral text available if needed
EXTRA_LANG = {"es":"es", "fr":"fr", "de":"de", "it":"it", "ru":"ru"}
# get minimal language code
def detect_lang(user):
    code = (getattr(user, "language_code", None) or "en").split("-")[0]
    return code if code in LANG or code in EXTRA_LANG else "en"

def menu_markup(user):
    lang = detect_lang(user)
    L = LANG.get(lang, LANG["en"])
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(L["btn_task"])
    kb.row(L["btn_balance"], L["btn_ref"])
    kb.row(L["btn_withdraw"], L["btn_support"])
    return kb

# ---------------- Handlers ----------------
@bot.message_handler(commands=['start'])
def on_start(m):
    uid = m.from_user.id
    ensure_user(uid)
    parts = m.text.split()
    if len(parts) > 1:
        register_referral(uid, parts[1])
    lang = detect_lang(m.from_user)
    L = LANG.get(lang, LANG["en"])
    ref_link = f"https://t.me/{bot.get_me().username}?start=ref{uid}"
    ref_msg = L["ref_msg"].format(link=ref_link)
    bot.send_message(m.chat.id, f"{L['start']}\n\n{ref_msg}", reply_markup=menu_markup(m.from_user))

@bot.message_handler(func=lambda m: True)
def main_handler(m):
    uid = m.from_user.id
    ensure_user(uid)
    lang = detect_lang(m.from_user)
    L = LANG.get(lang, LANG["en"])
    text = (m.text or "").strip()

    # Task
    if text == L["btn_task"]:
        acc = pop_account()
        if not acc:
            bot.send_message(m.chat.id, L["no_task"])
            return
        # keep exact shape, add TASK_URL line under password
        task_msg = (
            f"🔷 بيانات المهمة:\n"
            f"الاسم: {acc['first']} {acc['last']}\n"
            f"الإيميل: {acc['email']}\n"
            f"كلمة المرور: {acc['password']}\n\n"
            f"رابط المهمة: {TASK_URL}\n\n"
            f"{L['send_proof']}"
        )
        # save pending assign (so we know this user has assigned task)
        users[str(uid)]["pending"] = acc
        save_json(USERS_FILE, users)
        bot.send_message(m.chat.id, task_msg)
        return

    # Balance
    if text == L["btn_balance"]:
        bal = users.get(str(uid), {}).get("balance", 0.0)
        bot.send_message(m.chat.id, f"💰 {bal}$")
        return

    # Referral
    if text == L["btn_ref"]:
        ref_link = f"https://t.me/{bot.get_me().username}?start=ref{uid}"
        bot.send_message(m.chat.id, L["ref_msg"].format(link=ref_link))
        return

    # Withdraw (existing system assumed)
    if text == L.get("btn_withdraw"):
        bal = users.get(str(uid), {}).get("balance", 0.0)
        if bal < 1:
            bot.send_message(m.chat.id, L.get("min_withdraw"))
            return
        bot.send_message(m.chat.id, "Send your USDT (TRC20) wallet address:")
        bot.register_next_step_handler(m, receive_wallet)
        return

    # Support
    if text == L["btn_support"]:
        bot.send_message(m.chat.id, L["support_text"].format(admin=SUPPORT_USER))
        return

    # If user has pending assigned task, treat any text they send as proof (text-only)
    if users.get(str(uid), {}).get("pending"):
        acc = users[str(uid)].pop("pending")
        save_json(USERS_FILE, users)
        proof = text
        append_pending(uid, acc, proof_text=proof)
        # forward to admin for review with simple commands
        admin_msg = (
            f"📥 مهمة جديدة بانتظار المراجعة:\n\n"
            f"👤 المستخدم: {uid}\n"
            f"الاسم: {acc['first']} {acc['last']}\n"
            f"الإيميل: {acc['email']}\n"
            f"الباسورد: {acc['password']}\n"
            f"الرابط: {TASK_URL}\n\n"
            f"الرسالة:\n{proof}\n\n"
            f"للموافقة: /accept_{uid}\n"
            f"للرفض: /reject_{uid}\n"
        )
        bot.send_message(ADMIN_ID, admin_msg)
        bot.send_message(uid, "تم إرسال المهمة للمراجعة 👍")
        return

    # fallback
    bot.send_message(m.chat.id, "استخدم الأزرار أو ارسل /start")

# receive wallet handler
def receive_wallet(m):
    uid = m.from_user.id
    wallet = (m.text or "").strip()
    bal = users.get(str(uid), {}).get("balance", 0.0)
    bot.send_message(ADMIN_ID, f"طلب سحب:\nUser: {uid}\nBalance: {bal}$\nWallet: {wallet}")
    bot.send_message(m.chat.id, "تم إرسال طلب السحب للإدارة.")

# Admin commands (accept/reject/pay)
@bot.message_handler(commands=['accept_','reject_','pay'])
def admin_command(m):
    # fallback; we parse in full text handlers below
    pass

@bot.message_handler(func=lambda m: m.text and m.text.startswith("/accept_"))
def cmd_accept(m):
    if m.from_user.id != ADMIN_ID:
        return
    uid = m.text.replace("/accept_","").strip()
    add_balance(uid, 0.05)
    handle_first_task_bonus(uid)
    bot.send_message(int(uid), "✔ تم قبول المهمة وإضافة 0.05$ إلى رصيدك.")
    bot.reply_to(m, "✔ تم القبول.")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("/reject_"))
def cmd_reject(m):
    if m.from_user.id != ADMIN_ID:
        return
    uid = m.text.replace("/reject_","").strip()
    bot.send_message(int(uid), "❌ تم رفض المهمة.")
    bot.reply_to(m, "❌ تم الرفض.")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("/pay "))
def cmd_paid(m):
    if m.from_user.id != ADMIN_ID:
        return
    parts = m.text.split()
    if len(parts) != 3:
        return bot.reply_to(m, "Usage: /pay USERID AMOUNT")
    target = parts[1]
    try:
        amount = float(parts[2])
    except:
        return bot.reply_to(m, "Amount must be a number")
    sub_balance(target, amount)
    bot.send_message(int(target), f"✅ تم إرسال {amount}$ إلى محفظتك (تم التقييم من الإدارة).")
    bot.reply_to(m, "Paid and user notified.")

# ---------------- Webhook endpoints ----------------
@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "", 200
    else:
        abort(403)

@app.route("/")
def index():
    return "Bot is running (webhook)."

# ------------- set webhook on start -------------
def set_webhook():
    try:
        bot.remove_webhook()
    except:
        pass
    ok = bot.set_webhook(url=WEBHOOK_URL)
    logging.info("set_webhook returned: %s", ok)
    return ok

if __name__ == "__main__":
    set_webhook()
    # Use Flask builtin only for local testing; on Railway gunicorn will be used (Procfile)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
