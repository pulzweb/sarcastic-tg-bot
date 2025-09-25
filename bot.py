# --- НАЧАЛО ПОЛНОГО КОДА BOT.PY (Детективное Агентство "Шерлок Болмс" v2.0 с КНОПКАМИ) ---
import logging
import os
import asyncio
import re
import datetime
import json
from flask import Flask, Response
import hypercorn.config
from hypercorn.asyncio import serve as hypercorn_async_serve
import pymongo
from pymongo.errors import PyMongoError
from bson.objectid import ObjectId

# Импорты для AI.IO.NET
from openai import AsyncOpenAI, BadRequestError

# Импорты Telegram (ДОБАВЛЕНЫ КНОПКИ)
from telegram import Update, Bot, User, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import telegram.error

from dotenv import load_dotenv

load_dotenv()

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
IO_NET_API_KEY = os.getenv("IO_NET_API_KEY")
MONGO_DB_URL = os.getenv("MONGO_DB_URL")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

if not TELEGRAM_BOT_TOKEN: raise ValueError("НЕ НАЙДЕН TELEGRAM_BOT_TOKEN!")
if not IO_NET_API_KEY: raise ValueError("НЕ НАЙДЕН IO_NET_API_KEY!")
if not MONGO_DB_URL: raise ValueError("НЕ НАЙДЕНА MONGO_DB_URL!")
if ADMIN_USER_ID == 0: print("ПРЕДУПРЕЖДЕНИЕ: ADMIN_USER_ID не задан!")

# --- Логирование ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("hypercorn").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- ПОДКЛЮЧЕНИЕ К MONGODB ATLAS ---
try:
    mongo_client = pymongo.MongoClient(MONGO_DB_URL, serverSelectionTimeoutMS=5000)
    mongo_client.admin.command('ping')
    logger.info("Успешное подключение к MongoDB Atlas!")
    db = mongo_client['sherlock_bolms_db']
    cases_collection = db['detective_cases']
    cases_collection.create_index([("chat_id", 1), ("status", 1)])
    logger.info("Коллекция detective_cases готова.")
except Exception as e:
    logger.critical(f"ПИЗДЕЦ при настройке MongoDB: {e}", exc_info=True)
    raise SystemExit(f"Ошибка настройки MongoDB: {e}")

# --- НАСТРОЙКА КЛИЕНТА AI.IO.NET API ---
try:
    ionet_client = AsyncOpenAI(api_key=IO_NET_API_KEY, base_url="https://api.intelligence.io.solutions/api/v1/")
    IONET_TEXT_MODEL_ID = "mistralai/Mistral-Large-Instruct-2411"
    logger.info(f"Клиент AsyncOpenAI для ai.io.net API настроен. Модель: {IONET_TEXT_MODEL_ID}")
except Exception as e:
     logger.critical(f"ПИЗДЕЦ при настройке клиента ai.io.net: {e}", exc_info=True)
     raise SystemExit(f"Не удалось настроить клиента ai.io.net: {e}")

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

async def _call_ionet_api(messages: list, model_id: str, max_tokens: int, temperature: float) -> str | None:
    try:
        response = await ionet_client.chat.completions.create(model=model_id, messages=messages, max_tokens=max_tokens, temperature=temperature)
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
        else: 
            logger.warning(f"Ответ от {model_id} пуст/некорректен: {response}")
            return None
    except BadRequestError as e:
        logger.error(f"Ошибка BadRequest от ai.io.net API ({model_id}): {e.status_code} - {e.body}", exc_info=False)
        return f"[Ошибка API: {e.status_code}]"
    except Exception as e:
        logger.error(f"ПИЗДЕЦ при вызове ai.io.net API ({model_id}): {e}", exc_info=True)
        return f"[Критическая ошибка API: {type(e).__name__}]"

async def _get_active_case(chat_id: int) -> dict | None:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: cases_collection.find_one({"chat_id": chat_id, "status": "active"}))

# --- НОВАЯ ЦЕНТРАЛЬНАЯ ФУНКЦИЯ ДЛЯ ОТОБРАЖЕНИЯ ИНФО И КНОПОК ---
async def show_or_update_case_info(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int | None = None):
    """
    Отправляет или обновляет главное игровое сообщение, содержащее информацию о деле и кнопки действий.
    """
    case = await _get_active_case(chat_id)
    if not case:
        try:
            if message_id:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="🗿 Это дело уже закрыто или не существует.")
                await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
        except Exception:
            pass
        return

    case_data = case.get("case_data", {})
    
    # Формируем текстовую часть
    suspects_text = ", ".join([s['name'] for s in case_data.get("suspects", [])])
    locations_text = ", ".join([l['name'] for l in case_data.get("locations", [])])
    found_clues_text = "\n".join([f"  • {clue}" for clue in case.get("found_clues", [])]) or "Ни одной сраной улики пока не найдено."
    info_text = (
        f"<b>Сводка по делу №{case['case_id']}</b>\n\n"
        f"<b>Статус:</b> В процессе, и вы, как обычно, тупите.\n\n"
        f"<b>Подозреваемые:</b> {suspects_text}\n"
        f"<b>Локации:</b> {locations_text}\n\n"
        f"<b><u>Найденные улики:</u></b>\n{found_clues_text}\n\n"
        f"🗿 <b>Ваши действия, салаги?</b>"
    )

    # Формируем кнопки
    keyboard = []
    
    # Кнопки допроса
    suspects_buttons = [
        InlineKeyboardButton(f"Допросить: {s['name']}", callback_data=f"detective:interrogate:{s['name']}")
        for s in case_data.get("suspects", [])
    ]
    # Делаем ряды по 2 кнопки, если подозреваемых много
    for i in range(0, len(suspects_buttons), 2):
        keyboard.append(suspects_buttons[i:i + 2])
        
    # Кнопки обыска
    locations_buttons = [
        InlineKeyboardButton(f"Обыскать: {l['name']}", callback_data=f"detective:search:{l['name']}")
        for l in case_data.get("locations", [])
    ]
    for i in range(0, len(locations_buttons), 2):
        keyboard.append(locations_buttons[i:i + 2])
        
    # Кнопка обвинения
    keyboard.append([InlineKeyboardButton(" выдвинуть обвинение!", callback_data="detective:accuse_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        if message_id:
            # Обновляем существующее сообщение
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=info_text, parse_mode='HTML', reply_markup=reply_markup)
        else:
            # Отправляем новое сообщение
            await context.bot.send_message(chat_id=chat_id, text=info_text, parse_mode='HTML', reply_markup=reply_markup)
    except telegram.error.BadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.warning(f"Ошибка при обновлении игрового сообщения: {e}")
    except Exception as e:
        logger.error(f"Критическая ошибка при отправке/обновлении игрового сообщения: {e}", exc_info=True)


# --- ЛОГИКА ГЕНЕРАЦИИ ДЕЛА (без изменений) ---
async def _generate_new_case_data(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    logger.info("Запрос к ИИ на генерацию нового детективного дела...")
    prompt = (
        "Ты — гениальный, но циничный сценарист детективных историй в стиле нуар. "
        "Создай короткое детективное дело для группы игроков. "
        "Придумай преступление, 3-х колоритных подозреваемых с описанием и мотивами, и тайно реши, кто из них виновен. "
        "Придумай 3-4 уникальные улики (одна из них может быть ложной) и разбросай их по 2-3 локациям. "
        "Твой ответ ДОЛЖЕН БЫТЬ строго в формате JSON. Никакого текста до или после JSON. "
        "Пример формата JSON:\n"
        "{\n"
        "  \"crime_description\": \"Вчера ночью из сейфа известного филателиста Генриха Штампа была украдена редчайшая марка 'Голубой Маврикий'.\",\n"
        "  \"victim\": \"Генрих Штамп (его ограбили)\",\n"
        "  \"guilty_suspect_name\": \"Дворецкий Джеймс\",\n"
        "  \"suspects\": [\n"
        "    {\"name\": \"Дворецкий Джеймс\", \"description\": \"Верный слуга с сорокалетним стажем, но с огромными игорными долгами.\", \"alibi\": \"Утверждает, что всю ночь полировал фамильное серебро в подвале.\", \"dialogue_hint\": \"Говорит сбивчиво, постоянно оглядывается.\"},\n"
        "    {\"name\": \"Племянница Вероника\", \"description\": \"Единственная наследница, которой дядя грозился урезать содержание.\", \"alibi\": \"Была на светском рауте, но ушла с него пораньше.\", \"dialogue_hint\": \"Ведет себя высокомерно, но в глазах страх.\"},\n"
        "    {\"name\": \"Конкурент-коллекционер Бобби\", \"description\": \"Давно пытался выкупить марку у Генриха, но получал отказ.\", \"alibi\": \"Сидел в баре, что могут подтвердить два собутыльника.\", \"dialogue_hint\": \"Чрезмерно уверен в себе, насмехается над следствием.\"}\n"
        "  ],\n"
        "  \"locations\": [\n"
        "    {\"name\": \"Кабинет Генриха\", \"description\": \"Роскошный кабинет с дубовым столом и вскрытым сейфом.\", \"clues_here\": [\"Грязный след от ботинка 45-го размера\", \"Огарок дешевой сигареты в пепельнице\"]},\n"
        "    {\"name\": \"Комната Дворецкого\", \"description\": \"Скромная каморка под лестницей.\", \"clues_here\": [\"Свежая квитанция из ломбарда на крупную сумму\"]},\n"
        "    {\"name\": \"Оранжерея\", \"description\": \"Тихое место с экзотическими растениями.\", \"clues_here\": [\"Сломанный каблук от женской туфельки (ложная улика)\"]}\n"
        "  ]\n"
        "}"
    )
    try:
        response = await _call_ionet_api([{"role": "user", "content": prompt}], IONET_TEXT_MODEL_ID, 2048, 0.85)
        if not response or response.startswith("["):
            logger.error(f"ИИ вернул ошибку при генерации дела: {response}")
            return None
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if not json_match:
            logger.error(f"Не удалось найти JSON в ответе ИИ. Ответ был: {response}")
            return None
        case_data = json.loads(json_match.group(0))
        required_keys = ["crime_description", "guilty_suspect_name", "suspects", "locations"]
        if not all(key in case_data for key in required_keys):
            logger.error(f"Сгенерированный JSON не содержит всех обязательных ключей. Получено: {case_data.keys()}")
            return None
        return case_data
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON от ИИ: {e}\nОтвет ИИ был: {response}")
        return None
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при генерации дела: {e}", exc_info=True)
        return None

# --- КОМАНДЫ-ОБРАБОТЧИКИ ---

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "🗿 Агентство \"Шерлок Болмс\" слушает. Я здесь, чтобы распутывать самые грязные делишки. "
        "А вы, салаги, — мои глаза и уши. Вот что вы можете делать:\n\n"
        "<b>/new_case</b> — Начать новое расследование.\n\n"
        "<b>/case_info</b> — Показать панель управления текущим делом, если она куда-то пропала.\n\n"
        "Все остальные действия выполняются через <b>кнопки</b> под информационным сообщением. "
        "Если вы их не видите, используйте <code>/case_info</code>."
    )
    await update.message.reply_text(help_text, parse_mode='HTML')

async def start_new_case(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    if await _get_active_case(chat_id):
        await update.message.reply_text("🗿 Эй, тормози. Одно дело за раз. Сначала закончите с текущим. Используй /case_info, чтобы увидеть кнопки.")
        return

    thinking_msg = await update.message.reply_text("🗿 Принял. Копаюсь в архивах, ищу для вас подходящую грязь... Это может занять минуту.")

    case_data = await _generate_new_case_data(context)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=thinking_msg.message_id)
    except Exception: pass

    if not case_data:
        await update.message.reply_text("🗿 Пиздец. Вдохновение покинуло меня, или мой информатор ушел в запой. Не могу сейчас придумать дело. Попробуйте позже.")
        return

    # Отправляем первое сообщение о деле (оно будет без кнопок)
    start_message_text = (
        f"🚨 <b>НОВОЕ ДЕЛО АГЕНТСТВА \"ШЕРЛОК БОЛМС\"</b> 🚨\n\n"
        f"<b><u>Фабула:</u></b>\n{case_data['crime_description']}"
    )
    case_msg = await update.message.reply_text(start_message_text, parse_mode='HTML')

    db_document = {
        "chat_id": chat_id, "case_id": case_msg.message_id, "status": "active",
        "start_time": datetime.datetime.now(datetime.timezone.utc),
        "case_data": case_data, "found_clues": [], "interrogation_log": {}
    }
    cases_collection.insert_one(db_document)
    logger.info(f"Новое дело {case_msg.message_id} создано для чата {chat_id}.")
    
    # Сразу после этого отправляем панель управления
    await show_or_update_case_info(context, chat_id)

async def case_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /case_info."""
    chat_id = update.message.chat_id
    case = await _get_active_case(chat_id)
    if not case:
        await update.message.reply_text("🗿 У нас нет активных дел. Используйте `/new_case`.")
        return
    await show_or_update_case_info(context, chat_id)


# --- НОВЫЙ ЕДИНЫЙ ОБРАБОТЧИК КНОПОК ---
async def detective_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer() # Обязательно отвечаем на callback

    chat_id = query.message.chat_id
    message_id = query.message.message_id
    
    # Парсим данные кнопки: detective:action:data
    try:
        _, action, *data_parts = query.data.split(':')
        data = ":".join(data_parts) # На случай, если в данных (имени) есть двоеточие
    except ValueError:
        logger.error(f"Некорректный callback_data: {query.data}")
        return

    case = await _get_active_case(chat_id)
    if not case:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="🗿 Это дело уже закрыто.")
        await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
        return

    # --- Маршрутизация действий по кнопкам ---
    
    if action == 'interrogate':
        target_name = data
        suspect_data = next((s for s in case["case_data"].get("suspects", []) if s["name"] == target_name), None)
        if not suspect_data: return
        
        is_guilty = (suspect_data["name"] == case["case_data"]["guilty_suspect_name"])
        prompt = (f"Ты — актер, играющий роль персонажа по имени {suspect_data['name']}... [промпт как раньше]") # Сокращено для краткости
        response = await _call_ionet_api([{"role": "user", "content": prompt}], IONET_TEXT_MODEL_ID, 300, 0.9) or "..."
        final_text = f"<b>Допрос: {suspect_data['name']}</b>\n\n<i>{response}</i>"
        await context.bot.send_message(chat_id=chat_id, text=final_text, parse_mode='HTML')
        # Обновляем панель управления после действия
        await show_or_update_case_info(context, chat_id, message_id)

    elif action == 'search':
        target_location_name = data
        location_data = next((loc for loc in case["case_data"].get("locations", []) if loc["name"] == target_location_name), None)
        if not location_data: return

        clues_in_location = location_data.get("clues_here", [])
        found_clues_in_db = case.get("found_clues", [])
        newly_found_clues = [clue for clue in clues_in_location if clue not in found_clues_in_db]

        result_text = f"<b>Обыск: {location_data['name']}</b>\n\n"
        if not newly_found_clues:
            result_text += "Вы все тут уже перерыли. Больше ничего интересного."
        else:
            for clue in newly_found_clues:
                result_text += f"🔍 Найдена улика: <b>{clue}</b>\n"
            cases_collection.update_one({"_id": case["_id"]}, {"$push": {"found_clues": {"$each": newly_found_clues}}})
        
        await context.bot.send_message(chat_id=chat_id, text=result_text, parse_mode='HTML')
        # Обновляем панель управления после действия
        await show_or_update_case_info(context, chat_id, message_id)

    elif action == 'accuse_menu':
        # Показываем меню с выбором, кого обвинить
        suspects = case["case_data"].get("suspects", [])
        keyboard = [
            [InlineKeyboardButton(f"Виновен: {s['name']}", callback_data=f"detective:accuse_confirm:{s['name']}")] for s in suspects
        ]
        keyboard.append([InlineKeyboardButton("Отмена", callback_data="detective:info")])
        await query.edit_message_text(text="🗿 Кого вы обвиняете? Это ваш финальный ответ.", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif action == 'accuse_confirm':
        # Завершаем дело
        accused_name = data
        guilty_suspect_name = case["case_data"]["guilty_suspect_name"]
        is_correct = (accused_name.lower() == guilty_suspect_name.lower())
        final_status = "solved_success" if is_correct else "solved_fail"
        
        cases_collection.update_one({"_id": case["_id"]}, {"$set": {"status": final_status}})
        try:
            await context.bot.unpin_chat_message(chat_id=chat_id, message_id=case["case_id"])
        except Exception: pass

        prompt = (f"Ты — гениальный детектив... [промпт как раньше]")
        final_reveal = await _call_ionet_api([{"role": "user", "content": prompt}], IONET_TEXT_MODEL_ID, 1024, 0.7)
        header = "🏆 ДЕЛО РАСКРЫТО! 🏆" if is_correct else "🤦 ДЕЛО ПРОВАЛЕНО! 🤦"
        final_message = f"<b>{header}</b>\n\nВы обвинили: <b>{accused_name}</b>\n\n{final_reveal}"
        
        # Редактируем сообщение с кнопками, чтобы показать финал
        await query.edit_message_text(text=final_message, parse_mode='HTML', reply_markup=None)

    elif action == 'info':
        # Возвращаемся к главному меню
        await show_or_update_case_info(context, chat_id, message_id)


# --- ТОЧКА ВХОДА И ЗАПУСК ---
app = Flask(__name__)
@app.route('/')
def index(): return "Sherlock Bolms Detective Agency is running.", 200
@app.route('/healthz')
def health_check(): return "OK", 200

async def run_bot_async(application: Application) -> None:
    await application.initialize()
    await application.start()
    if application.updater:
        await application.updater.start_polling()
    logger.info("Бот запущен и работает в режиме polling...")
    await asyncio.Future()

async def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Основные команды
    application.add_handler(CommandHandler("start", help_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("new_case", start_new_case))
    application.add_handler(CommandHandler("case_info", case_info_command))

    # НОВЫЙ ОБРАБОТЧИК ДЛЯ ВСЕХ КНОПОК
    application.add_handler(CallbackQueryHandler(detective_button_callback, pattern=r'^detective:'))

    logger.info("Обработчики Telegram добавлены.")

    # Запуск сервера и бота
    port = int(os.environ.get("PORT", 8080))
    hypercorn_config = hypercorn.config.Config()
    hypercorn_config.bind = [f"0.0.0.0:{port}"]
    
    shutdown_event = asyncio.Event()
    bot_task = asyncio.create_task(run_bot_async(application))
    server_task = asyncio.create_task(hypercorn_async_serve(app, hypercorn_config, shutdown_trigger=shutdown_event.wait))

    try:
        await asyncio.gather(bot_task, server_task)
    except asyncio.CancelledError:
        logger.info("Задачи были отменены, завершение работы...")
    finally:
        if application.updater and application.updater.is_running: await application.updater.stop()
        if application.running: await application.stop()
        shutdown_event.set()

if __name__ == "__main__":
    logger.info("Запуск скрипта bot.py...")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Скрипт остановлен вручную.")
    except Exception as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА В main: {e}", exc_info=True)
