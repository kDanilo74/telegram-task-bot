import os
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).parent
ENV_PATH = BASE / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

TOKEN = os.getenv("TG_BOT_TOKEN")  # ضع توكن البوت هنا أو في .env
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # ضع رقم الأدمن هنا
SUPPORT_USER = os.getenv("SUPPORT_USER", "")  # اسم اليوزر للدعم بدون @
TASK_URL = os.getenv("TASK_URL", "https://example.com/task")
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"
ACCOUNTS_FILE = DATA_DIR / "accounts.csv"
PENDING_FILE = DATA_DIR / "pending_tasks.csv"

# Runtime settings
TASK_TIMEOUT_SECONDS = int(os.getenv("TASK_TIMEOUT_SECONDS", "900"))  # 15 minutes default
RATE_LIMIT_SECONDS = int(os.getenv("RATE_LIMIT_SECONDS", "5"))  # rate limit between commands
REF_BONUS = float(os.getenv("REF_BONUS", "0.02"))
TASK_REWARD = float(os.getenv("TASK_REWARD", "0.05"))

# Supported languages
DEFAULT_LANG = "ar"
SUPPORTED_LANGS = ["ar","en","es","fr","de","it","ru"]
import logging
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "bot.log"

logger = logging.getLogger("pro_bot")
logger.setLevel(logging.INFO)

fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
fh.setFormatter(formatter)
logger.addHandler(fh)
# also stream to console
sh = logging.StreamHandler()
sh.setFormatter(formatter)
logger.addHandler(sh)
import json
import csv
from pathlib import Path
from threading import Lock
from config import USERS_FILE, ACCOUNTS_FILE, PENDING_FILE
from logger import logger

_lock = Lock()

def _read_json(file):
    if not file.exists():
        return {}
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.exception("Failed reading json %s: %s", file, e)
        return {}

def _write_json(file, data):
    try:
        file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.exception("Failed writing json %s: %s", file, e)

def load_users():
    with _lock:
        return _read_json(USERS_FILE)

def save_users(data):
    with _lock:
        _write_json(USERS_FILE, data)

def ensure_user(users, uid):
    uid=str(uid)
    if uid not in users:
        users[uid] = {
            "balance": 0.0,
            "ref": None,
            "first_task_done": False,
            "lang": None,
            "pending": None,  # pending assigned account
            "task_assigned_at": None,
            "cooldown_until": None,
        }
        save_users(users)
    return users[uid]

def read_accounts():
    if not ACCOUNTS_FILE.exists():
        return []
    rows = []
    with ACCOUNTS_FILE.open(encoding="utf-8") as f:
        r = csv.reader(f)
        for a in r:
            if len(a) >= 4:
                rows.append({"first": a[0], "last": a[1], "email": a[2], "password": a[3]})
    return rows

def pop_account():
    accounts = read_accounts()
    if not accounts:
        return None
    acc = accounts.pop(0)
    with ACCOUNTS_FILE.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        for a in accounts:
            w.writerow([a["first"], a["last"], a["email"], a["password"]])
    return acc

def append_pending_row(row):
    with PENDING_FILE.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(row)
from telebot import types
from config import SUPPORTED_LANGS, DEFAULT_LANG
from storage import load_users, save_users, ensure_user
from logger import logger

LANG = {
    "ar": {
        "start": "أهلاً! اختر من القائمة:",
        "btn_task": "📝 المهام",
        "btn_balance": "💰 الرصيد",
        "btn_ref": "🔗 رابط الإحالة",
        "btn_support": "🆘 الدعم",
        "btn_withdraw": "💸 سحب الأرباح",
        "language": "🌐 تغيير اللغة",
    },
    "en": {
        "start": "Welcome! Choose from menu:",
        "btn_task": "📝 Tasks",
        "btn_balance": "💰 Balance",
        "btn_ref": "🔗 Referral",
        "btn_support": "🆘 Support",
        "btn_withdraw": "💸 Withdraw",
        "language": "🌐 Change language",
    }
    # يمكن إضافة باقي اللغات هنا
}

def get_locale(user):
    users = load_users()
    u = users.get(str(user.id), {})
    lang = u.get("lang") or (user.language_code or DEFAULT_LANG)[:2]
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    return LANG.get(lang, LANG[DEFAULT_LANG])

def menu_for(user):
    L = get_locale(user)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(L["btn_task"])
    kb.row(L["btn_balance"], L["btn_ref"])
    kb.row(L["btn_withdraw"], L["language"])
    kb.row(L["btn_support"])
    return kb

def cmd_start(bot, m):
    users = load_users()
    ensure_user(users, m.from_user.id)
    L = get_locale(m.from_user)
    bot.send_message(m.chat.id, L["start"], reply_markup=menu_for(m.from_user))
    logger.info("User %s started", m.from_user.id)
import time
from telebot import types
from config import TASK_URL, TASK_TIMEOUT_SECONDS, TASK_REWARD, REF_BONUS
from storage import load_users, save_users, pop_account, append_pending_row, ensure_user
from logger import logger

def request_task(bot, m, L):
    uid = str(m.from_user.id)
    users = load_users()
    ensure_user(users, uid)
    user = users[uid]

    # Require username to avoid fake accounts
    if not getattr(m.from_user, "username", None):
        bot.send_message(m.chat.id, "⚠️ الرجاء إضافة @username في إعدادات تيليجرام قبل استخدام البوت.")
        return

    # Rate-limit / cooldown
    now = int(time.time())
    if user.get("cooldown_until") and now < user["cooldown_until"]:
        bot.send_message(m.chat.id, "⏳ انتظر قليلاً قبل طلب مهمة جديدة.")
        return

    # if user has pending assigned
    if user.get("pending"):
        bot.send_message(m.chat.id, "📌 لديك مهمة معلقة لم ترسل لها إثبات بعد. أرسل الإثبات أو انتظر مراجعة الأدمن.")
        return

    acc = pop_account()
    if not acc:
        bot.send_message(m.chat.id, L["no_task"] if "no_task" in L else "No tasks available.")
        return

    mission = (
        f"🔷 **بيانات المهمة:**\n"
        f"الاسم: {acc['first']} {acc['last']}\n"
        f"الإيميل: {acc['email']}\n"
        f"كلمة المرور: {acc['password']}\n"
        f"رابط المهمة: {TASK_URL}\n"
        f"\n⚠️ بعد التنفيذ أرسل رسالة نصية تؤكد إتمام المهمة."
    )

    bot.send_message(m.chat.id, mission, parse_mode="Markdown")
    # assign
    user["pending"] = acc
    user["task_assigned_at"] = now
    user["cooldown_until"] = now + 2  # tiny protection
    save_users(users)
    logger.info("Assigned task to %s (%s)", uid, acc["email"])

def receive_proof(bot, m, L):
    uid = str(m.from_user.id)
    users = load_users()
    if uid not in users or not users[uid].get("pending"):
        return False  # not a proof message
    acc = users[uid]["pending"]
    proof = m.text
    append_pending_row([uid, acc["first"], acc["last"], acc["email"], acc["password"], proof])
    # notify admin
    bot.send_message(
        int(bot.config.ADMIN_ID),
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
    del users[uid]["pending"]
    users[uid]["task_assigned_at"] = None
    save_users(users)
    logger.info("User %s submitted proof", uid)
    return True
from storage import load_users, save_users, ensure_user
from logger import logger

def show_balance(bot, m, L):
    uid = str(m.from_user.id)
    users = load_users()
    ensure_user(users, uid)
    balance = users[uid]["balance"]
    bot.send_message(m.chat.id, f"💰 رصيدك: {balance:.2f}$")

def start_withdraw(bot, m, L):
    uid = str(m.from_user.id)
    users = load_users()
    ensure_user(users, uid)
    balance = users[uid]["balance"]
    if balance <= 0:
        bot.send_message(m.chat.id, "رصيدك صفر، لا يمكن السحب.")
        return
    bot.send_message(m.chat.id, "أرسل وسيلة السحب (مثل: Vodafone Cash / Payeer / USDT) متبوعًا بالمعلومات المطلوبة.")
    # set state simple: store expecting_withdraw
    users[uid]["expect_withdraw"] = True
    save_users(users)

def receive_withdraw_request(bot, m):
    uid = str(m.from_user.id)
    users = load_users()
    if users.get(uid, {}).get("expect_withdraw"):
        info = m.text
        users[uid]["expect_withdraw"] = False
        # log to admin channel
        bot.send_message(int(bot.config.ADMIN_ID),
                         f"🟡 طلب سحب من {uid}:\n{info}\nالرصيد: {users[uid]['balance']:.2f}$\nاستخدم /pay {uid} <amount> للموافقة.")
        bot.send_message(m.chat.id, "تم إرسال طلب السحب للأدمن للمراجعة.")
        save_users(users)
        return True
    return False
from storage import load_users, save_users, ensure_user
from config import REF_BONUS, TASK_REWARD
from logger import logger

def send_ref(bot, m, L):
    uid = m.from_user.id
    link = f"https://t.me/{bot.get_me().username}?start={uid}"
    bot.send_message(m.chat.id, L["ref_msg"].format(link=link))

def process_start_param(bot, m, param):
    # when user clicked referral /start=<id>
    users = load_users()
    uid = str(m.from_user.id)
    ensure_user(users, uid)
    if not param:
        save_users(users)
        return
    try:
        ref_id = str(int(param))
    except:
        save_users(users)
        return
    # set ref only if new user has no ref and ref != self
    if users[uid].get("ref") is None and ref_id != uid:
        users[uid]["ref"] = ref_id
        save_users(users)
        # do NOT give bonus until ref completes first task; that logic is in admin accept flow
from storage import load_users, save_users
from logger import logger
from config import TASK_REWARD, REF_BONUS
import time

def cmd_stats(bot, m):
    users = load_users()
    total_users = len(users)
    total_balance = sum(u.get("balance",0) for u in users.values())
    bot.reply_to(m, f"Users: {total_users}\nTotal balance: {total_balance:.2f}$")

def cmd_pending(bot, m):
    # show last lines in pending_tasks.csv
    from pathlib import Path
    p = Path(bot.config.PENDING_FILE)
    if not p.exists():
        bot.reply_to(m, "No pending tasks file.")
        return
    lines = p.read_text(encoding="utf-8").strip().splitlines()[-20:]
    bot.send_message(m.chat.id, "Recent pending entries:\n" + "\n".join(lines))

def cmd_accounts(bot, m):
    from pathlib import Path
    p = Path(bot.config.ACCOUNTS_FILE)
    if not p.exists():
        bot.reply_to(m, "No accounts file.")
        return
    count = len(p.read_text(encoding="utf-8").strip().splitlines())
    bot.reply_to(m, f"Accounts available: {count}")

def cmd_broadcast(bot, m, text):
    users = load_users()
    failed = 0
    sent = 0
    for uid in list(users.keys()):
        try:
            bot.send_message(int(uid), text)
            sent += 1
        except Exception:
            failed += 1
    bot.reply_to(m, f"Broadcast sent: {sent}, failed: {failed}")

def accept_user(bot, uid):
    users = load_users()
    uid=str(uid)
    if uid not in users:
        return False
    users[uid]["balance"] = users[uid].get("balance",0) + float(bot.config.TASK_REWARD)
    # referral bonus if first task
    if not users[uid].get("first_task_done"):
        users[uid]["first_task_done"] = True
        ref = users[uid].get("ref")
        if ref and str(ref) in users:
            users[str(ref)]["balance"] = users[str(ref)].get("balance",0) + float(bot.config.REF_BONUS)
    save_users(users)
    bot.send_message(int(uid), f"✔ تم قبول المهمة وإضافة {bot.config.TASK_REWARD}$ إلى رصيدك.")
    logger.info("Accepted user %s", uid)
    return True

def reject_user(bot, uid):
    users = load_users()
    uid=str(uid)
    if uid not in users:
        return False
    bot.send_message(int(uid), "❌ تم رفض المهمة.")
    logger.info("Rejected user %s", uid)
    return True

def pay_command(bot, m, args):
    # /pay <uid> <amount>
    parts = args.split()
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /pay <uid> <amount>")
        return
    uid, amount = parts[0], parts[1]
    users = load_users()
    if uid not in users:
        bot.reply_to(m, "User not found.")
        return
    try:
        amt = float(amount)
    except:
        bot.reply_to(m, "Invalid amount.")
        return
    users[uid]["balance"] = users[uid].get("balance",0) - amt
    save_users(users)
    bot.send_message(int(uid), f"تم إرسال {amt}$ يدوياً من الأدمن.")
    bot.reply_to(m, "تمت الدفع (سجلت محلياً).")
import telebot
import time
from config import TOKEN, ADMIN_ID, SUPPORT_USER, USERS_FILE, TASK_URL, DEFAULT_LANG
from logger import logger
import config as cfg
from storage import load_users, save_users, ensure_user
from handlers import start as start_h, tasks as tasks_h, balance as balance_h, refs as refs_h, admin as admin_h

# attach config to bot for convenience
bot = telebot.TeleBot(TOKEN, threaded=True)
bot.config = cfg

# Basic command handlers
@bot.message_handler(commands=['start'])
def handle_start(m):
    # check param
    param = None
    if m.text and " " in m.text:
        param = m.text.split(" ",1)[1].strip()
    if param:
        refs_h.process_start_param(bot, m, param)
    start_h.cmd_start(bot, m)

@bot.message_handler(commands=['stats'])
def cmd_stats(m):
    if m.from_user.id != ADMIN_ID:
        return
    admin_h.cmd_stats(bot, m)

@bot.message_handler(commands=['pending'])
def cmd_pending(m):
    if m.from_user.id != ADMIN_ID:
        return
    admin_h.cmd_pending(bot, m)

@bot.message_handler(commands=['accounts'])
def cmd_accounts(m):
    if m.from_user.id != ADMIN_ID:
        return
    admin_h.cmd_accounts(bot, m)

@bot.message_handler(commands=['broadcast'])
def cmd_broadcast(m):
    if m.from_user.id != ADMIN_ID:
        return
    text = m.text.partition(" ")[2]
    if not text:
        bot.reply_to(m, "Usage: /broadcast <message>")
        return
    admin_h.cmd_broadcast(bot, m, text)

@bot.message_handler(commands=['pay'])
def cmd_pay(m):
    if m.from_user.id != ADMIN_ID:
        return
    args = m.text.partition(" ")[2]
    admin_h.pay_command(bot, m, args)

# Admin accept/reject pattern: support both /accept_123 and /accept 123
@bot.message_handler(commands=['accept'])
def cmd_accept(m):
    if m.from_user.id != ADMIN_ID:
        return
    arg = m.text.partition(" ")[2] or m.text.replace("/accept_","")
    if not arg:
        bot.reply_to(m, "Usage: /accept <uid> or /accept_<uid>")
        return
    admin_h.accept_user(bot, arg)

@bot.message_handler(commands=['reject'])
def cmd_reject(m):
    if m.from_user.id != ADMIN_ID:
        return
    arg = m.text.partition(" ")[2] or m.text.replace("/reject_","")
    if not arg:
        bot.reply_to(m, "Usage: /reject <uid> or /reject_<uid>")
        return
    admin_h.reject_user(bot, arg)

# text messages handler (menu buttons and free text)
@bot.message_handler(func=lambda m: True)
def main_handler(m):
    users = load_users()
    ensure_user(users, m.from_user.id)
    L = start_h.get_locale(m.from_user)

    text = (m.text or "").strip()

    # Withdrawal flow
    if text == L.get("btn_withdraw"):
        balance_h.start_withdraw(bot, m, L)
        return

    # Balance
    if text == L.get("btn_balance"):
        balance_h.show_balance(bot, m, L)
        return

    # Referral link
    if text == L.get("btn_ref"):
        refs_h.send_ref(bot, m, L)
        return

    # Support
    if text == L.get("btn_support"):
        bot.send_message(m.chat.id, L.get("btn_support") + f": @{SUPPORT_USER}")
        return

    # Change language simple implementation - toggle
    if text == L.get("language"):
        # cycle languages
        users = load_users()
        u = users.get(str(m.from_user.id))
        current = u.get("lang") or DEFAULT_LANG
        idx = start_h.LANG.keys() if False else None  # placeholder
        # simple toggle for demonstration:
        new_lang = "en" if current == "ar" else "ar"
        u["lang"] = new_lang
        save_users(users)
        bot.send_message(m.chat.id, "تم تغيير اللغة.")
        start_h.cmd_start(bot, m)
        return

    # Tasks
    if text == L.get("btn_task"):
        tasks_h.request_task(bot, m, L)
        return

    # If user is currently in withdraw flow
    if balance_h.receive_withdraw_request(bot, m):
        return

    # If user submitted proof for a pending task
    if tasks_h.receive_proof(bot, m, L):
        return

    # default fallback
    bot.send_message(m.chat.id, "أمر غير معروف. استخدم الأزرار في القائمة.")
    logger.info("Unknown message from %s: %s", m.from_user.id, text)

if __name__ == "__main__":
    logger.info("Bot starting up...")
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        logger.exception("Bot crashed: %s", e)
