import asyncio
import sqlite3
import base64
import html
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN = os.getenv("8312628536:AAEQRKYK43dAiErDAt0YMcco4yBGtRXV5hE")  # Токен будет бережно храниться в настройках

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect("fate_contracts.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_id INTEGER,
            master_tag TEXT,
            servant_id INTEGER,
            servant_tag TEXT,
            servant_name TEXT,
            seals INTEGER DEFAULT 3
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- КОМАНДЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    text = (
        "🌅 <b>Добро пожаловать в бот реестра Fate!</b>\n\n"
        "📜 <b>Команды для управления контрактами:</b>\n"
        "• <code>/contract @username_слуги Имя_Слуги</code> — Предложить контракт\n"
        "• <code>/use_seal</code> — Использовать 1 Командное Заклинание\n"
        "• <code>/list</code> — Посмотреть список активных Мастеров и Слуг"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("contract"))
async def make_contract(message: types.Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("⚠️ Формат: <code>/contract @username_слуги Имя_Слуги</code>", parse_mode="HTML")
        return

    servant_tag = args[1].replace("@", "")
    servant_name = args[2]
    master_tag = message.from_user.username

    if not master_tag:
        await message.answer("❌ У вас должен быть установлен @username в Telegram!")
        return

    data_str = f"{master_tag}|{servant_name}|{message.from_user.id}"
    encoded_data = base64.b64encode(data_str.encode('utf-8')).decode('utf-8')

    builder = InlineKeyboardBuilder()
    builder.button(text="🤝 Принять контракт (3 КЗ)", callback_data=f"acc:{encoded_data}")
    builder.button(text="❌ Отклонить", callback_data="deny_contract")

    m_tag_esc = html.escape(master_tag)
    s_tag_esc = html.escape(servant_tag)
    s_name_esc = html.escape(servant_name)

    await message.answer(
        f"⏳ Запрос отправлен! @{s_tag_esc}, подтвердите контракт с Мастером @{m_tag_esc} (Слуга: <b>{s_name_esc}</b>).",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("acc:"))
async def accept_contract(call: types.CallbackQuery):
    try:
        encoded_data = call.data.split("acc:")[1]
        decoded_str = base64.b64decode(encoded_data.encode('utf-8')).decode('utf-8')
        master_tag, servant_name, master_id_str = decoded_str.split("|")
        master_id = int(master_id_str)
    except Exception:
        await call.answer("⚠️ Ошибка обработки данных контракта.", show_alert=True)
        return

    servant_id = call.from_user.id
    servant_tag = call.from_user.username or "без_юзернейма"

    conn = sqlite3.connect("fate_contracts.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contracts WHERE master_id = ? OR servant_id = ?", (master_id, servant_id))
    if cursor.fetchone():
        await call.answer("❌ Один из участников уже находится в контракте!", show_alert=True)
        conn.close()
        return

    cursor.execute(
        "INSERT INTO contracts (master_id, master_tag, servant_id, servant_tag, servant_name, seals) VALUES (?, ?, ?, ?, ?, 3)",
        (master_id, master_tag, servant_id, servant_tag, servant_name)
    )
    conn.commit()
    conn.close()

    m_tag_esc = html.escape(master_tag)
    s_tag_esc = html.escape(servant_tag)
    s_name_esc = html.escape(servant_name)

    await call.message.edit_text(
        f"⚔️ <b>Контракт успешно заключен!</b>\n\n"
        f"👤 <b>Мастер:</b> @{m_tag_esc}\n"
        f"🗡 <b>Слуга:</b> {s_name_esc} (@{s_tag_esc})\n"
        f"🔴 <b>Командные Заклинания:</b> 3/3",
        parse_mode="HTML"
    )
    await call.answer("Контракт принят!")

@dp.callback_query(F.data == "deny_contract")
async def deny_contract(call: types.CallbackQuery):
    await call.message.edit_text("❌ Предложение контракта отклонено.")

@dp.message(Command("use_seal"))
async def use_seal(message: types.Message):
    master_id = message.from_user.id

    conn = sqlite3.connect("fate_contracts.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, servant_name, servant_tag, seals FROM contracts WHERE master_id = ?", (master_id,))
    contract = cursor.fetchone()

    if not contract:
        await message.answer("❌ У вас нет активного контракта!")
        conn.close()
        return

    contract_id, servant_name, servant_tag, seals = contract
    new_seals = seals - 1

    s_name_esc = html.escape(servant_name)
    s_tag_esc = html.escape(servant_tag)

    if new_seals > 0:
        cursor.execute("UPDATE contracts SET seals = ? WHERE id = ?", (new_seals, contract_id))
        conn.commit()
        seals_display = "🔴" * new_seals + "⚪" * (3 - new_seals)
        await message.answer(
            f"💥 <b>Мастер применил Командное Заклинание!</b>\n\n"
            f"Слуга: <b>{s_name_esc}</b> (@{s_tag_esc})\n"
            f"Осталось командных заклинаний: {seals_display} ({new_seals}/3)",
            parse_mode="HTML"
        )
    else:
        cursor.execute("DELETE FROM contracts WHERE id = ?", (contract_id,))
        conn.commit()
        m_tag_esc = html.escape(message.from_user.username or "Мастер")
        await message.answer(
            f"🔴 <b>Использовано ПОСЛЕДНЕЕ Командное Заклинание!</b>\n\n"
            f"💥 Контракт между Мастером @{m_tag_esc} и Слугой <b>{s_name_esc}</b> (@{s_tag_esc}) <b>РАСТОРГНУТ</b>!\n"
            f"Пара удалена из списка.",
            parse_mode="HTML"
        )

    conn.close()

@dp.message(Command("list"))
async def list_contracts(message: types.Message):
    conn = sqlite3.connect("fate_contracts.db")
    cursor = conn.cursor()
    cursor.execute("SELECT master_tag, servant_name, servant_tag, seals FROM contracts")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await message.answer("🏖 <b>Активных контрактов пока нет.</b>", parse_mode="HTML")
        return

    text = "📜 <b>СПИСОК АКТИВНЫХ КОНТРАКТОВ:</b>\n\n"
    for idx, row in enumerate(rows, 1):
        m_tag, s_name, s_tag, seals = row
        m_tag_esc = html.escape(str(m_tag))
        s_name_esc = html.escape(str(s_name))
        s_tag_esc = html.escape(str(s_tag))
        seals_display = "🔴" * seals + "⚪" * (3 - seals)
        text += f"{idx}. 👤 @{m_tag_esc} ↔️ 🗡 <b>{s_name_esc}</b> (@{s_tag_esc})\n"
        text += f"   └ Заклинания: {seals_display} ({seals}/3)\n\n"

    await message.answer(text, parse_mode="HTML")

async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())