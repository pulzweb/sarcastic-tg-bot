# --- НАЧАЛО ПОЛНОГО КОДА BOT.PY (Детективное Агентство "Шерлок Болмс") ---
import logging
import os
import asyncio
import re
import pytz
import datetime
import json
import random
from flask import Flask, Response
import hypercorn.config
from hypercorn.asyncio import serve as hypercorn_async_serve
import pymongo
from pymongo.errors import PyMongoError
from bson.objectid import ObjectId

# Импорты для AI.IO.NET (OpenAI библиотека)
from openai import AsyncOpenAI, BadRequestError

# Импорты Telegram
from telegram import Update, Bot, User
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import telegram.error

from dotenv import load_dotenv

# Загружаем секреты (.env для локального запуска)
load_dotenv()

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
IO_NET_API_KEY = os.getenv("IO_NET_API_KEY")
MONGO_DB_URL = os.getenv("MONGO_DB_URL")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

# Проверка ключей
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
    # Новая коллекция для хранения дел
    cases_collection = db['detective_cases']
    cases_collection.create_index([("chat_id", 1), ("status", 1)]) # Индекс для поиска активных дел в чате
    logger.info("Коллекция detective_cases готова.")
    # Старые коллекции для админских функций
    chat_activity_collection = db['chat_activity']
    bot_status_collection = db['bot_status']
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
    """Вызывает текстовый API ai.io.net и возвращает ответ или текст ошибки."""
    try:
        response = await ionet_client.chat.completions.create(
            model=model_id, messages=messages, max_tokens=max_tokens, temperature=temperature
        )
        if response.choices and response.choices.message and response.choices.message.content:
            return response.choices.message.content.strip()
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
    """Находит и возвращает активное дело для указанного чата из MongoDB."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: cases_collection.find_one({"chat_id": chat_id, "status": "active"})
    )

# --- ЛОГИКА ГЕНЕРАЦИИ ДЕЛА ---

async def _generate_new_case_data(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    """Генерирует новое дело с помощью ИИ и парсит его в словарь."""
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
        
        # Ищем JSON в ответе, т.к. ИИ иногда добавляет лишний текст
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if not json_match:
            logger.error("Не удалось найти JSON в ответе ИИ.")
            return None
        
        case_data = json.loads(json_match.group(0))
        
        # Валидация данных (базовая)
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
    """Отправляет справку по командам бота-детектива."""
    help_text = (
        "🗿 Агентство \"Шерлок Болмс\" слушает. Я здесь, чтобы распутывать самые грязные делишки. "
        "А вы, салаги, — мои глаза и уши. Вот что вы можете делать:\n\n"
        "<b>/new_case</b> или '<i>Бот, новое дело</i>'\n"
        "— Начать новое расследование. Только одно дело на чат.\n\n"
        "<b>/case_info</b> или '<i>Бот, что по делу?</i>'\n"
        "— Показать текущий статус расследования: подозреваемых, локации и найденные улики.\n\n"
        "<b>/interrogate [Имя]</b> или '<i>Бот, допроси [Имя]</i>'\n"
        "— Допросить одного из подозреваемых. Например: <code>/interrogate Дворецкий Джеймс</code>\n\n"
        "<b>/search [Локация]</b> или '<i>Бот, обыщи [Локация]</i>'\n"
        "— Обыскать доступную локацию в поисках улик. Например: <code>/search Кабинет</code>\n\n"
        "<b>/accuse [Имя]</b> или '<i>Бот, виновен [Имя]</i>'\n"
        "— Выдвинуть окончательное обвинение. Используйте, когда уверены в своей версии.\n\n"
        "Удачи, Ватсоны-недоучки. Она вам понадобится."
    )
    await update.message.reply_text(help_text, parse_mode='HTML')

async def start_new_case(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Начинает новое детективное расследование в чате."""
    chat_id = update.message.chat_id

    # Проверяем, нет ли уже активного дела
    if await _get_active_case(chat_id):
        await update.message.reply_text("🗿 Эй, тормози. Одно дело за раз. Сначала закончите с текущим, потом будете лезть в новые неприятности.")
        return

    thinking_msg = await update.message.reply_text("🗿 Принял. Копаюсь в архивах, ищу для вас подходящую грязь... Это может занять минуту.")

    # Генерируем данные для дела
    case_data = await _generate_new_case_data(context)

    await context.bot.delete_message(chat_id=chat_id, message_id=thinking_msg.message_id)

    if not case_data:
        await update.message.reply_text("🗿 Пиздец. Вдохновение покинуло меня, или мой информатор ушел в запой. Не могу сейчас придумать дело. Попробуйте позже.")
        return

    # Формируем стартовое сообщение
    suspects_text = []
    for suspect in case_data.get("suspects", []):
        suspects_text.append(f"  • <b>{suspect['name']}</b>: {suspect['description']}")
    
    locations_text = ", ".join([loc['name'] for loc in case_data.get("locations", [])])

    start_message_text = (
        f"🚨 <b>НОВОЕ ДЕЛО АГЕНТСТВА \"ШЕРЛОК БОЛМС\"</b> 🚨\n\n"
        f"<b><u>Фабула:</u></b>\n{case_data['crime_description']}\n\n"
        f"<b><u>Подозреваемые:</u></b>\n" + "\n".join(suspects_text) + "\n\n"
        f"<b><u>Доступные для обыска локации:</u></b>\n{locations_text}\n\n"
        f"🗿 Итак, салаги, время работать мозгами. Используйте <code>/interrogate</code> и <code>/search</code>. Когда решите, что докопались до правды, используйте <code>/accuse</code>."
    )

    case_msg = await update.message.reply_text(start_message_text, parse_mode='HTML')

    # Сохраняем дело в БД
    db_document = {
        "chat_id": chat_id,
        "case_id": case_msg.message_id,
        "status": "active",
        "start_time": datetime.datetime.now(datetime.timezone.utc),
        "case_data": case_data,
        "found_clues": [],
        "interrogation_log": {}
    }
    cases_collection.insert_one(db_document)
    logger.info(f"Новое дело {case_msg.message_id} создано для чата {chat_id}.")
    try:
        await context.bot.pin_chat_message(chat_id=chat_id, message_id=case_msg.message_id)
    except Exception as e:
        logger.warning(f"Не удалось закрепить сообщение о деле: {e}")

async def show_case_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает текущий статус расследования."""
    chat_id = update.message.chat_id
    case = await _get_active_case(chat_id)

    if not case:
        await update.message.reply_text("🗿 У нас нет активных дел. Либо вы все раскрыли, либо вы бездельники. Используйте `/new_case`.")
        return

    case_data = case.get("case_data", {})
    suspects_text = ", ".join([s['name'] for s in case_data.get("suspects", [])])
    locations_text = ", ".join([l['name'] for l in case_data.get("locations", [])])
    found_clues_text = "\n".join([f"  • {clue}" for clue in case.get("found_clues", [])]) or "Ни одной сраной улики пока не найдено."

    info_text = (
        f"<b>Сводка по делу №{case['case_id']}</b>\n\n"
        f"<b>Статус:</b> В процессе, и вы, как обычно, тупите.\n\n"
        f"<b>Подозреваемые:</b> {suspects_text}\n"
        f"<b>Локации:</b> {locations_text}\n\n"
        f"<b><u>Найденные улики:</u></b>\n{found_clues_text}"
    )
    await update.message.reply_text(info_text, parse_mode='HTML')

async def interrogate_suspect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает допрос подозреваемого."""
    chat_id = update.message.chat_id
    case = await _get_active_case(chat_id)
    if not case:
        await update.message.reply_text("🗿 Кого допрашивать? Дела-то нет.")
        return

    # Извлекаем имя из команды
    command_text = update.message.text
    match = re.search(r'(?:/interrogate|допроси)\s+(.+)', command_text, re.IGNORECASE)
    if not match:
        await update.message.reply_text("🗿 Укажи, кого допрашивать. Например: `/interrogate Дворецкий Джеймс`.")
        return
    target_name = match.group(1).strip()

    # Ищем подозреваемого в деле
    suspect_data = None
    for s in case["case_data"].get("suspects", []):
        if s["name"].lower() == target_name.lower():
            suspect_data = s
            break
    
    if not suspect_data:
        await update.message.reply_text(f"🗿 Я не знаю никакого '{target_name}'. Проверь список подозреваемых в `/case_info`.")
        return
        
    is_guilty = (suspect_data["name"] == case["case_data"]["guilty_suspect_name"])
    
    thinking_msg = await update.message.reply_text(f"🗿 Вызываю {suspect_data['name']} на допрос. Ща он вам напоет...")

    prompt = (
        f"Ты — актер, играющий роль персонажа по имени {suspect_data['name']} в детективной игре. "
        f"Твое описание: {suspect_data['description']}. Твое алиби: {suspect_data['alibi']}. "
        f"Подсказка к диалогу: {suspect_data.get('dialogue_hint', 'Веди себя естественно')}. "
        f"На самом деле ты {'ВИНОВЕН' if is_guilty else 'НЕ ВИНОВЕН'}. "
        f"Группа сыщиков только что начала допрос. Выдай их первую реакцию или реплику от лица своего персонажа. "
        f"Говори в 2-4 предложениях. Будь убедительным. Если виновен — лги и изворачивайся. Если нет — можешь быть честным, но немного напуганным или раздраженным."
    )

    response = await _call_ionet_api([{"role": "user", "content": prompt}], IONET_TEXT_MODEL_ID, 300, 0.9)
    await context.bot.delete_message(chat_id=chat_id, message_id=thinking_msg.message_id)

    if not response or response.startswith("["):
        response = f"🗿 {suspect_data['name']} молчит. Видимо, впал в ступор от вашей тупости."

    final_text = f"<b>Допрос: {suspect_data['name']}</b>\n\n<i>{response}</i>"
    await update.message.reply_text(final_text, parse_mode='HTML')

async def search_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает обыск локации."""
    chat_id = update.message.chat_id
    case = await _get_active_case(chat_id)
    if not case:
        await update.message.reply_text("🗿 Нечего обыскивать, дела нет.")
        return

    command_text = update.message.text
    match = re.search(r'(?:/search|обыщи)\s+(.+)', command_text, re.IGNORECASE)
    if not match:
        await update.message.reply_text("🗿 Укажи, что обыскивать. Например: `/search Кабинет`.")
        return
    target_location_name = match.group(1).strip()

    location_data = None
    for loc in case["case_data"].get("locations", []):
        if loc["name"].lower() == target_location_name.lower():
            location_data = loc
            break

    if not location_data:
        await update.message.reply_text(f"🗿 Локации '{target_location_name}' нет в этом деле. Смотри `/case_info`.")
        return

    clues_in_location = location_data.get("clues_here", [])
    found_clues_in_db = case.get("found_clues", [])
    newly_found_clues = [clue for clue in clues_in_location if clue not in found_clues_in_db]

    result_text = f"<b>Обыск: {location_data['name']}</b>\n\n{location_data['description']}\n\n"
    if not newly_found_clues:
        result_text += "Вы все тут уже перерыли. Больше ничего интересного."
    else:
        for clue in newly_found_clues:
            result_text += f"🔍 Найдена улика: <b>{clue}</b>\n"
        # Обновляем список найденных улик в БД
        cases_collection.update_one(
            {"_id": case["_id"]},
            {"$push": {"found_clues": {"$each": newly_found_clues}}}
        )
        logger.info(f"В чате {chat_id} найдены улики: {newly_found_clues}")

    await update.message.reply_text(result_text, parse_mode='HTML')

async def make_accusation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выдвигает обвинение и завершает дело."""
    chat_id = update.message.chat_id
    case = await _get_active_case(chat_id)
    if not case:
        await update.message.reply_text("🗿 Некого обвинять, дела нет.")
        return

    command_text = update.message.text
    match = re.search(r'(?:/accuse|виновен)\s+(.+)', command_text, re.IGNORECASE)
    if not match:
        await update.message.reply_text("🗿 Кого обвиняем? Пример: `/accuse Дворецкий Джеймс`.")
        return
    accused_name = match.group(1).strip()

    # Проверяем, есть ли такой подозреваемый
    suspect_names = [s['name'].lower() for s in case["case_data"].get("suspects", [])]
    if accused_name.lower() not in suspect_names:
        await update.message.reply_text(f"🗿 '{accused_name}'? Такого даже в списке нет. Вы совсем идиоты?")
        return

    guilty_suspect_name = case["case_data"]["guilty_suspect_name"]
    is_correct = (accused_name.lower() == guilty_suspect_name.lower())
    
    final_status = "solved_success" if is_correct else "solved_fail"
    
    # Завершаем дело в БД
    cases_collection.update_one(
        {"_id": case["_id"]},
        {"$set": {"status": final_status, "finished_at": datetime.datetime.now(datetime.timezone.utc)}}
    )
    logger.info(f"Дело {case['case_id']} в чате {chat_id} завершено. Результат: {final_status}")
    try:
        await context.bot.unpin_chat_message(chat_id=chat_id, message_id=case["case_id"])
    except Exception:
        pass

    # Формируем финальное сообщение от ИИ
    prompt = (
        f"Ты — гениальный детектив Шерлок Болмс, подводящий итоги дела. "
        f"Команда сыщиков-идиотов выдвинула обвинение против '{accused_name}'. "
        f"Настоящий преступник — '{guilty_suspect_name}'. "
        f"Таким образом, их ответ {'ПРАВИЛЬНЫЙ' if is_correct else 'НЕПРАВИЛЬНЫЙ'}. "
        f"Напиши развернутое, саркастичное заключение по делу. Объясни, кто, как и почему совершил преступление. "
        f"Если команда угадала, неохотно похвали их. Если нет — унизь их интеллектуальные способности. "
        f"Начинай с фразы '🗿 Итак, слушайте сюда, Ватсоны-недоучки...'."
    )
    
    final_reveal = await _call_ionet_api([{"role": "user", "content": prompt}], IONET_TEXT_MODEL_ID, 1024, 0.7)
    
    header = "🏆 ДЕЛО РАСКРЫТО! 🏆" if is_correct else "🤦 ДЕЛО ПРОВАЛЕНО! 🤦"
    
    final_message = f"<b>{header}</b>\n\nВы обвинили: <b>{accused_name}</b>\n\n{final_reveal}"
    
    await update.message.reply_text(final_message, parse_mode='HTML')

# --- ТОЧКА ВХОДА И ЗАПУСК ---

app = Flask(__name__)
@app.route('/')
def index(): return "Sherlock Bolms Detective Agency is running.", 200
@app.route('/healthz')
def health_check(): return "OK", 200 # Упрощенная проверка для начала

async def run_bot_async(application: Application) -> None:
    await application.initialize()
    await application.start()
    if application.updater:
        await application.updater.start_polling()
    logger.info("Бот запущен и работает в режиме polling...")
    await asyncio.Future() # Работать вечно

async def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", help_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("new_case", start_new_case))
    application.add_handler(CommandHandler("case_info", show_case_info))
    application.add_handler(CommandHandler("interrogate", interrogate_suspect))
    application.add_handler(CommandHandler("search", search_location))
    application.add_handler(CommandHandler("accuse", make_accusation))
    
    # Русские текстовые алиасы
    application.add_handler(MessageHandler(filters.Regex(r'(?i).*(новое дело|новый кейс).*'), start_new_case))
    application.add_handler(MessageHandler(filters.Regex(r'(?i).*(что по делу|инфо по делу|статус дела).*'), show_case_info))
    application.add_handler(MessageHandler(filters.Regex(r'(?i).*(допроси|допросить)\s+(.+).*'), interrogate_suspect))
    application.add_handler(MessageHandler(filters.Regex(r'(?i).*(обыщи|обыскать)\s+(.+).*'), search_location))
    application.add_handler(MessageHandler(filters.Regex(r'(?i).*(виновен|обвиняю)\s+(.+).*'), make_accusation))

    logger.info("Обработчики Telegram добавлены.")

    # Настройка и запуск Hypercorn + бота
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
        if application.updater and application.updater.is_running:
            await application.updater.stop()
        if application.running:
            await application.stop()
        shutdown_event.set()

if __name__ == "__main__":
    logger.info("Запуск скрипта bot.py...")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Скрипт остановлен вручную.")
    except Exception as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА В main: {e}", exc_info=True)
