import os
import asyncio
import logging
from datetime import datetime, date, timezone
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import aiosqlite

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
DB_PATH = os.getenv("DB_PATH", "data/sollaner.sqlite3")
POINTS_PER_MESSAGE = int(os.getenv("POINTS_PER_MESSAGE", "1"))
MESSAGE_COOLDOWN = int(os.getenv("MESSAGE_COOLDOWN", "60"))
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "20"))
DAILY_BONUS = int(os.getenv("DAILY_BONUS", "3"))
REWARD_COST = int(os.getenv("REWARD_COST", "100"))
GROUP_ID = os.getenv("GROUP_ID", "").strip()

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()
os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            points INTEGER NOT NULL DEFAULT 0,
            last_message TEXT,
            message_day TEXT,
            daily_count INTEGER NOT NULL DEFAULT 0,
            last_daily TEXT
        );
        CREATE TABLE IF NOT EXISTS rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            cost INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            reward_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        );
        """)
        cur = await db.execute("SELECT COUNT(*) FROM rewards")
        count = (await cur.fetchone())[0]
        if count == 0:
            await db.executemany("INSERT INTO rewards(title,cost) VALUES(?,?)", [
                ("Обычный Telegram-подарок", REWARD_COST),
                ("Особый Telegram-подарок", REWARD_COST * 3)
            ])
        await db.commit()

async def upsert_user(user):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT INTO users(user_id, username, first_name) VALUES(?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name
        """, (user.id, user.username or "", user.first_name or ""))
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0

@dp.message(CommandStart())
async def start(message: Message):
    await upsert_user(message.from_user)
    await message.answer(
        "🎁 <b>Sollaner Rewards</b>\n\n"
        "Общайся в чате, зарабатывай баллы и обменивай их на подарки.\n\n"
        "/profile — профиль\n/top — рейтинг\n/daily — ежедневный бонус\n/rewards — магазин наград\n/help — помощь"
    )

@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "🎮 <b>Команды Sollaner Rewards</b>\n"
        "/profile — твои баллы\n/top — топ участников\n/daily — бонус раз в день\n"
        "/rewards — каталог подарков\n/redeem ID — запросить награду\n/myid — узнать свой Telegram ID"
    )

@dp.message(Command("myid"))
async def myid(message: Message):
    await message.answer(f"Твой Telegram ID: <code>{message.from_user.id}</code>")

@dp.message(Command("profile"))
async def profile(message: Message):
    await upsert_user(message.from_user)
    pts = await get_user(message.from_user.id)
    await message.answer(f"👤 <b>{message.from_user.first_name}</b>\nБаланс: <b>{pts}</b> баллов")

@dp.message(Command("daily"))
async def daily(message: Message):
    await upsert_user(message.from_user)
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT last_daily FROM users WHERE user_id=?", (message.from_user.id,))
        row = await cur.fetchone()
        if row and row[0] == today:
            await message.answer("Ты уже забирал ежедневный бонус. Возвращайся завтра!")
            return
        await db.execute("UPDATE users SET points=points+?, last_daily=? WHERE user_id=?",
                         (DAILY_BONUS, today, message.from_user.id))
        await db.commit()
    await message.answer(f"🎉 Ежедневный бонус: +{DAILY_BONUS} балла!")

@dp.message(Command("top"))
async def top(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT first_name, username, points FROM users ORDER BY points DESC LIMIT 10")
        rows = await cur.fetchall()
    if not rows:
        await message.answer("Пока рейтинг пуст.")
        return
    lines = ["🏆 <b>ТОП-10 Sollaner</b>"]
    for i, (name, username, points) in enumerate(rows, 1):
        label = f"@{username}" if username else name
        lines.append(f"{i}. {label} — <b>{points}</b>")
    await message.answer("\n".join(lines))

@dp.message(Command("rewards"))
async def rewards(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, title, cost FROM rewards WHERE active=1 ORDER BY cost")
        rows = await cur.fetchall()
    lines = ["🎁 <b>Магазин наград</b>"]
    for rid, title, cost in rows:
        lines.append(f"\n<b>#{rid} {title}</b> — {cost} баллов\nЗапрос: <code>/redeem {rid}</code>")
    await message.answer("\n".join(lines))

@dp.message(Command("redeem"))
async def redeem(message: Message, bot: Bot):
    await upsert_user(message.from_user)
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /redeem ID\nПосмотри каталог: /rewards")
        return
    rid = int(parts[1])
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT title, cost FROM rewards WHERE id=? AND active=1", (rid,))
        reward = await cur.fetchone()
        if not reward:
            await message.answer("Такой награды нет.")
            return
        title, cost = reward
        cur = await db.execute("SELECT points FROM users WHERE user_id=?", (message.from_user.id,))
        points = (await cur.fetchone())[0]
        if points < cost:
            await message.answer(f"Не хватает баллов. Нужно {cost}, у тебя {points}.")
            return
        # Reserve points at request creation to prevent duplicate spending.
        await db.execute("UPDATE users SET points=points-? WHERE user_id=?", (cost, message.from_user.id))
        cur = await db.execute(
            "INSERT INTO requests(user_id,reward_id,created_at) VALUES(?,?,?)",
            (message.from_user.id, rid, datetime.now(timezone.utc).isoformat())
        )
        req_id = cur.lastrowid
        await db.commit()

    await message.answer(f"✅ Заявка #{req_id} отправлена администратору. Баллы зарезервированы.")
    if ADMIN_IDS:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{req_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{req_id}")
        ]])
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"🎁 <b>Новая заявка #{req_id}</b>\n"
                    f"Участник: {message.from_user.full_name} (<code>{message.from_user.id}</code>)\n"
                    f"Награда: {title}\nСтоимость: {cost} баллов\n\n"
                    "Одобрение означает, что ты берёшь на себя ручную отправку подарка через Telegram.",
                    reply_markup=kb
                )
            except Exception:
                logging.exception("Cannot notify admin %s", admin_id)

@dp.callback_query(F.data.startswith("approve:"))
async def approve(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    req_id = int(call.data.split(":")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id, status FROM requests WHERE id=?", (req_id,))
        row = await cur.fetchone()
        if not row or row[1] != "pending":
            await call.answer("Заявка уже обработана", show_alert=True)
            return
        user_id = row[0]
        await db.execute("UPDATE requests SET status='approved' WHERE id=?", (req_id,))
        await db.commit()
    await bot.send_message(user_id, f"🎉 Твоя заявка #{req_id} одобрена!\nАдминистратор выдаст подарок вручную.")
    await call.message.edit_text(call.message.text + "\n\n✅ <b>ОДОБРЕНО</b>\nПодарок необходимо отправить вручную.")
    await call.answer("Одобрено")

@dp.callback_query(F.data.startswith("reject:"))
async def reject(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    req_id = int(call.data.split(":")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id, reward_id, status FROM requests WHERE id=?", (req_id,))
        row = await cur.fetchone()
        if not row or row[2] != "pending":
            await call.answer("Заявка уже обработана", show_alert=True)
            return
        user_id, reward_id, _ = row
        cur = await db.execute("SELECT cost FROM rewards WHERE id=?", (reward_id,))
        reward = await cur.fetchone()
        if reward:
            await db.execute("UPDATE users SET points=points+? WHERE user_id=?", (reward[0], user_id))
        await db.execute("UPDATE requests SET status='rejected' WHERE id=?", (req_id,))
        await db.commit()
    await bot.send_message(user_id, f"Заявка #{req_id} отклонена. Баллы возвращены.")
    await call.message.edit_text(call.message.text + "\n\n❌ <b>ОТКЛОНЕНО</b>\nБаллы возвращены участнику.")
    await call.answer("Отклонено")

@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def activity(message: Message):
    if not message.from_user or message.from_user.is_bot:
        return
    if GROUP_ID and str(message.chat.id) != GROUP_ID:
        return
    if not message.text or message.text.startswith("/"):
        return
    await upsert_user(message.from_user)
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT last_message, message_day, daily_count FROM users WHERE user_id=?",
                               (message.from_user.id,))
        row = await cur.fetchone()
        last_message, msg_day, count = row
        if msg_day != today:
            count = 0
        if count >= DAILY_LIMIT:
            return
        if last_message:
            try:
                last_dt = datetime.fromisoformat(last_message)
                if (now - last_dt).total_seconds() < MESSAGE_COOLDOWN:
                    return
            except ValueError:
                pass
        await db.execute("""
            UPDATE users SET points=points+?, last_message=?, message_day=?, daily_count=?
            WHERE user_id=?
        """, (POINTS_PER_MESSAGE, now.isoformat(), today, count + 1, message.from_user.id))
        await db.commit()

async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Set it in hosting environment variables.")
    await init_db()
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    logging.info("Starting @%s", me.username)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
