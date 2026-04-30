import asyncio
import json
import logging
import os
import random
import string
from datetime import datetime, timedelta
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN  = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID   = int(os.getenv("ADMIN_ID", "123456789"))   # Ganti di Railway env var
EMAIL_DOMAIN = os.getenv("EMAIL_DOMAIN", "mail.com")   # Domain email custom
DB_FILE    = "accounts.json"
SLOTS      = ["A", "B", "C", "D", "E"]
CHECK_INTERVAL_HOURS = 6

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp  = Dispatcher(bot)

# ─── DATABASE HELPERS ─────────────────────────────────────────────────────────
def load_db() -> list:
    if not Path(DB_FILE).exists():
        return []
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data: list):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_account(index: int) -> dict | None:
    db = load_db()
    if 0 <= index < len(db):
        return db[index]
    return None

def update_account(index: int, data: dict):
    db = load_db()
    db[index] = data
    save_db(db)

# ─── UTILITIES ────────────────────────────────────────────────────────────────
def gen_email() -> str:
    prefix = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"{prefix}@{EMAIL_DOMAIN}"

def gen_password() -> str:
    chars = string.ascii_letters + string.digits + "!@#$%"
    return "".join(random.choices(chars, k=12))

def expiry_from_days(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).isoformat()

def days_left(expiry_iso: str) -> int:
    exp = datetime.fromisoformat(expiry_iso)
    return (exp - datetime.now()).days

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def fmt_account(idx: int, acc: dict, show_profiles=False) -> str:
    profiles = acc.get("profiles", {})
    filled   = len([v for v in profiles.values() if v])
    empty    = 5 - filled

    text = (
        f"<b>📦 Akun #{idx}</b>\n"
        f"📧 <code>{acc['email']}</code>\n"
        f"🔑 <code>{acc['password']}</code>\n"
        f"📌 Status: <b>{acc['status'].upper()}</b>\n"
        f"👥 Profil: {filled}/5 terisi | {empty} kosong\n"
    )

    if show_profiles and profiles:
        text += "\n<b>── Slot Profil ──</b>\n"
        for slot in SLOTS:
            exp_iso = profiles.get(slot)
            if exp_iso:
                dl = days_left(exp_iso)
                icon = "✅" if dl > 3 else ("⚠️" if dl >= 0 else "❌")
                text += f"  {icon} [{slot}] {profiles.get(slot+'_name', slot)} — {dl} hari\n"
            else:
                text += f"  ⬜ [{slot}] — kosong\n"

    return text

# ─── ADMIN CHECK DECORATOR ────────────────────────────────────────────────────
def admin_only(func):
    async def wrapper(message: types.Message, *args, **kwargs):
        if not is_admin(message.from_user.id):
            await message.reply("⛔ Akses ditolak.")
            return
        return await func(message, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

# ─── COMMANDS ─────────────────────────────────────────────────────────────────

@dp.message_handler(commands=["start", "help"])
async def cmd_help(message: types.Message):
    text = (
        "🎬 <b>Netflix Manager Bot</b>\n\n"
        "<b>── Akun ──</b>\n"
        "/create — Generate akun baru\n"
        "/list — Lihat semua akun\n"
        "/quick — Ambil akun unused otomatis\n"
        "/status <i>index status</i> — Update status akun\n"
        "/delete <i>index</i> — Hapus akun\n\n"
        "<b>── Profil / Buyer ──</b>\n"
        "/addprofile <i>index slot nama hari</i>\n"
        "/listprofile <i>index</i>\n"
        "/extendprofile <i>index slot hari</i>\n"
        "/delprofile <i>index slot</i>\n\n"
        "<b>── Lainnya ──</b>\n"
        "/dashboard — Statistik lengkap\n"
        "/export — Export semua akun ke .txt\n\n"
        "<i>Contoh: /addprofile 0 A Budi 30</i>"
    )
    await message.reply(text)


@dp.message_handler(commands=["create"])
@admin_only
async def cmd_create(message: types.Message):
    db = load_db()
    new_acc = {
        "email":    gen_email(),
        "password": gen_password(),
        "status":   "unused",
        "profiles": {s: None for s in SLOTS},
    }
    db.append(new_acc)
    save_db(db)
    idx = len(db) - 1

    await message.reply(
        f"✅ <b>Akun #{idx} berhasil dibuat!</b>\n\n"
        f"📧 <code>{new_acc['email']}</code>\n"
        f"🔑 <code>{new_acc['password']}</code>\n"
        f"📌 Status: UNUSED"
    )


@dp.message_handler(commands=["list"])
@admin_only
async def cmd_list(message: types.Message):
    db = load_db()
    if not db:
        await message.reply("📭 Belum ada akun.")
        return

    text = f"📋 <b>Total Akun: {len(db)}</b>\n\n"
    for i, acc in enumerate(db):
        profiles  = acc.get("profiles", {})
        filled    = len([v for v in profiles.values() if v])
        icon_map  = {"unused": "⚪", "used": "🔵", "active": "🟢",
                     "failed": "🔴", "refund": "🟠", "expired": "⛔"}
        icon = icon_map.get(acc["status"], "❓")
        text += f"{icon} <b>#{i}</b> {acc['email']} | {acc['status']} | {filled}/5\n"

    await message.reply(text)


@dp.message_handler(commands=["quick"])
@admin_only
async def cmd_quick(message: types.Message):
    db = load_db()
    unused = [(i, a) for i, a in enumerate(db) if a["status"] == "unused"]
    if not unused:
        await message.reply("😔 Tidak ada akun <b>unused</b> saat ini.")
        return

    idx, acc = random.choice(unused)
    acc["status"] = "used"
    update_account(idx, acc)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🎬 Buka Netflix", url="https://netflix.com"))

    await message.reply(
        f"🎯 <b>Akun #{idx} siap digunakan!</b>\n\n"
        f"📧 <code>{acc['email']}</code>\n"
        f"🔑 <code>{acc['password']}</code>\n"
        f"📌 Status: USED",
        reply_markup=kb
    )


@dp.message_handler(commands=["status"])
@admin_only
async def cmd_status(message: types.Message):
    args = message.get_args().split()
    valid = ["unused", "used", "active", "failed", "refund", "expired"]

    if len(args) < 2:
        await message.reply("⚠️ Format: /status <i>index status</i>\nStatus valid: " + ", ".join(valid))
        return

    try:
        idx    = int(args[0])
        status = args[1].lower()
    except ValueError:
        await message.reply("⚠️ Index harus angka.")
        return

    if status not in valid:
        await message.reply(f"⚠️ Status tidak valid. Pilihan: {', '.join(valid)}")
        return

    acc = get_account(idx)
    if not acc:
        await message.reply(f"⚠️ Akun #{idx} tidak ditemukan.")
        return

    acc["status"] = status
    update_account(idx, acc)

    # Auto recycle
    if status in ["failed", "refund"]:
        await bot.send_message(ADMIN_ID, f"🚨 <b>Alert!</b> Akun #{idx} di-mark sebagai <b>{status.upper()}</b>.\n"
                                          f"📧 {acc['email']}\n⚙️ Auto-recycle ke UNUSED.")
        acc["status"] = "unused"
        update_account(idx, acc)
        await message.reply(f"✅ Status akun #{idx} → <b>{status.upper()}</b>\n♻️ Auto-recycle → <b>UNUSED</b>")
    else:
        await message.reply(f"✅ Status akun #{idx} → <b>{status.upper()}</b>")


@dp.message_handler(commands=["delete"])
@admin_only
async def cmd_delete(message: types.Message):
    args = message.get_args().split()
    if not args:
        await message.reply("⚠️ Format: /delete <i>index</i>")
        return
    try:
        idx = int(args[0])
    except ValueError:
        await message.reply("⚠️ Index harus angka.")
        return

    db = load_db()
    if idx < 0 or idx >= len(db):
        await message.reply(f"⚠️ Akun #{idx} tidak ditemukan.")
        return

    removed = db.pop(idx)
    save_db(db)
    await message.reply(f"🗑️ Akun #{idx} ({removed['email']}) berhasil dihapus.")


# ─── PROFILE MANAGEMENT ───────────────────────────────────────────────────────

@dp.message_handler(commands=["addprofile"])
@admin_only
async def cmd_addprofile(message: types.Message):
    # /addprofile 0 A Budi 30
    args = message.get_args().split()
    if len(args) < 4:
        await message.reply("⚠️ Format: /addprofile <i>index slot nama hari</i>\nContoh: /addprofile 0 A Budi 30")
        return

    try:
        idx  = int(args[0])
        slot = args[1].upper()
        nama = args[2]
        days = int(args[3])
    except (ValueError, IndexError):
        await message.reply("⚠️ Cek format perintah.")
        return

    if slot not in SLOTS:
        await message.reply(f"⚠️ Slot tidak valid. Pilih: {', '.join(SLOTS)}")
        return

    acc = get_account(idx)
    if not acc:
        await message.reply(f"⚠️ Akun #{idx} tidak ditemukan.")
        return

    if acc["profiles"].get(slot):
        dl = days_left(acc["profiles"][slot])
        await message.reply(f"⚠️ Slot {slot} sudah terisi oleh <b>{acc['profiles'].get(slot+'_name', '?')}</b> ({dl} hari lagi).\nGunakan /extendprofile atau /delprofile dulu.")
        return

    acc["profiles"][slot]           = expiry_from_days(days)
    acc["profiles"][f"{slot}_name"] = nama
    update_account(idx, acc)

    exp_str = (datetime.now() + timedelta(days=days)).strftime("%d %b %Y")
    await message.reply(
        f"✅ <b>Profil ditambahkan!</b>\n\n"
        f"📦 Akun #{idx} | Slot [{slot}]\n"
        f"👤 Nama: <b>{nama}</b>\n"
        f"📅 Aktif: {days} hari (s/d {exp_str})"
    )


@dp.message_handler(commands=["listprofile"])
@admin_only
async def cmd_listprofile(message: types.Message):
    args = message.get_args().split()
    if not args:
        await message.reply("⚠️ Format: /listprofile <i>index</i>")
        return

    try:
        idx = int(args[0])
    except ValueError:
        await message.reply("⚠️ Index harus angka.")
        return

    acc = get_account(idx)
    if not acc:
        await message.reply(f"⚠️ Akun #{idx} tidak ditemukan.")
        return

    await message.reply(fmt_account(idx, acc, show_profiles=True))


@dp.message_handler(commands=["extendprofile"])
@admin_only
async def cmd_extendprofile(message: types.Message):
    # /extendprofile 0 A 30
    args = message.get_args().split()
    if len(args) < 3:
        await message.reply("⚠️ Format: /extendprofile <i>index slot hari</i>")
        return

    try:
        idx  = int(args[0])
        slot = args[1].upper()
        days = int(args[2])
    except ValueError:
        await message.reply("⚠️ Cek format perintah.")
        return

    acc = get_account(idx)
    if not acc:
        await message.reply(f"⚠️ Akun #{idx} tidak ditemukan.")
        return

    if slot not in SLOTS:
        await message.reply(f"⚠️ Slot tidak valid. Pilih: {', '.join(SLOTS)}")
        return

    current = acc["profiles"].get(slot)
    if not current:
        await message.reply(f"⚠️ Slot {slot} masih kosong. Gunakan /addprofile dulu.")
        return

    # Extend dari expiry saat ini (atau dari sekarang jika sudah expired)
    base = datetime.fromisoformat(current)
    if base < datetime.now():
        base = datetime.now()
    new_exp = (base + timedelta(days=days)).isoformat()
    acc["profiles"][slot] = new_exp
    update_account(idx, acc)

    nama    = acc["profiles"].get(f"{slot}_name", slot)
    exp_str = datetime.fromisoformat(new_exp).strftime("%d %b %Y")
    await message.reply(
        f"✅ <b>Profil diperpanjang!</b>\n\n"
        f"📦 Akun #{idx} | Slot [{slot}] {nama}\n"
        f"➕ Tambah: {days} hari\n"
        f"📅 Baru aktif s/d: {exp_str}"
    )


@dp.message_handler(commands=["delprofile"])
@admin_only
async def cmd_delprofile(message: types.Message):
    # /delprofile 0 A
    args = message.get_args().split()
    if len(args) < 2:
        await message.reply("⚠️ Format: /delprofile <i>index slot</i>")
        return

    try:
        idx  = int(args[0])
        slot = args[1].upper()
    except ValueError:
        await message.reply("⚠️ Cek format perintah.")
        return

    acc = get_account(idx)
    if not acc:
        await message.reply(f"⚠️ Akun #{idx} tidak ditemukan.")
        return

    if slot not in SLOTS:
        await message.reply(f"⚠️ Slot tidak valid. Pilih: {', '.join(SLOTS)}")
        return

    nama = acc["profiles"].get(f"{slot}_name", slot)
    acc["profiles"][slot]           = None
    acc["profiles"][f"{slot}_name"] = None
    update_account(idx, acc)

    await message.reply(f"🗑️ Profil [{slot}] <b>{nama}</b> di akun #{idx} berhasil dihapus. Slot kini kosong.")


# ─── DASHBOARD ────────────────────────────────────────────────────────────────

@dp.message_handler(commands=["dashboard"])
@admin_only
async def cmd_dashboard(message: types.Message):
    db          = load_db()
    total_acc   = len(db)
    total_slots = total_acc * 5

    filled = expired_soon = 0
    soon_list = []

    for i, acc in enumerate(db):
        for slot in SLOTS:
            exp = acc["profiles"].get(slot)
            if exp:
                filled += 1
                dl = days_left(exp)
                if dl <= 3:
                    expired_soon += 1
                    nama = acc["profiles"].get(f"{slot}_name", slot)
                    soon_list.append(f"  ⚠️ Akun #{i} [{slot}] {nama} — {dl} hari lagi")

    status_count = {}
    for acc in db:
        s = acc["status"]
        status_count[s] = status_count.get(s, 0) + 1

    status_text = "\n".join([f"  • {k.upper()}: {v}" for k, v in status_count.items()]) or "  (kosong)"
    soon_text   = "\n".join(soon_list) if soon_list else "  ✅ Semua aman"

    text = (
        f"📊 <b>Dashboard Netflix Manager</b>\n"
        f"─────────────────────────\n"
        f"📦 Total Akun    : {total_acc}\n"
        f"🎰 Total Slot    : {total_slots}\n"
        f"✅ Terisi         : {filled}\n"
        f"⬜ Kosong         : {total_slots - filled}\n"
        f"⚠️ Akan Expired   : {expired_soon}\n\n"
        f"<b>Status Akun:</b>\n{status_text}\n\n"
        f"<b>Profil Hampir Expired:</b>\n{soon_text}"
    )
    await message.reply(text)


# ─── EXPORT ───────────────────────────────────────────────────────────────────

@dp.message_handler(commands=["export"])
@admin_only
async def cmd_export(message: types.Message):
    db = load_db()
    if not db:
        await message.reply("📭 Tidak ada data untuk diekspor.")
        return

    lines = [f"{a['email']}|{a['password']}|{a['status']}" for a in db]
    content = "\n".join(lines)

    with open("export.txt", "w") as f:
        f.write(content)

    with open("export.txt", "rb") as f:
        await bot.send_document(
            message.chat.id,
            f,
            caption=f"📤 Export selesai — {len(db)} akun\n🕐 {datetime.now().strftime('%d %b %Y %H:%M')}"
        )


# ─── AUTO BACKGROUND TASK ─────────────────────────────────────────────────────

async def auto_check():
    """Jalan setiap CHECK_INTERVAL_HOURS jam — cek expiry & recycle."""
    await asyncio.sleep(10)  # Delay awal biar bot ready dulu
    while True:
        log.info("🔄 Auto check berjalan...")
        db = load_db()
        modified = False

        for i, acc in enumerate(db):
            # Auto recycle failed/refund (jaga-jaga kalau belum ter-recycle via /status)
            if acc["status"] in ["failed", "refund"]:
                acc["status"] = "unused"
                modified = True
                log.info(f"♻️ Akun #{i} di-recycle ke unused")

            for slot in SLOTS:
                exp = acc["profiles"].get(slot)
                if not exp:
                    continue

                dl   = days_left(exp)
                nama = acc["profiles"].get(f"{slot}_name", slot)

                if dl == 3:
                    await bot.send_message(ADMIN_ID,
                        f"⚠️ <b>Reminder H-3</b>\n"
                        f"📦 Akun #{i} [{slot}] <b>{nama}</b>\n"
                        f"📅 Expired dalam 3 hari!")
                elif dl == 1:
                    await bot.send_message(ADMIN_ID,
                        f"🚨 <b>Reminder H-1</b>\n"
                        f"📦 Akun #{i} [{slot}] <b>{nama}</b>\n"
                        f"📅 Expired BESOK!")
                elif dl < 0:
                    # Hapus profil expired
                    acc["profiles"][slot]           = None
                    acc["profiles"][f"{slot}_name"] = None
                    modified = True
                    log.info(f"🗑️ Profil #{i}[{slot}] {nama} dihapus (expired)")
                    await bot.send_message(ADMIN_ID,
                        f"❌ <b>Profil Expired & Dihapus</b>\n"
                        f"📦 Akun #{i} [{slot}] <b>{nama}</b>\n"
                        f"Slot [{slot}] kini kosong.")

        if modified:
            save_db(db)

        await asyncio.sleep(CHECK_INTERVAL_HOURS * 3600)


async def on_startup(dp):
    log.info("🚀 Bot started!")
    asyncio.create_task(auto_check())


# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Pastikan file DB ada
    if not Path(DB_FILE).exists():
        save_db([])
        log.info(f"📁 {DB_FILE} dibuat (kosong).")

    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)
      
