import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Токен бота от @BotFather
TOKEN = "8312628536:AAEQRKYK43dAiErDAt0YMcco4yBGtRXV5hE"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect("fate_contracts.db")
    cursor = conn.cursor()
    # Таблица контрактов
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

# --- КОМАНДЫ И ЛОГИКА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    text = (
        "🌅 **Добро пожаловать в бот реестра Fate!**\n\n"
        "📜 **Команды для управления контрактами:**\n"
        "• `/contract @username_слуги Имя_Слуги` — Предложить контракт\n"
        "• `/use_seal` — Использовать 1 Командное Заклинание\n"
        "• `/list` — Посмотреть список активных Мастеров и Слуг\n"
        "• `/break` — Расторгнуть контракт вручную"
    )
    await message.answer(text, parse_mode="Markdown")

# 1. ПРЕДЛОЖЕНИЕ КОНТРАКТА
@dp.message(Command("contract"))
async def make_contract(message: types.Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("⚠️ Формат команды: `/contract @username_слуги Имя_Слуги`\n*Пример:* `/contract @OutTrashreal Кухулин`", parse_mode="Markdown")
        return

    servant_tag = args[1].replace("@", "")
    servant_name = args[2]
    master_tag = message.from_user.username

    if not master_tag:
        await message.answer("❌ У вас должен быть установлен @username в Telegram!")
        return

    # Инлайн-кнопки для подтверждения Слугой
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🤝 Принять контракт (3 КЗ)", 
        callback_data=f"accept_{master_tag}_{servant_name}_{message.from_user.id}"
    )
    builder.button(
        text="❌ Отклонить", 
        callback_data="deny_contract"
    )

    await message.answer(
        f"⏳ Запрос отправлен! *@ {servant_tag}*, подтвердите заключение контракта с Мастером *@ {master_tag}* (Слуга: *{servant_name}*).",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# 2. ПОДТВЕРЖДЕНИЕ СЛУГОЙ
@dp.callback_query(F.data.startswith("accept_"))
async def accept_contract(call: types.CallbackQuery):
    _, master_tag, servant_name, master_id = call.data.split("_")
    servant_id = call.from_user.id
    servant_tag = call.from_user.username

    conn = sqlite3.connect("fate_contracts.db")
    cursor = conn.cursor()
    
    # Проверка на существование активного контракта
    cursor.execute("SELECT * FROM contracts WHERE master_id = ? OR servant_id = ?", (master_id, servant_id))
    if cursor.fetchone():
        await call.message.edit_text("❌ Один из участников уже находится в активном контракте!")
        conn.close()
        return

    # Сохраняем контракт с 3 КЗ
    cursor.execute(
        "INSERT INTO contracts (master_id, master_tag, servant_id, servant_tag, servant_name, seals) VALUES (?, ?, ?, ?, ?, 3)",
        (master_id, master_tag, servant_id, servant_tag, servant_name)
    )
    conn.commit()
    conn.close()

    await call.message.edit_text(
        f"⚔️ **Контракт успешно заключен!**\n\n"
        f"👤 **Мастер:** @{master_tag}\n"
        f"🗡 **Слуга:** {servant_name} (@{servant_tag})\n"
        f"🔴 **Командные Заклинания:** 3/3",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "deny_contract")
async def deny_contract(call: types.CallbackQuery):
    await call.message.edit_text("❌ Предложение контракта отклонено.")

# 3. ИСПОЛЬЗОВАНИЕ КОМАНДНОГО ЗАКЛИНАНИЯ
@dp.message(Command("use_seal"))
async def use_seal(message: types.Message):
    master_id = message.from_user.id

    conn = sqlite3.connect("fate_contracts.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, servant_name, servant_tag, seals FROM contracts WHERE master_id = ?", (master_id,))
    contract = cursor.fetchone()

    if not contract:
        await message.answer("❌ У вас нет активного контракта со Слугой!")
        conn.close()
        return

    contract_id, servant_name, servant_tag, seals = contract
    new_seals = seals - 1

    if new_seals > 0:
        # Уменьшаем количество КЗ
        cursor.execute("UPDATE contracts SET seals = ? WHERE id = ?", (new_seals, contract_id))
        conn.commit()
        seals_display = "🔴" * new_seals + "⚪" * (3 - new_seals)
        await message.answer(
            f"💥 **Мастер применил Командное Заклинание!**\n\n"
            f"Слуга: *{servant_name}* (@{servant_tag})\n"
            f"Осталось командных заклинаний: {seals_display} ({new_seals}/3)",
            parse_mode="Markdown"
        )
    else:
        # 0 КЗ -> Контракт расторгается и удаляется из базы
        cursor.execute("DELETE FROM contracts WHERE id = ?", (contract_id,))
        conn.commit()
        await message.answer(
            f"🔴 **Использовано ПОСЛЕДНЕЕ Командное Заклинание!**\n\n"
            f"💥 Запас магии исчерпан. Контракт между Мастером @{message.from_user.username} и Слугой *{servant_name}* (@{servant_tag}) **РАСТОРГНУТ**!\n"
            f"Пара удалена из общего списка.",
            parse_mode="Markdown"
        )

    conn.close()

# 4. СПИСОК ВСЕХ МАСТЕРОВ И СЛУГ
@dp.message(Command("list"))
async def list_contracts(message: types.Message):
    conn = sqlite3.connect("fate_contracts.db")
    cursor = conn.cursor()
    cursor.execute("SELECT master_tag, servant_name, servant_tag, seals FROM contracts")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await message.answer("🏖 **Активных контрактов пока нет.** Все свободны!")
        return

    text = "📜 **СПИСОК АКТИВНЫХ КОНТРАКТОВ:**\n\n"
    for idx, row in enumerate(rows, 1):
        m_tag, s_name, s_tag, seals = row
        seals_display = "🔴" * seals + "⚪" * (3 - seals)
        text += f"{idx}. 👤 *@ {m_tag}*  ↔️  🗡 *{s_name}* (@{s_tag})\n"
        text += f"   └ Заклинания: {seals_display} ({seals}/3)\n\n"

    await message.answer(text, parse_mode="Markdown")

# ЗАПУСК БОТА
async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
