# ======================================================
# STABLE FILE LOCK BOT (FINAL)
# Pyrogram v2 | Render + Termux
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
    "stable_file_lock_bot",
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
    used INTEGER DEFAULT 0,
    password TEXT
)
""")
db.commit()

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

def normalize_channel(v):
    v = v.strip()
    if v.startswith("@"):
        return v
    if v.startswith("https://t.me/") or v.startswith("http://t.me/"):
        return v
    return None

def parse_expiry(t):
    if t == "0":
        return 0
    m = re.match(
        r"(\d+)\s*(s|sec|m|min|h|hr|d|day|y|year)",
        t.lower()
    )
    if not m:
        return None
    n = int(m.group(1))
    u = m.group(2)
    if u.startswith("s"): return n
    if u.startswith("m"): return n * 60
    if u.startswith("h"): return n * 3600
    if u.startswith("d"): return n * 86400
    if u.startswith("y"): return n * 31536000

# ---------------- START ----------------
@app.on_message(filters.command("start"))
async def start(_, msg):
    if len(msg.command) == 1:
        await msg.reply(
            "✨ **WELCOME** ✨\n\n"
            "🔐 **SECURE FILE BOT**\n\n"
            "File access requires channel join.\n"
            "Open your special link to continue.",
            disable_web_page_preview=True
        )
        return

    token = msg.command[1]
    cur.execute("SELECT 1 FROM files WHERE token=?", (token,))
    if not cur.fetchone():
        await msg.reply("❌ Invalid / Expired Link")
        return

    buttons = [[InlineKeyboardButton("📢 JOIN CHANNEL", url=c)] for c in get_channels()]
    buttons.append([InlineKeyboardButton("✅ VERIFY", callback_data=f"v|{token}")])

    await msg.reply(
        "🔒 **ACCESS LOCKED**\n\nJoin all channels then verify.",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ---------------- VERIFY ----------------
@app.on_callback_query(filters.regex("^v\\|"))
async def verify(_, cb):
    token = cb.data.split("|", 1)[1]
    uid = cb.from_user.id

    for ch in get_channels():
        try:
            await app.get_chat_member(ch, uid)
        except UserNotParticipant:
            await cb.answer("❌ Join ALL channels", show_alert=True)
            return

    cur.execute("SELECT file_id, expiry, password FROM files WHERE token=?", (token,))
    row = cur.fetchone()
    if not row:
        await cb.message.edit("❌ Invalid")
        return

    file_id, expiry, password = row

    if expiry and time.time() > expiry:
        await cb.message.edit("⏳ Link Expired")
        return

    if password:
        STATE[uid] = ("pass", token)
        await cb.message.edit("🔐 Enter Password")
        return

    cur.execute("UPDATE files SET used=used+1 WHERE token=?", (token,))
    db.commit()
    await cb.message.delete()
    await app.send_document(uid, file_id)

# ---------------- TEXT (NON COMMAND) ----------------
@app.on_message(filters.text & ~filters.regex(r"^/"))
async def text_handler(_, msg):
    uid = msg.from_user.id
    if uid not in STATE:
        return

    st = STATE[uid]

    if st[0] == "pass":
        token = st[1]
        cur.execute("SELECT file_id, password FROM files WHERE token=?", (token,))
        file_id, real = cur.fetchone()
        if msg.text != real:
            await msg.reply("❌ Wrong Password")
            return
        cur.execute("UPDATE files SET used=used+1 WHERE token=?", (token,))
        db.commit()
        del STATE[uid]
        await app.send_document(uid, file_id)

    elif st[0] == "setpass":
        pwd = None if msg.text == "0" else msg.text[:20]
        STATE[uid] = ("setexp", st[1], st[2], pwd)
        await msg.reply("⏳ Send expiry (12h / 1d / 0)")

    elif st[0] == "setexp":
        sec = parse_expiry(msg.text)
        if sec is None:
            await msg.reply("❌ Invalid expiry")
            return
        expiry = 0 if sec == 0 else int(time.time() + sec)
        token, file_id, pwd = st[1], st[2], st[3]
        cur.execute(
            "INSERT INTO files VALUES (?,?,?,?,?)",
            (token, file_id, expiry, 0, pwd)
        )
        db.commit()
        del STATE[uid]
        await msg.reply(
            f"✅ Link Created:\nhttps://t.me/{(await app.get_me()).username}?start={token}"
        )

# ---------------- ADMIN ----------------
@app.on_message(filters.command("upload") & filters.reply)
async def upload(_, msg):
    if not is_admin(msg.from_user.id):
        return
    token = uuid.uuid4().hex[:10]
    file_id = msg.reply_to_message.document.file_id
    STATE[msg.from_user.id] = ("setpass", token, file_id)
    await msg.reply("🔐 Send password (0 = no password)")

@app.on_message(filters.command("addchannel"))
async def add_channel(_, msg):
    if not is_admin(msg.from_user.id):
        return
    ch = normalize_channel(msg.command[1])
    if not ch:
        await msg.reply("❌ Use @username or t.me link")
        return
    cur.execute("INSERT INTO channels VALUES (?)", (ch,))
    db.commit()
    await msg.reply("✅ Channel Added")

@app.on_message(filters.command("promote"))
async def promote(_, msg):
    if not is_owner(msg.from_user.id):
        return
    uid = int(msg.command[1])
    cur.execute("INSERT OR IGNORE INTO admins VALUES (?)", (uid,))
    db.commit()
    await msg.reply(f"✅ Promoted {uid}")

@app.on_message(filters.command("demote"))
async def demote(_, msg):
    if not is_owner(msg.from_user.id):
        return
    uid = int(msg.command[1])
    cur.execute("DELETE FROM admins WHERE uid=?", (uid,))
    db.commit()
    await msg.reply(f"❌ Demoted {uid}")

print("✅ BOT RUNNING (STABLE)")
app.run()
