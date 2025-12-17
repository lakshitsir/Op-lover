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
app = Client("premium_lock_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---------------- DB ----------------
os.makedirs("data", exist_ok=True)
db = sqlite3.connect("data/bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS admins (uid INTEGER PRIMARY KEY)")
cur.execute("CREATE TABLE IF NOT EXISTS channels (val TEXT)")
cur.execute("""CREATE TABLE IF NOT EXISTS files (
token TEXT PRIMARY KEY,
file_id TEXT,
expiry INTEGER,
max_use INTEGER,
used INTEGER DEFAULT 0,
password TEXT
)""")
db.commit()

# ---------------- TEMP STATES ----------------
UPLOAD_STATE = {}

# ---------------- HELPERS ----------------
def is_owner(uid): return uid == OWNER_ID

def is_admin(uid):
    cur.execute("SELECT 1 FROM admins WHERE uid=?", (uid,))
    return cur.fetchone() or is_owner(uid)

def get_channels():
    cur.execute("SELECT val FROM channels")
    return [x[0] for x in cur.fetchall()]

def parse_expiry(text):
    if text == "0": return 0
    m = re.match(r"(\\d+)\\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hour|hours|d|day|days|y|year|years)", text.lower())
    if not m: return None
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
        await msg.reply("✨ **𝑾𝒆𝒍𝒄𝒐𝒎𝒆**\n🔐 Secure File Bot")
        return

    token = msg.command[1]
    cur.execute("SELECT * FROM files WHERE token=?", (token,))
    f = cur.fetchone()
    if not f:
        await msg.reply("❌ Invalid / Expired Link")
        return

    buttons = []
    for ch in get_channels():
        buttons.append([InlineKeyboardButton("📢 Join Channel", url=ch)])
    buttons.append([InlineKeyboardButton("✅ VERIFY", callback_data=f"verify|{token}")])

    await msg.reply(
        "🔒 **ACCESS LOCKED**\n\nJoin all channels then verify 👇",
        reply_markup=InlineKeyboardMarkup(buttons)
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

    cur.execute("SELECT * FROM files WHERE token=?", (token,))
    f = cur.fetchone()
    if not f:
        await cb.message.edit("❌ Invalid")
        return

    _, file_id, expiry, max_use, used, password = f

    if expiry and time.time() > expiry:
        await cb.message.edit("⏳ Link Expired")
        return

    if password:
        UPLOAD_STATE[uid] = ("pass", token)
        await cb.message.edit("🔐 **Enter Password**")
        return

    cur.execute("UPDATE files SET used=used+1 WHERE token=?", (token,))
    db.commit()
    await cb.message.delete()
    await app.send_document(uid, file_id)

# ---------------- PASSWORD INPUT ----------------
@app.on_message(filters.text)
async def text_handler(_, msg):
    uid = msg.from_user.id
    if uid not in UPLOAD_STATE: return

    mode, token = UPLOAD_STATE[uid]

    if mode == "pass":
        cur.execute("SELECT password FROM files WHERE token=?", (token,))
        real = cur.fetchone()[0]
        if msg.text != real:
            await msg.reply("❌ Wrong Password")
            return
        cur.execute("UPDATE files SET used=used+1 WHERE token=?", (token,))
        db.commit()
        del UPLOAD_STATE[uid]
        await app.send_document(uid, cur.execute("SELECT file_id FROM files WHERE token=?", (token,)).fetchone()[0])

# ---------------- ADMIN UPLOAD ----------------
@app.on_message(filters.command("upload") & filters.reply)
async def upload(_, msg):
    if not is_admin(msg.from_user.id): return
    token = uuid.uuid4().hex[:10]
    file_id = msg.reply_to_message.document.file_id
    UPLOAD_STATE[msg.from_user.id] = ("setpass", token, file_id)
    await msg.reply("🔐 Send password (0 = no password)")

@app.on_message(filters.text)
async def admin_flow(_, msg):
    uid = msg.from_user.id
    if uid not in UPLOAD_STATE: return

    state = UPLOAD_STATE[uid]

    if state[0] == "setpass":
        pwd = None if msg.text == "0" else msg.text[:20]
        UPLOAD_STATE[uid] = ("setexp", state[1], state[2], pwd)
        await msg.reply("⏳ Send expiry (e.g. 12h / 1 day / 0)")

    elif state[0] == "setexp":
        sec = parse_expiry(msg.text)
        if sec is None:
            await msg.reply("❌ Invalid format")
            return
        expiry = 0 if sec == 0 else int(time.time() + sec)
        token, file_id, pwd = state[1], state[2], state[3]
        cur.execute("INSERT INTO files VALUES (?,?,?,?,?,?)", (token, file_id, expiry, 0, 0, pwd))
        db.commit()
        del UPLOAD_STATE[uid]
        await msg.reply(f"✅ Link Created:\nhttps://t.me/{(await app.get_me()).username}?start={token}")

print("🔥 BOT RUNNING")
app.run()