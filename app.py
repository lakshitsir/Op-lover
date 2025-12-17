# ======================================================
# PREMIUM HARD-LOCK FILE BOT
# PASSWORD + EXPIRY | RENDER + TERMUX
# ======================================================

import os, time, uuid, sqlite3, re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# ---------------- CONFIG ----------------
API_ID = 12767104
API_HASH = "a0ce1daccf78234927eb68a62f894b97"
BOT_TOKEN = "8373581806:AAE46Kn4jgWh6l_R-tonKh4fA-TTvN_H71w"
OWNER_ID = 5421311764

# ---------------- APP ----------------
app = Client(
    "premium_lock_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ---------------- DB ----------------
os.makedirs("data", exist_ok=True)
db = sqlite3.connect("data/bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS admins (uid INTEGER PRIMARY KEY)")
cur.execute("CREATE TABLE IF NOT EXISTS channels (val TEXT)")
cur.execute("""
CREATE TABLE IF NOT EXISTS files (
    token TEXT PRIMARY KEY,
    file_id TEXT,
    expiry INTEGER,
    max_use INTEGER,
    used INTEGER DEFAULT 0,
    password TEXT
)
""")
db.commit()

# ---------------- TEMP STATE ----------------
STATE = {}

# ---------------- HELPERS ----------------
def is_owner(uid):
    return uid == OWNER_ID

def is_admin(uid):
    cur.execute("SELECT 1 FROM admins WHERE uid=?", (uid,))
    return cur.fetchone() is not None or is_owner(uid)

def get_channels():
    cur.execute("SELECT val FROM channels")
    return [x[0] for x in cur.fetchall()]

def normalize_channel(val: str):
    val = val.strip()
    if val.startswith("@"):
        return val
    if val.startswith("https://t.me/") or val.startswith("http://t.me/"):
        return val
    return None

def parse_expiry(text):
    if text == "0":
        return 0
    m = re.match(
        r"(\d+)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hour|hours|d|day|days|y|year|years)",
        text.lower()
    )
    if not m:
        return None
    num = int(m.group(1))
    unit = m.group(2)
    if unit.startswith("s"): return num
    if unit.startswith("m"): return num * 60
    if unit.startswith("h"): return num * 3600
    if unit.startswith("d"): return num * 86400
    if unit.startswith("y"): return num * 31536000

# ---------------- START ----------------
@app.on_message(filters.command("start"))
async def start(_, msg):
    if len(msg.command) == 1:
        await msg.reply(
            "✨ **𝙒𝙀𝙇𝘾𝙊𝙈𝙀** ✨\n\n"
            "🔐 **𝙋𝙍𝙀𝙈𝙄𝙐𝙈 𝙎𝙀𝘾𝙐𝙍𝙀 𝙁𝙄𝙇𝙀 𝘽𝙊𝙏**\n\n"
            "📥 File access is protected by:\n"
            "• Mandatory Channel Join\n"
            "• Password Protection\n"
            "• Expiry Locked Links\n\n"
            "🔓 Open your special link to continue.",
            disable_web_page_preview=True
        )
        return

    token = msg.command[1]
    cur.execute("SELECT 1 FROM files WHERE token=?", (token,))
    if not cur.fetchone():
        await msg.reply("❌ **Invalid or Expired Link**")
        return

    buttons = []
    for ch in get_channels():
        buttons.append([InlineKeyboardButton("📢 JOIN CHANNEL", url=ch)])
    buttons.append([InlineKeyboardButton("✅ VERIFY ACCESS", callback_data=f"verify|{token}")])

    await msg.reply(
        "🔒 **ACCESS LOCKED**\n\n"
        "📢 Join **ALL** required channels below 👇\n"
        "⚠️ Even one missing = verification fail.\n\n"
        "After joining, tap **VERIFY ACCESS** ✅",
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True
    )

# ---------------- VERIFY ----------------
@app.on_callback_query(filters.regex("^verify"))
async def verify(_, cb):
    token = cb.data.split("|")[1]
    uid = cb.from_user.id

    for ch in get_channels():
        try:
            await app.get_chat_member(ch, uid)
        except UserNotParticipant:
            await cb.answer("❌ Join ALL channels", show_alert=True)
            return
        except Exception:
            await cb.answer("❌ Verification Failed", show_alert=True)
            return

    cur.execute("SELECT file_id, expiry, used, password FROM files WHERE token=?", (token,))
    row = cur.fetchone()
    if not row:
        await cb.message.edit("❌ Invalid")
        return

    file_id, expiry, used, password = row

    if expiry and time.time() > expiry:
        await cb.message.edit("⏳ Link Expired")
        return

    if password:
        STATE[uid] = ("user_pass", token)
        await cb.message.edit("🔐 **Enter Password**")
        return

    cur.execute("UPDATE files SET used=used+1 WHERE token=?", (token,))
    db.commit()
    await cb.message.delete()
    await app.send_document(uid, file_id)

# ---------------- TEXT HANDLER ----------------
@app.on_message(filters.text & ~filters.command)
async def text_handler(_, msg):
    uid = msg.from_user.id
    if uid not in STATE:
        return

    state = STATE[uid]

    if state[0] == "user_pass":
        token = state[1]
        cur.execute("SELECT file_id, password FROM files WHERE token=?", (token,))
        file_id, real = cur.fetchone()
        if msg.text != real:
            await msg.reply("❌ Wrong Password")
            return
        cur.execute("UPDATE files SET used=used+1 WHERE token=?", (token,))
        db.commit()
        del STATE[uid]
        await app.send_document(uid, file_id)

    elif state[0] == "setpass":
        pwd = None if msg.text == "0" else msg.text[:20]
        STATE[uid] = ("setexp", state[1], state[2], pwd)
        await msg.reply("⏳ Send expiry (12h / 1 day / 0)")

    elif state[0] == "setexp":
        sec = parse_expiry(msg.text)
        if sec is None:
            await msg.reply("❌ Invalid expiry format")
            return
        expiry = 0 if sec == 0 else int(time.time() + sec)
        token, file_id, pwd = state[1], state[2], state[3]
        cur.execute(
            "INSERT INTO files VALUES (?,?,?,?,?,?)",
            (token, file_id, expiry, 0, 0, pwd)
        )
        db.commit()
        del STATE[uid]
        await msg.reply(
            f"✅ **Link Created**\n\n"
            f"https://t.me/{(await app.get_me()).username}?start={token}",
            disable_web_page_preview=True
        )

# ---------------- ADMIN COMMANDS ----------------
@app.on_message(filters.command("upload") & filters.reply)
async def upload(_, msg):
    if not is_admin(msg.from_user.id):
        return
    token = uuid.uuid4().hex[:10]
    file_id = msg.reply_to_message.document.file_id
    STATE[msg.from_user.id] = ("setpass", token, file_id)
    await msg.reply("🔐 Send password (0 = no password)")

@app.on_message(filters.command("promote"))
async def promote(_, msg):
    if not is_owner(msg.from_user.id):
        return
    uid = int(msg.command[1])
    cur.execute("INSERT OR IGNORE INTO admins VALUES (?)", (uid,))
    db.commit()
    await msg.reply("✅ User Promoted")

@app.on_message(filters.command("demote"))
async def demote(_, msg):
    if not is_owner(msg.from_user.id):
        return
    uid = int(msg.command[1])
    cur.execute("DELETE FROM admins WHERE uid=?", (uid,))
    db.commit()
    await msg.reply("❌ User Demoted")

@app.on_message(filters.command("help"))
async def help_cmd(_, msg):
    if not is_admin(msg.from_user.id):
        return
    await msg.reply(
        "🛠 **ADMIN HELP**\n\n"
        "/upload (reply file)\n"
        "/addchannel @username OR t.me link\n"
        "/removechannel value\n"
        "/listchannels\n"
        "/stats\n\n"
        "/promote user_id (OWNER)\n"
        "/demote user_id (OWNER)",
        disable_web_page_preview=True
    )

# ---------------- STATS ----------------
@app.on_message(filters.command("stats"))
async def stats_cmd(_, msg):
    if not is_admin(msg.from_user.id):
        return

    cur.execute("SELECT COUNT(*) FROM admins")
    admins = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM channels")
    channels = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM files")
    files = cur.fetchone()[0]

    cur.execute("SELECT SUM(used) FROM files")
    used = cur.fetchone()[0] or 0

    now = int(time.time())
    cur.execute("SELECT COUNT(*) FROM files WHERE expiry = 0 OR expiry > ?", (now,))
    active = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM files WHERE expiry != 0 AND expiry <= ?", (now,))
    expired = cur.fetchone()[0]

    await msg.reply(
        "📊 **BOT STATISTICS**\n\n"
        f"👑 Admins: `{admins}`\n"
        f"📢 Channels: `{channels}`\n"
        f"📦 Files Created: `{files}`\n"
        f"🔓 Total Access: `{used}`\n"
        f"⏳ Active Links: `{active}`\n"
        f"❌ Expired Links: `{expired}`",
        disable_web_page_preview=True
    )

# ---------------- CHANNEL MGMT ----------------
@app.on_message(filters.command("addchannel"))
async def add_channel(_, msg):
    if not is_admin(msg.from_user.id):
        return
    raw = msg.command[1]
    ch = normalize_channel(raw)
    if not ch:
        await msg.reply("❌ Invalid channel\nUse @username or t.me link")
        return
    cur.execute("INSERT INTO channels VALUES (?)", (ch,))
    db.commit()
    await msg.reply("✅ Channel Added")

@app.on_message(filters.command("removechannel"))
async def remove_channel(_, msg):
    if not is_admin(msg.from_user.id):
        return
    ch = msg.command[1]
    cur.execute("DELETE FROM channels WHERE val=?", (ch,))
    db.commit()
    await msg.reply("🗑 Channel Removed")

@app.on_message(filters.command("listchannels"))
async def list_channels(_, msg):
    if not is_admin(msg.from_user.id):
        return
    txt = "\n".join(get_channels()) or "No channels"
    await msg.reply(f"📢 **Channels**:\n{txt}", disable_web_page_preview=True)

print("🔥 BOT RUNNING – FINAL WITH STATS")
app.run()
