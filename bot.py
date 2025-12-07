"""
ДЕМО-ВЕРСИЯ: Telegram-бот для раздач по выкупу на ВБ

Это пример реализации бота с базовым функционалом.
Для полной версии требуется доработка и тестирование.

TODO:
- Добавить валидацию скриншотов
- Реализовать систему уведомлений администраторам
- Добавить экспорт данных в Excel/CSV
- Улучшить обработку ошибок
- Добавить логирование действий
"""

import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from database import Database
from config import BOT_TOKEN, ADMIN_IDS, FOLDERS

# Создаём папки если их нет
for folder in FOLDERS.values():
    os.makedirs(folder, exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = Database()

# Состояния для FSM
class ParticipantStates(StatesGroup):
    waiting_for_screenshots = State()
    waiting_for_requisites = State()

class AdminStates(StatesGroup):
    adding_task = State()
    setting_limit = State()
    deleting_task = State()

# ============= ОСНОВНЫЕ КОМАНДЫ =============

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Команда /start"""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""
    
    await db.add_participant(user_id, username, full_name)
    
    participant = await db.get_participant(user_id)
    
    if participant and participant["status"] == "pending_payment":
        await message.answer(
            "✅ Вы уже участвуете в раздаче!\n\n"
            "Ваш статус: Ожидание оплаты\n"
            "Ваши реквизиты получены и находятся на проверке."
        )
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Участвовать в раздаче", callback_data="participate")]
    ])
    
    await message.answer(
        "👋 Добро пожаловать в бот для раздач по выкупу на ВБ!\n\n"
        "Нажмите кнопку ниже, чтобы принять участие в раздаче.",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "participate")
async def participate_handler(callback: CallbackQuery, state: FSMContext):
    """Обработка участия в раздаче"""
    user_id = callback.from_user.id
    
    # Проверяем, не участвует ли уже
    participant = await db.get_participant(user_id)
    if participant and participant["current_task_id"]:
        await callback.answer("Вы уже участвуете в раздаче!", show_alert=True)
        return
    
    # Ищем доступное задание
    tasks = await db.get_all_tasks(active_only=True)
    if not tasks:
        await callback.answer("На данный момент нет доступных заданий.", show_alert=True)
        return
    
    # Берем первое активное задание
    task = tasks[0]
    task_id = task["id"]
    
    # Проверяем лимит
    can_assign = await db.can_assign_task(task_id)
    if not can_assign:
        await callback.answer(
            "К сожалению, сегодня лимит раздач выполнен.",
            show_alert=True
        )
        await callback.message.answer("❌ К сожалению, сегодня лимит раздач выполнен.")
        return
    
    # Назначаем задание
    await db.assign_task(user_id, task_id)
    
    await callback.answer("✅ Вы успешно зарегистрированы!")
    
    # Отправляем задание
    await callback.message.answer(
        f"🎯 Ваше задание:\n\n{task['description']}\n\n"
        "📸 Пожалуйста, отправьте скриншоты выполнения задания.\n"
        "Вы можете отправить несколько скриншотов подряд."
    )
    
    await state.set_state(ParticipantStates.waiting_for_screenshots)

@dp.message(ParticipantStates.waiting_for_screenshots, F.photo)
async def handle_screenshot(message: Message, state: FSMContext):
    """Обработка скриншотов"""
    user_id = message.from_user.id
    participant = await db.get_participant(user_id)
    
    if not participant or not participant["current_task_id"]:
        await message.answer("Сначала зарегистрируйтесь на участие в раздаче.")
        return
    
    file_id = message.photo[-1].file_id
    file_info = await bot.get_file(file_id)
    
    # TODO: Добавить проверку качества/размера скриншота
    # TODO: Добавить валидацию что это действительно скриншот выполнения задания
    
    # Сохраняем файл
    file_path = os.path.join(
        FOLDERS["pending_review"],
        f"{user_id}_{participant['current_task_id']}_{file_info.file_id}.jpg"
    )
    await bot.download_file(file_info.file_path, file_path)
    
    # Добавляем в БД
    await db.add_screenshot(
        user_id,
        participant["current_task_id"],
        file_id,
        file_path
    )
    
    screenshots_count = await db.get_screenshots_count(user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Все скриншоты отправлены", callback_data="screenshots_done")]
    ])
    
    await message.answer(
        f"✅ Скриншот получен! (Всего: {screenshots_count})\n\n"
        "Если вы отправили все необходимые скриншоты, нажмите кнопку ниже.",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "screenshots_done")
async def screenshots_done_handler(callback: CallbackQuery, state: FSMContext):
    """Обработка завершения отправки скриншотов"""
    user_id = callback.from_user.id
    
    await db.move_to_review(user_id)
    await callback.answer("✅ Скриншоты приняты на проверку!")
    
    await callback.message.answer(
        "✅ Ваши скриншоты приняты и отправлены на проверку!\n\n"
        "После проверки вам нужно будет отправить реквизиты для получения кешбэка.\n\n"
        "💳 Пожалуйста, отправьте ваши реквизиты для кешбэка:"
    )
    
    await state.set_state(ParticipantStates.waiting_for_requisites)

@dp.message(ParticipantStates.waiting_for_requisites)
async def handle_requisites(message: Message, state: FSMContext):
    """Обработка реквизитов"""
    user_id = message.from_user.id
    requisites = message.text
    
    if not requisites or len(requisites.strip()) < 5:
        await message.answer("Пожалуйста, отправьте корректные реквизиты.")
        return
    
    # TODO: Добавить валидацию формата реквизитов (номер карты, счет и т.д.)
    # TODO: Добавить маскировку чувствительных данных при сохранении
    
    await db.add_requisites(user_id, requisites)
    await state.clear()
    
    # TODO: Отправить уведомление администратору о новом участнике на оплату
    
    await message.answer(
        "✅ Ваши реквизиты получены!\n\n"
        "Вы перемещены в папку 'На оплату'. "
        "Ожидайте обработки вашей заявки."
    )

# ============= АДМИН-ПАНЕЛЬ =============

def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    return user_id in ADMIN_IDS

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    """Админ-панель"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к админ-панели.")
        return
    
    stats = await db.get_statistics()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить задание", callback_data="admin_add_task")],
        [InlineKeyboardButton(text="📋 Список заданий", callback_data="admin_list_tasks")],
        [InlineKeyboardButton(text="👥 На проверку", callback_data="admin_pending_review")],
        [InlineKeyboardButton(text="💰 На оплату", callback_data="admin_pending_payment")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")]
    ])
    
    await message.answer(
        "🔧 <b>Админ-панель</b>\n\n"
        f"📊 Статистика:\n"
        f"• Всего участников: {stats['total_participants']}\n"
        f"• На проверку: {stats['pending_review']}\n"
        f"• На оплату: {stats['pending_payment']}\n"
        f"• Активных заданий: {stats['active_tasks']}",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "admin_add_task")
async def admin_add_task_handler(callback: CallbackQuery, state: FSMContext):
    """Добавление задания"""
    await callback.answer()
    await callback.message.answer(
        "📝 Введите описание нового задания:\n\n"
        "Пример: 'Выкупить товар X на ВБ, сделать скриншот заказа и отзыва'"
    )
    await state.set_state(AdminStates.adding_task)

@dp.message(AdminStates.adding_task)
async def process_add_task(message: Message, state: FSMContext):
    """Обработка добавления задания"""
    description = message.text
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Без лимита", callback_data=f"task_limit_0")],
        [InlineKeyboardButton(text="🔢 Установить лимит", callback_data=f"task_set_limit")]
    ])
    
    task_id = await db.add_task(description)
    await state.update_data(task_id=task_id)
    
    await message.answer(
        f"✅ Задание добавлено!\n\n"
        f"Описание: {description}\n\n"
        "Установите лимит участников:",
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("task_limit_"))
async def set_task_limit_handler(callback: CallbackQuery, state: FSMContext):
    """Установка лимита для задания"""
    limit = int(callback.data.split("_")[-1])
    data = await state.get_data()
    task_id = data.get("task_id")
    
    if task_id:
        await db.update_task_limit(task_id, limit)
        limit_text = "без ограничений" if limit == 0 else f"{limit} человек"
        await callback.answer(f"✅ Лимит установлен: {limit_text}")
        await callback.message.edit_text(
            f"✅ Задание создано с лимитом: {limit_text}"
        )
    else:
        await callback.answer("Ошибка при создании задания", show_alert=True)
    
    await state.clear()

@dp.callback_query(F.data == "task_set_limit")
async def task_set_limit_handler(callback: CallbackQuery, state: FSMContext):
    """Запрос лимита у админа"""
    await callback.answer()
    await callback.message.answer("🔢 Введите максимальное количество участников для этого задания (число):")
    await state.set_state(AdminStates.setting_limit)

@dp.message(AdminStates.setting_limit)
async def process_set_limit(message: Message, state: FSMContext):
    """Обработка установки лимита"""
    try:
        limit = int(message.text)
        if limit < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число (0 или больше).")
        return
    
    data = await state.get_data()
    task_id = data.get("task_id")
    
    if task_id:
        await db.update_task_limit(task_id, limit)
        limit_text = "без ограничений" if limit == 0 else f"{limit} человек"
        await message.answer(f"✅ Лимит установлен: {limit_text}")
    else:
        await message.answer("❌ Ошибка при установке лимита.")
    
    await state.clear()

@dp.callback_query(F.data == "admin_list_tasks")
async def admin_list_tasks_handler(callback: CallbackQuery):
    """Список заданий"""
    tasks = await db.get_all_tasks(active_only=False)
    
    if not tasks:
        await callback.answer("Нет заданий", show_alert=True)
        return
    
    keyboard_buttons = []
    for task in tasks:
        status = "✅" if task["is_active"] else "❌"
        limit = f"Лимит: {task['max_participants']}" if task["max_participants"] > 0 else "Без лимита"
        participants = f"Участников: {task['current_participants']}"
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{status} Задание #{task['id']}",
                callback_data=f"task_info_{task['id']}"
            )
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text(
        "📋 <b>Список заданий:</b>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("task_info_"))
async def task_info_handler(callback: CallbackQuery):
    """Информация о задании"""
    task_id = int(callback.data.split("_")[-1])
    tasks = await db.get_all_tasks(active_only=False)
    task = next((t for t in tasks if t["id"] == task_id), None)
    
    if not task:
        await callback.answer("Задание не найдено", show_alert=True)
        return
    
    limit_text = f"{task['max_participants']} человек" if task['max_participants'] > 0 else "Без ограничений"
    status_text = "Активно" if task["is_active"] else "Неактивно"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"task_delete_{task_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_list_tasks")]
    ])
    
    await callback.message.edit_text(
        f"📝 <b>Задание #{task_id}</b>\n\n"
        f"Описание: {task['description']}\n"
        f"Статус: {status_text}\n"
        f"Лимит: {limit_text}\n"
        f"Участников: {task['current_participants']}\n"
        f"Создано: {task['created_date'][:10]}",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("task_delete_"))
async def task_delete_handler(callback: CallbackQuery):
    """Удаление задания"""
    task_id = int(callback.data.split("_")[-1])
    await db.delete_task(task_id)
    await callback.answer("✅ Задание удалено!")
    await admin_list_tasks_handler(callback)

@dp.callback_query(F.data == "admin_pending_review")
async def admin_pending_review_handler(callback: CallbackQuery):
    """Участники на проверку"""
    participants = await db.get_participants_by_status("pending_review")
    
    if not participants:
        await callback.answer("Нет участников на проверку", show_alert=True)
        return
    
    text = "👥 <b>Участники на проверку:</b>\n\n"
    for p in participants[:20]:  # Показываем первые 20
        date = p["task_received_date"][:10] if p["task_received_date"] else "N/A"
        text += f"• {p['full_name']} (@{p['username']})\n"
        text += f"  Дата получения: {date}\n"
        text += f"  Скриншотов: {p['screenshots_count']}\n\n"
    
    # TODO: Добавить кнопки для просмотра скриншотов каждого участника
    # TODO: Добавить кнопку "Одобрить" / "Отклонить"
    # TODO: Добавить пагинацию если участников больше 20
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query(F.data == "admin_pending_payment")
async def admin_pending_payment_handler(callback: CallbackQuery):
    """Участники на оплату"""
    participants = await db.get_participants_by_status("pending_payment")
    
    if not participants:
        await callback.answer("Нет участников на оплату", show_alert=True)
        return
    
    text = "💰 <b>Участники на оплату:</b>\n\n"
    for p in participants[:20]:  # Показываем первые 20
        date = p["task_received_date"][:10] if p["task_received_date"] else "N/A"
        text += f"• {p['full_name']} (@{p['username']})\n"
        text += f"  Дата получения: {date}\n"
        text += f"  Реквизиты: {p['requisites'][:50]}...\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_handler(callback: CallbackQuery):
    """Статистика"""
    stats = await db.get_statistics()
    
    text = (
        "📊 <b>Статистика бота:</b>\n\n"
        f"👥 Всего участников: {stats['total_participants']}\n"
        f"🔍 На проверку: {stats['pending_review']}\n"
        f"💰 На оплату: {stats['pending_payment']}\n"
        f"📝 Активных заданий: {stats['active_tasks']}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query(F.data == "admin_back")
async def admin_back_handler(callback: CallbackQuery):
    """Возврат в главное меню админки"""
    await cmd_admin(callback.message)

# ============= ЗАПУСК =============

async def main():
    """Главная функция"""
    await db.init_db()
    print("✅ База данных инициализирована")
    print("🤖 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

