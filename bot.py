# --- НАЧАЛО ПОЛНОГО КОДА BOT.PY (Детективное Агентство "Шерлок Болмс" v2.2 с Улучшенной Отладкой) ---
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

# Импорты Telegram
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
            return "[API вернул пустой или некорректный ответ]" # <<<--- ИЗМЕНЕНИЕ ЗДЕСЬ
    except BadRequestError as e:
        # <<<--- ИЗМЕНЕНИЕ ЗДЕСЬ: Логируем и возвращаем тело ошибки
        error_body = e.body or "No error body"
        logger.error(f"Ошибка BadRequest от ai.io.net API ({model_id}): {e.status_code} - {error_body}", exc_info=False)
        return f"[Ошибка API {e.status_code}: {str(error_body)[:200]}]"
    except Exception as e:
        logger.error(f"ПИЗДЕЦ при вызове ai.io.net API ({model_id}): {e}", exc_info=True)
        return f"[Критическая ошибка API: {type(e).__name__}]"

async def _get_active_case(chat_id: int) -> dict | None:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: cases_collection.find_one({"chat_id": chat_id, "status": "active"}))

# --- ЛОГИКА ГЕНЕРАЦИИ ДЕЛА ---

# <<<--- ИЗМЕНЕНИЕ ЗДЕСЬ: Функция теперь возвращает кортеж (dict | None, str | None)
async def _generate_new_case_data(context: ContextTypes.DEFAULT_TYPE) -> tuple[dict | None, str | None]:
    """Генерирует новое дело с помощью ИИ и парсит его в словарь. Возвращает (дело, текст_ошибки)."""
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
        # <<<--- ИЗМЕНЕНИЕ ЗДЕСЬ: Логируем сырой ответ
        logger.info(f"Сырой ответ от ИИ (первые 500 символов): {str(response)[:500]}")
        
        if not response or response.startswith("["):
            error_msg = f"ИИ вернул ошибку или пустой ответ: {response}"
            logger.error(error_msg)
            return None, error_msg

        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if not json_match:
            error_msg = "Не удалось найти JSON в ответе ИИ."
            logger.error(error_msg)
            return None, error_msg
        
        case_data = json.loads(json_match.group(0))
        required_keys = ["crime_description", "guilty_suspect_name", "suspects", "locations"]
        if not all(key in case_data for key in required_keys):
            error_msg = f"Сгенерированный JSON не содержит всех обязательных ключей."
            logger.error(error_msg)
            return None, error_msg

        return case_data, None # Возвращаем дело и отсутствие ошибки
    except json.JSONDecodeError as e:
        error_msg = f"Ошибка декодирования JSON от ИИ: {e}"
        logger.error(f"{error_msg}\nОтвет ИИ был: {response}")
        return None, error_msg
    except Exception as e:
        error_msg = f"Непредвиденная ошибка при генерации дела: {e}"
        logger.error(error_msg, exc_info=True)
        return None, error_msg

# --- КОМАНДЫ-ОБРАБОТЧИКИ (и остальные функции без изменений) ---

# Код остальных функций (help_command, show_or_update_case_info, и т.д.) остается прежним.
# Нам нужно изменить только start_new_case, чтобы она обрабатывала новый формат ответа.

async def start_new_case(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    if await _get_active_case(chat_id):
        await update.message.reply_text("🗿 Эй, тормози. Одно дело за раз. Используй /case_info, чтобы увидеть панель управления.")
        return

    thinking_msg = await update.message.reply_text("🗿 Принял. Копаюсь в архивах, ищу для вас подходящую грязь...")
    
    # <<<--- ИЗМЕНЕНИЕ ЗДЕСЬ: Получаем и дело, и возможную ошибку
    case_data, error_text = await _generate_new_case_data(context)
    
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=thinking_msg.message_id)
    except Exception: pass

    if not case_data:
        # <<<--- ИЗМЕНЕНИЕ ЗДЕСЬ: Показываем конкретную ошибку
        user_error_message = (
            "🗿 Пиздец. Вдохновение покинуло меня, или мой информатор ушел в запой.\n\n"
            f"<b>Техническая причина отказа:</b> <code>{error_text or 'Неизвестная ошибка'}</code>\n\n"
            "Попробуйте позже."
        )
        await update.message.reply_text(user_error_message, parse_mode='HTML')
        return

    start_message_text = f"🚨 <b>НОВОЕ ДЕЛО АГЕНТСТВА \"ШЕРЛОК БОЛМС\"</b> 🚨\n\n<b><u>Фабула:</u></b>\n{case_data['crime_description']}"
    case_msg = await update.message.reply_text(start_message_text, parse_mode='HTML')

    db_document = {
        "chat_id": chat_id, "case_id": case_msg.message_id, "status": "active",
        "start_time": datetime.datetime.now(datetime.timezone.utc),
        "case_data": case_data, "found_clues": [], "interrogation_log": {}
    }
    cases_collection.insert_one(db_document)
    logger.info(f"Новое дело {case_msg.message_id} создано для чата {chat_id}.")
    
    await show_or_update_case_info(context, chat_id, update_obj=update)


# [ ... Весь остальной код бота остается без изменений ... ]
# Я вставлю его полностью, чтобы вы могли просто скопировать весь файл.

async def show_or_update_case_info(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int | None = None, update_obj: Update | None = None):
    case = await _get_active_case(chat_id)
    if not case:
        try:
            target_message_id = message_id or (update_obj.callback_query.message.message_id if update_obj and update_obj.callback_query else None)
            if target_message_id:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=target_message_id, text="🗿 Это дело уже закрыто или не существует.")
                await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=target_message_id, reply_markup=None)
        except Exception:
            pass
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
        f"<b><u>Найденные улики:</u></b>\n{found_clues_text}\n\n"
        f"🗿 <b>Ваши действия, салаги?</b>"
    )

    keyboard = []
    suspects_buttons = [InlineKeyboardButton(f"Допросить: {s['name']}", callback_data=f"detective:interrogate_menu:{s['name']}") for s in case_data.get("suspects", [])]
    for i in range(0, len(suspects_buttons), 2): keyboard.append(suspects_buttons[i:i + 2])
        
    locations_buttons = [InlineKeyboardButton(f"Обыскать: {l['name']}", callback_data=f"detective:search:{l['name']}") for l in case_data.get("locations", [])]
    for i in range(0, len(locations_buttons), 2): keyboard.append(locations_buttons[i:i + 2])
        
    keyboard.append([InlineKeyboardButton(" Выдвинуть обвинение!", callback_data="detective:accuse_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        target_message_id = message_id or (update_obj.callback_query.message.message_id if update_obj and update_obj.callback_query else None)
        if target_message_id:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=target_message_id, text=info_text, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await context.bot.send_message(chat_id=chat_id, text=info_text, parse_mode='HTML', reply_markup=reply_markup)
    except telegram.error.BadRequest as e:
        if "message is not modified" not in str(e).lower(): logger.warning(f"Ошибка при обновлении игрового сообщения: {e}")
    except Exception as e:
        logger.error(f"Критическая ошибка при отправке/обновлении игрового сообщения: {e}", exc_info=True)

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

async def case_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    if not await _get_active_case(chat_id):
        await update.message.reply_text("🗿 У нас нет активных дел. Используйте `/new_case`.")
        return
    await show_or_update_case_info(context, chat_id, update_obj=update)

async def detective_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    message_id = query.message.message_id
    
    try:
        _, action, *data_parts = query.data.split(':')
        data = ":".join(data_parts)
    except ValueError:
        logger.error(f"Некорректный callback_data: {query.data}")
        return

    case = await _get_active_case(chat_id)
    if not case:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="🗿 Это дело уже закрыто.")
        await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
        return

    if action == 'interrogate_menu':
        target_name = data
        context.user_data['next_action'] = 'interrogate'
        context.user_data['target_suspect'] = target_name
        await query.edit_message_text(text=f"Вы собираетесь допросить <b>{target_name}</b>.\n\nНапишите ваш вопрос в чат следующим сообщением.", parse_mode='HTML')

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
            for clue in newly_found_clues: result_text += f"🔍 Найдена улика: <b>{clue}</b>\n"
            cases_collection.update_one({"_id": case["_id"]}, {"$push": {"found_clues": {"$each": newly_found_clues}}})
        
        await context.bot.send_message(chat_id=chat_id, text=result_text, parse_mode='HTML')
        await show_or_update_case_info(context, chat_id, message_id, update)

    elif action == 'accuse_menu':
        suspects = case["case_data"].get("suspects", [])
        keyboard = [[InlineKeyboardButton(f"Виновен: {s['name']}", callback_data=f"detective:accuse_confirm:{s['name']}")] for s in suspects]
        keyboard.append([InlineKeyboardButton("Отмена", callback_data="detective:info")])
        await query.edit_message_text(text="🗿 Кого вы обвиняете? Это ваш финальный ответ.", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif action == 'accuse_confirm':
        accused_name = data
        guilty_suspect_name = case["case_data"]["guilty_suspect_name"]
        is_correct = (accused_name.lower() == guilty_suspect_name.lower())
        final_status = "solved_success" if is_correct else "solved_fail"
        
        cases_collection.update_one({"_id": case["_id"]}, {"$set": {"status": final_status}})
        try: await context.bot.unpin_chat_message(chat_id=chat_id, message_id=case["case_id"])
        except Exception: pass

        prompt = (f"Ты — гениальный детектив Шерлок Болмс, подводящий итоги дела...")
        final_reveal = await _call_ionet_api([{"role": "user", "content": prompt}], IONET_TEXT_MODEL_ID, 1024, 0.7)
        header = "🏆 ДЕЛО РАСКРЫТО! 🏆" if is_correct else "🤦 ДЕЛО ПРОВАЛЕНО! 🤦"
        final_message = f"<b>{header}</b>\n\nВы обвинили: <b>{accused_name}</b>\n\n{final_reveal}"
        await query.edit_message_text(text=final_message, parse_mode='HTML', reply_markup=None)

    elif action == 'info':
        await show_or_update_case_info(context, chat_id, message_id, update)

async def handle_user_input_for_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    
    action = context.user_data.get('next_action')
    if not action: return

    if action == 'interrogate':
        target_name = context.user_data.get('target_suspect')
        user_question = update.message.text

        del context.user_data['next_action']
        del context.user_data['target_suspect']

        case = await _get_active_case(chat_id)
        if not case or not target_name: return

        suspect_data = next((s for s in case["case_data"].get("suspects", []) if s["name"] == target_name), None)
        if not suspect_data: return

        thinking_msg = await update.message.reply_text("🗿 Передаю ваш каверзный вопрос. Подозреваемый думает, что соврать...")
        
        is_guilty = (suspect_data["name"] == case["case_data"]["guilty_suspect_name"])
        prompt = (
            f"Ты — актер, играющий роль персонажа по имени {suspect_data['name']}... [Промпт как раньше]"
        )

        response = await _call_ionet_api([{"role": "user", "content": prompt}], IONET_TEXT_MODEL_ID, 400, 0.9)
        
        try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_msg.message_id)
        except Exception: pass
        
        if not response or response.startswith("["):
            response = "🗿 ...подозреваемый смотрит на вас стеклянными глазами и молчит."
            
        final_text = f"<b>Допрос: {suspect_data['name']}</b>\n<i>(Ответ на вопрос: '{user_question}')</i>\n\n{response}"
        await context.bot.send_message(chat_id=chat_id, text=final_text, parse_mode='HTML')
        
        await show_or_update_case_info(context, chat_id, case.get("case_id"), update)

app = Flask(__name__)
@app.route('/')
def index(): return "Sherlock Bolms Detective Agency is running.", 200
@app.route('/healthz')
def health_check(): return "OK", 200

async def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", help_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("new_case", start_new_case))
    application.add_handler(CommandHandler("case_info", case_info_command))
    application.add_handler(CallbackQueryHandler(detective_button_callback, pattern=r'^detective:'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input_for_action))

    logger.info("Обработчики Telegram добавлены.")

    port = int(os.environ.get("PORT", 8080))
    hypercorn_config = hypercorn.config.Config()
    hypercorn_config.bind = [f"0.0.0.0:{port}"]
    shutdown_event = asyncio.Event()
    
    async with application:
        await application.start()
        if application.updater: await application.updater.start_polling()
        
        logger.info("Бот запущен...")
        server_task = asyncio.create_task(hypercorn_async_serve(app, hypercorn_config, shutdown_trigger=shutdown_event.wait))
        
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            logger.info("Завершение работы...")
        finally:
            if application.updater: await application.updater.stop()
            await application.stop()
            shutdown_event.set()
            await server_task

if __name__ == "__main__":
    logger.info("Запуск скрипта bot.py...")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Скрипт остановлен вручную.")
    except Exception as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА В main: {e}", exc_info=True)
