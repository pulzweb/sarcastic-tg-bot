# --- НАЧАЛО ПОЛНОГО КОДА BOT.PY (AI.IO.NET ВЕРСИЯ - ФИНАЛ) ---
import logging
import os
import asyncio
import re
import datetime
import requests # Нужен для NewsAPI
import json # Для обработки ответа
import random
import base64
from collections import deque
from flask import Flask
import hypercorn.config
from hypercorn.asyncio import serve as hypercorn_async_serve
import signal
import pymongo
from pymongo.errors import ConnectionFailure

# Импорты для AI.IO.NET (OpenAI библиотека)
from openai import OpenAI, AsyncOpenAI, BadRequestError
import httpx

# Импорты Telegram
from telegram import Update, Bot, User
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, JobQueue
import telegram # --->>> ВОТ ЭТА СТРОКА НУЖНА <<<---

from dotenv import load_dotenv

# Загружаем секреты (.env для локального запуска)
load_dotenv()

# --->>> СИСТЕМА ЗВАНИЙ ПО СООБЩЕНИЯМ <<<---
# Словарь: порог_сообщений: (Название звания, Сообщение о достижении)
TITLES_BY_COUNT = {
    10:    ("Залетный Пиздабол", "🗿 {mention}, ты настрочил аж 10 высеров! Теперь ты официально 'Залетный Пиздабол'. Хули так мало?"),
    50:    ("Почетный Флудер", "🗿 Ого, {mention}, уже 50 сообщений! Поздравляю с почетным званием 'Флудера'. Продолжай засирать чат."),
    100:   ("Мастер Бесполезного Трёпа", "🗿 {mention}, соточка! Ты достиг вершины - 'Мастер Бесполезного Трёпа'. Мои аплодисменты, блядь."),
    250:   ("Кандидат в Затычки для Бочки", "🗿 250 сообщений от {mention}! Серьезная заявка на 'Кандидата в Затычки для Бочки'. Скоро переплюнешь меня."),
    500:   ("Заслуженный Долбоеб Чата™", "🗿 ПИЗДЕЦ! {mention}, 500 высеров! Ты теперь 'Заслуженный Долбоеб Чата™'. Это почти как Нобелевка, но бесполезнее."),
    1000:  ("Попиздякин Друг", "🗿 ЕБАТЬ! {mention}, тысяча! Ты либо мой лучший друг, либо самый главный враг. Звание: 'Попиздякин Друг'."),
    5000:  ("Мегапиздабол", "🗿 Ахуеть! {mention}, 5к! Ты либо безработный, либо самый лютый любитель попиздеть. Звание: 'Мегапиздабол'."),
}
# --->>> КОНЕЦ СИСТЕМЫ ЗВАНИЙ <<<---

# --->>> СИСТЕМА ПИСЕЧНЫХ ЗВАНИЙ <<<---
# Словарь: порог_длины_см: (Название звания, Сообщение о достижении)
PENIS_TITLES_BY_SIZE = {
    10:  ("Короткоствол", "🗿 Ого, {mention}, у тебя уже <b>{size} см</b>! Звание 'Короткоствол' твоё! Не стесняйся, это только начало... или конец, хуй знает."),
    30:  ("Среднестатистический Хуец", "🗿 {mention}, целых <b>{size} см</b>! Поздравляю, ты теперь 'Среднестатистический Хуец'! Почти как у всех, но ты же особенный, да?"),
    50:  ("Приличный Агрегат", "🗿 Нихуя себе, {mention}! <b>{size} см</b>! Ты дослужился до 'Приличного Агрегата'! Таким и бабу можно впечатлить... если она слепая."),
    75:  ("Ебырь-Террорист", "🗿 Пиздец, {mention}, у тебя уже <b>{size} см</b>! Ты теперь 'Ебырь-Террорист'! Опасно, сука, опасно!"),
    100: ("Властелин Писек", "🗿 ВАШУ МАТЬ! {mention}, <b>{size} см</b>!!! Ты теперь 'Властелин Писек Всея Чата'! Снимаю шляпу... и трусы."),
    150: ("Мифический Елдак", "🗿 Это вообще законно, {mention}?! <b>{size} см</b>?! Ты не человек, ты 'Мифический Елдак'! Легенды будут ходить!"),
    200: ("Членотитан", "🗿 Ебать, {mention}?! <b>{size} см</b>?! Ты не человек, ты 'Членотитан'! Битву титанов можно было завершить иначе!"),
    300: ("Тракторист", "🗿 Сюдаааа, {mention}?! <b>{size} см</b>?! Ты достиг членосовершенства, ты 'Тракторист'! И даже бог тебе не судья!"),
    500: ("Дед Максим", "🗿 Епт, {mention}?! <b>{size} см</b>?! Видимо легенды оживают, ты 'Дед Максим'! Ищи бабу Зину и корзину, хуле!"),
    1000: ("Членолебедка", "🗿 Бля, {mention}?! <b>{size} см</b>?! Я хуй знает зачем тебе этот канат, но теперь ты 'Членолебедка'! Можешь смело доставать камазы из кювета!"),
    # Добавь еще, если надо
}
PENIS_GROWTH_COOLDOWN_SECONDS = 6 * 60 * 60 # 6 часов
# --->>> КОНЕЦ СИСТЕМЫ <<<---

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
IO_NET_API_KEY = os.getenv("IO_NET_API_KEY")
MONGO_DB_URL = os.getenv("MONGO_DB_URL")
MAX_MESSAGES_TO_ANALYZE = 200 # Оптимальное значение
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))
if ADMIN_USER_ID == 0: logger.warning("ADMIN_USER_ID не задан!")

# --- НАСТРОЙКИ НОВОСТЕЙ (GNEWS) ---
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY")
NEWS_COUNTRY = "ru" # Страна
NEWS_LANG = "ru"    # Язык новостей
NEWS_COUNT = 3      # Сколько новостей брать
NEWS_POST_INTERVAL = 60 * 60 * 6 # Интервал постинга (6 часов)
NEWS_JOB_NAME = "post_news_job"

if not GNEWS_API_KEY:
    logger.warning("GNEWS_API_KEY не найден! Новостная функция будет отключена.")


# Проверка ключей
if not TELEGRAM_BOT_TOKEN: raise ValueError("НЕ НАЙДЕН TELEGRAM_BOT_TOKEN!")
if not IO_NET_API_KEY: raise ValueError("НЕ НАЙДЕН IO_NET_API_KEY!")
if not MONGO_DB_URL: raise ValueError("НЕ НАЙДЕНА MONGO_DB_URL!")

# --- Логирование ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("hypercorn").setLevel(logging.INFO)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("pymongo").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- ПОДКЛЮЧЕНИЕ К MONGODB ATLAS ---
try:
    mongo_client = pymongo.MongoClient(MONGO_DB_URL, serverSelectionTimeoutMS=5000)
    mongo_client.admin.command('ping')
    logger.info("Успешное подключение к MongoDB Atlas!")
    db = mongo_client['popizdyaka_db']
    history_collection = db['message_history']
    last_reply_collection = db['last_replies']
    chat_activity_collection = db['chat_activity']
    chat_activity_collection.create_index("chat_id", unique=True)
    user_profiles_collection = db['user_profiles']
    user_profiles_collection.create_index("user_id", unique=True)
    logger.info("Коллекция user_profiles готова.")
    logger.info("Коллекции MongoDB готовы.")
    bot_status_collection = db['bot_status']
    logger.info("Коллекция bot_status готова.")
except Exception as e:
    logger.critical(f"ПИЗДЕЦ при настройке MongoDB: {e}", exc_info=True)
    raise SystemExit(f"Ошибка настройки MongoDB: {e}")

# --- НАСТРОЙКА КЛИЕНТА AI.IO.NET API ---
try:
    ionet_client = AsyncOpenAI(
        api_key=IO_NET_API_KEY,
        base_url="https://api.intelligence.io.solutions/api/v1/" # ПРОВЕРЕННЫЙ URL!
    )
    logger.info("Клиент AsyncOpenAI для ai.io.net API настроен.")
except Exception as e:
     logger.critical(f"ПИЗДЕЦ при настройке клиента ai.io.net: {e}", exc_info=True)
     raise SystemExit(f"Не удалось настроить клиента ai.io.net: {e}")

# --- ВЫБОР МОДЕЛЕЙ AI.IO.NET (ПРОВЕРЬ ДОСТУПНОСТЬ!) ---
IONET_TEXT_MODEL_ID = "mistralai/Mistral-Large-Instruct-2411" # Твоя модель для текста
IONET_VISION_MODEL_ID = "Qwen/Qwen2-VL-7B-Instruct" # Для картинок
logger.info(f"Текстовая модель ai.io.net: {IONET_TEXT_MODEL_ID}")
logger.info(f"Vision модель ai.io.net: {IONET_VISION_MODEL_ID}")

# --- Хранилище истории в памяти больше не нужно ---
logger.info(f"Максимальная длина истории для анализа из БД: {MAX_MESSAGES_TO_ANALYZE}")

# --- Вспомогательная функция для вызова текстового API ---
async def _call_ionet_api(messages: list, model_id: str, max_tokens: int, temperature: float) -> str | None:
    """Вызывает текстовый API ai.io.net и возвращает ответ или текст ошибки."""
    try:
        logger.info(f"Отправка запроса к ai.io.net API ({model_id})...")
        response = await ionet_client.chat.completions.create(
            model=model_id, messages=messages, max_tokens=max_tokens, temperature=temperature
        )
        logger.info(f"Получен ответ от {model_id}.")
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
        else: logger.warning(f"Ответ от {model_id} пуст/некорректен: {response}"); return None
    except BadRequestError as e:
        logger.error(f"Ошибка BadRequest от ai.io.net API ({model_id}): {e.status_code} - {e.body}", exc_info=False) # Не пишем весь трейсбек
        error_detail = str(e.body or e)
        return f"🗿 API {model_id.split('/')[1].split('-')[0]} вернул ошибку: `{error_detail[:100]}`"
    except Exception as e:
        logger.error(f"ПИЗДЕЦ при вызове ai.io.net API ({model_id}): {e}", exc_info=True)
        return f"🗿 Ошибка API: `{type(e).__name__}`"
    
    ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))
    if ADMIN_USER_ID == 0: logger.warning("ADMIN_USER_ID не задан!")

# --->>> ВОТ ЭТИ ДВЕ ФУНКЦИИ НУЖНЫ ЗДЕСЬ <<<---
async def is_maintenance_mode(loop: asyncio.AbstractEventLoop) -> bool:
    """Проверяет в MongoDB, активен ли режим техработ."""
    try:
        status_doc = await loop.run_in_executor(None, lambda: bot_status_collection.find_one({"_id": "maintenance_status"}))
        return status_doc.get("active", False) if status_doc else False
    except Exception as e:
        logger.error(f"Ошибка чтения статуса техработ из MongoDB: {e}")
        return False

async def set_maintenance_mode(active: bool, loop: asyncio.AbstractEventLoop) -> bool:
    """Включает или выключает режим техработ в MongoDB."""
    try:
        await loop.run_in_executor(None, lambda: bot_status_collection.update_one({"_id": "maintenance_status"},{"$set": {"active": active, "updated_at": datetime.datetime.now(datetime.timezone.utc)} }, upsert=True))
        logger.info(f"Режим техработ {'ВКЛЮЧЕН' if active else 'ВЫКЛЮЧЕН'}.")
        return True
    except Exception as e:
        logger.error(f"Ошибка записи статуса техработ в MongoDB: {e}")
        return False
# --->>> КОНЕЦ ФУНКЦИЙ ДЛЯ ТЕХРАБОТ <<<---

# --- ПОЛНОСТЬЮ ПЕРЕПИСАННАЯ store_message (v3, с профилями и званиями) ---
async def store_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # 1. Проверяем базовые вещи
    if not update.message or not update.message.from_user or not update.message.chat:
        return

    user = update.message.from_user
    chat_id = update.message.chat.id
    timestamp = update.message.date or datetime.datetime.now(datetime.timezone.utc)

    # 2. Определяем текст сообщения или заглушку
    message_text = None
    if update.message.text: message_text = update.message.text
    elif update.message.photo: file_id = update.message.photo[-1].file_id; message_text = f"[КАРТИНКА:{file_id}]"
    elif update.message.sticker: emoji = update.message.sticker.emoji or ''; message_text = f"[СТИКЕР {emoji}]"
    elif update.message.video: message_text = "[ОТПРАВИЛ(А) ВИДЕО]"
    elif update.message.voice: message_text = "[ОТПРАВИЛ(А) ГОЛОСОВОЕ]"

    # Если не смогли определить текст/заглушку - выходим
    if not message_text: return

    # 3. Работаем с профилем пользователя в MongoDB
    profile = None
    current_message_count = 0
    current_title = None
    custom_nickname = None
    display_name = user.first_name or "Аноним" # Имя по умолчанию
    profile_update_result = None
    loop = asyncio.get_running_loop()

    try:
        # Атомарно увеличиваем счетчик сообщений и получаем обновленный профиль
        # $inc увеличивает поле на 1
        # $set устанавливает/обновляет поля
        # $setOnInsert устанавливает поля только при создании нового документа
        # return_document=pymongo.ReturnDocument.AFTER возвращает документ ПОСЛЕ обновления
        profile_update_result = await loop.run_in_executor(
            None,
            lambda: user_profiles_collection.find_one_and_update(
                {"user_id": user.id}, # Ищем по ID
                {
                    "$inc": {"message_count": 1},
                    "$set": {"tg_first_name": user.first_name, "tg_username": user.username},
                    # --->>> УБИРАЕМ message_count ОТСЮДА <<<---
                    "$setOnInsert": {"user_id": user.id, "custom_nickname": None, "current_title": None,
                                     "penis_size": 0, "last_penis_growth": datetime.datetime.fromtimestamp(0, datetime.timezone.utc), "current_penis_title": None}
                    # --->>> КОНЕЦ ИСПРАВЛЕНИЯ <<<---
                },
                projection={"message_count": 1, "custom_nickname": 1, "current_title": 1}, # Возвращаем нужные поля
                upsert=True, # Создаем, если нет
                return_document=pymongo.ReturnDocument.AFTER # Возвращаем обновленный
            )
        )

        if profile_update_result:
            profile = profile_update_result # Сохраняем результат
            current_message_count = profile.get("message_count", 1) # Получаем новый счетчик
            current_title = profile.get("current_title") # Текущее записанное звание
            custom_nickname = profile.get("custom_nickname") # Кастомный ник
            if custom_nickname:
                 display_name = custom_nickname # Используем кастомный ник для логов/истории
             # logger.debug(f"Обновлен счетчик для {display_name} ({user.id}): {current_message_count}")

    except Exception as e:
        logger.error(f"Ошибка обновления профиля/счетчика для user_id {user.id} в MongoDB: {e}", exc_info=True)
        # Продолжаем выполнение, но без обновления званий

    # 4. Записываем сообщение в историю (используя display_name)
    message_doc = {
        "chat_id": chat_id, "user_name": display_name, "text": message_text,
        "timestamp": timestamp, "message_id": update.message.message_id, "user_id": user.id # Добавили user_id в историю
    }
    try:
        await loop.run_in_executor(None, lambda: history_collection.insert_one(message_doc))
    except Exception as e:
        logger.error(f"Ошибка записи в history_collection: {e}")

    # 5. Обновляем активность чата (как было)
    try:
        activity_update_doc = {"$set": {"last_message_time": timestamp}, "$setOnInsert": {"last_bot_shitpost_time": datetime.datetime.fromtimestamp(0, datetime.timezone.utc), "chat_id": chat_id}}
        await loop.run_in_executor(None, lambda: chat_activity_collection.update_one({"chat_id": chat_id}, activity_update_doc, upsert=True))
    except Exception as e:
         logger.error(f"Ошибка обновления активности чата {chat_id}: {e}")

    # 6. Проверяем достижение нового звания (только если смогли обновить профиль)
    if profile:
         new_title_achieved = None
         new_title_message = ""
         # Ищем самое высокое звание, которого достиг пользователь
         for count_threshold, (title_name, achievement_message) in sorted(TITLES_BY_COUNT.items()):
             if current_message_count >= count_threshold:
                 new_title_achieved = title_name
                 new_title_message = achievement_message # Запоминаем сообщение для этого звания
             else:
                 break # Дальше пороги выше

         # Если достигнутое звание НОВОЕ (не совпадает с тем, что записано в профиле)
         if new_title_achieved and new_title_achieved != current_title:
             logger.info(f"Пользователь {display_name} ({user.id}) достиг нового звания: {new_title_achieved} ({current_message_count} сообщений)")
             # Обновляем звание в БД
             try:
                 await loop.run_in_executor(
                     None,
                     lambda: user_profiles_collection.update_one(
                         {"user_id": user.id},
                         {"$set": {"current_title": new_title_achieved}}
                     )
                 )
                 # Отправляем поздравительно-уничижительное сообщение
                 # Используем mention_html для кликабельности
                 mention = user.mention_html()
                 achievement_text = new_title_message.format(mention=mention) # Подставляем упоминание в шаблон
                 await context.bot.send_message(chat_id=chat_id, text=achievement_text, parse_mode='HTML')
             except Exception as e:
                 logger.error(f"Ошибка обновления звания или отправки сообщения о звании для user_id {user.id}: {e}", exc_info=True)

# Конец функции store_message



# --- ПОЛНАЯ ФУНКЦИЯ analyze_chat (С УЛУЧШЕННЫМ УДАЛЕНИЕМ <think>) ---
async def analyze_chat(update: Update | None, context: ContextTypes.DEFAULT_TYPE, direct_chat_id: int | None = None, direct_user: User | None = None) -> None:
     # --->>> НАЧАЛО НОВОЙ ПРОВЕРКИ ТЕХРАБОТ <<<---
# Проверяем наличие update и message - без них проверка невозможна
    if not update or not update.message or not update.message.from_user or not update.message.chat:
        logger.warning(f"Не могу проверить техработы - нет данных в update ({__name__})") # Логгируем имя текущей функции
        # Если это важная команда, можно тут вернуть ошибку пользователю
        # await context.bot.send_message(chat_id=update.effective_chat.id, text="Ошибка проверки данных.")
        return # Или просто выйти

    real_chat_id = update.message.chat.id
    real_user_id = update.message.from_user.id
    real_chat_type = update.message.chat.type

    loop = asyncio.get_running_loop()
    maintenance_active = await is_maintenance_mode(loop) # Вызываем функцию проверки

    # Блокируем, если техработы ВКЛЮЧЕНЫ и это НЕ админ в ЛС
    if maintenance_active and (real_user_id != ADMIN_USER_ID or real_chat_type != 'private'):
        logger.info(f"Команда отклонена из-за режима техработ в чате {real_chat_id}")
        try: # Пытаемся ответить и удалить команду
            await context.bot.send_message(chat_id=real_chat_id, text="🔧 Сорян, у меня сейчас технические работы. Попробуй позже.")
            await context.bot.delete_message(chat_id=real_chat_id, message_id=update.message.message_id)
        except Exception as e:
            logger.warning(f"Не удалось ответить/удалить сообщение о техработах: {e}")
        return # ВЫХОДИМ ИЗ ФУНКЦИИ
# --->>> КОНЕЦ НОВОЙ ПРОВЕРКИ ТЕХРАБОТ <<<---
    # Получаем chat_id и user либо из Update, либо из прямых аргументов
    if update and update.message:
        chat_id = update.message.chat_id
        user = update.message.from_user
        user_name = user.first_name if user else "Хуй Пойми Кто"
    elif direct_chat_id and direct_user:
        chat_id = direct_chat_id
        user = direct_user
        user_name = user.first_name or "Переделкин" # Имя для retry
    else:
        logger.error("analyze_chat вызвана некорректно!")
        return

    logger.info(f"Пользователь '{user_name}' запросил анализ текста в чате {chat_id} через {IONET_TEXT_MODEL_ID}")

    # --- ЧТЕНИЕ ИСТОРИИ ИЗ MONGODB ---
    messages_from_db = []
    try:
        logger.debug(f"Запрос истории для чата {chat_id} из MongoDB...")
        limit = MAX_MESSAGES_TO_ANALYZE
        query = {"chat_id": chat_id}
        sort_order = [("timestamp", pymongo.DESCENDING)]
        loop = asyncio.get_running_loop()
        history_cursor = await loop.run_in_executor(
            None, lambda: history_collection.find(query).sort(sort_order).limit(limit)
        )
        messages_from_db = list(history_cursor)[::-1] # Переворачиваем
        history_len = len(messages_from_db)
        logger.info(f"Из MongoDB для чата {chat_id} загружено {history_len} сообщений.")
    except Exception as e:
        logger.error(f"Ошибка чтения истории MongoDB: {e}")
        await context.bot.send_message(chat_id=chat_id, text="Бля, не смог прочитать историю из БД.")
        return

    # Проверяем, достаточно ли сообщений
    min_msgs = 10
    if history_len < min_msgs:
        logger.info(f"В чате {chat_id} слишком мало сообщений в БД ({history_len}/{min_msgs}).")
        await context.bot.send_message(chat_id=chat_id, text=f"Слышь, {user_name}, надо {min_msgs} сообщений, а в БД {history_len}.")
        return

    # Формируем текст для ИИ
    conversation_lines = [f"{msg.get('user_name', '?')}: {msg.get('text', '')}" for msg in messages_from_db]
    conversation_text = "\n".join(conversation_lines)
    logger.info(f"Начинаю анализ {len(messages_from_db)} сообщений через {IONET_TEXT_MODEL_ID}...")

    # Вызов ИИ
    try:
        # Промпт (оставляем тот, что с сутью и панчлайном, но с запретом мета)
        system_prompt = (
            f"Ты - злобный, циничный и пиздецки наблюдательный хронист ебанутого Telegram-чата. Твоя задача - прочитать ПОСЛЕДНИЙ фрагмент переписки и составить из него саркастическую хронику, выделив **несколько (постарайся найти от 3 до 7, если есть!) САМЫХ ЯРКИХ, ТУПЫХ или ПОКАЗАТЕЛЬНЫХ СЮЖЕТОВ/ДИАЛОГОВ/ИСТОРИЙ**.\n\n"
            f"Инструкции для хроники:\n"
            f"1.  Для КАЖДОГО сюжета напиши ОДИН абзац (2-4 предложения).\n"
            f"2.  В начале абзаца **ОБЯЗАТЕЛЬНО УКАЖИ ГЛАВНЫХ ДЕЙСТВУЮЩИХ ЛИЦ** (по именам/никам из диалога, например: 'Volodya и Ⓜ️ⓊⓈⓎⓐ опять срались...' или 'Наша Катя рассказала историю...').\n"
            f"3.  **ОПИШИ СУТЬ** сюжета в своей фирменной токсичной, саркастичной, матерной манере. Используй черный юмор, высмеивай тупость, нелепость, банальность.\n"
            f"4.  В конце КАЖДОГО абзаца добавь **КОРОТКИЙ (3-7 слов) ЕДКИЙ ПАНЧЛАЙН/ВЫВОД**, подводящий итог этому сюжету.\n"
            f"5.  **КАЖДЫЙ** абзац (запись хроники) начинай с новой строки и символа **`🗿 `**.\n"
            f"6.  Игнорируй незначащий флуд. Ищи именно **СЮЖЕТЫ**.\n"
            f"7.  НЕ ПИШИ никаких вступлений типа 'Вот хроника:'. СРАЗУ начинай с первого `🗿 `.\n"
            f"8.  Если интересных сюжетов не нашлось, напиши ОДНУ строку: `🗿 Перепись долбоебов не выявила сегодня ярких экземпляров. Скукота.`\n\n"
            f"Пример ЗАЕБАТОГО формата:\n"
            f"🗿 Volodya подкинул идею духов с запахом тухлой селедки, Ⓜ️ⓊⓈⓎⓐ захотела травить ими коллег, а Волкова 😈 предложила просто наблевать в ебало. — Практичные сучки, хули.\n"
            f"🗿 Щедрый Volodya предложил Ⓜ️ⓊⓈⓎⓐ икры, попутно пнув жадину Волкову 😈, которая реально сожрала все запасы. — Крыса консервная.\n"
            f"🗿 Левша Volodya прочитал про миллиардеров и тут же заорал 'ГДЕ МОИ БАБКИ?!'. — До сих пор ищет, наивный.\n\n"
            f"Проанализируй диалог ниже и составь подобную хронику:"
        )
        messages_for_api = [
            {"role": "system", "content": system_prompt},
            # Передаем сам диалог как сообщение пользователя
            {"role": "user", "content": f"Проанализируй этот диалог:\n```\n{conversation_text}\n```"}
        ]

        thinking_message = await context.bot.send_message(chat_id=chat_id, text=f"Так, блядь, щас подключу мозги {IONET_TEXT_MODEL_ID.split('/')[1].split('-')[0]}...")

        # Вызываем вспомогательную функцию
        sarcastic_summary = await _call_ionet_api(messages_for_api, IONET_TEXT_MODEL_ID, 600, 0.7) or "[Хроника не составлена]" # Увеличили до 600

        # --->>> УЛУЧШЕННОЕ УДАЛЕНИЕ <think> ТЕГОВ <<<---
        # Компилируем регулярку один раз для эффективности (хотя тут не критично)
        think_pattern = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)
        if sarcastic_summary and think_pattern.search(sarcastic_summary):
            logger.info("Обнаружены теги <think>, удаляем...")
            # Заменяем найденное на пустую строку и убираем лишние пробелы по краям
            sarcastic_summary = think_pattern.sub("", sarcastic_summary).strip()
            logger.info(f"Текст после удаления <think>: '{sarcastic_summary[:50]}...'")
        # --->>> КОНЕЦ УЛУЧШЕНИЯ <<<---

        # Добавляем Моаи, если его нет и это не ошибка
        if not sarcastic_summary.startswith("🗿") and not sarcastic_summary.startswith("["):
            sarcastic_summary = "🗿 " + sarcastic_summary

        # Удаляем "Думаю..."
        try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass

        # Страховочная обрезка и отправка
        MAX_MESSAGE_LENGTH = 4096;
        if len(sarcastic_summary) > MAX_MESSAGE_LENGTH: sarcastic_summary = sarcastic_summary[:MAX_MESSAGE_LENGTH - 3] + "..."
        sent_message = await context.bot.send_message(chat_id=chat_id, text=sarcastic_summary)
        logger.info(f"Отправил результат анализа ai.io.net '{sarcastic_summary[:50]}...'")

        # Запись для /retry
        if sent_message:
             reply_doc = { "chat_id": chat_id, "message_id": sent_message.message_id, "analysis_type": "text", "timestamp": datetime.datetime.now(datetime.timezone.utc) }
             try:
                 loop = asyncio.get_running_loop(); await loop.run_in_executor(None, lambda: last_reply_collection.update_one({"chat_id": chat_id}, {"$set": reply_doc}, upsert=True))
                 logger.debug(f"Сохранен/обновлен ID ({sent_message.message_id}, text) для /retry чата {chat_id}.")
             except Exception as e: logger.error(f"Ошибка записи /retry (text) в MongoDB: {e}")

    except Exception as e: # Общая ошибка самого analyze_chat
        logger.error(f"ПИЗДЕЦ в analyze_chat (после чтения БД): {e}", exc_info=True)
        try:
            if 'thinking_message' in locals(): await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass
        await context.bot.send_message(chat_id=chat_id, text=f"Бля, {user_name}, я обосрался при анализе чата. Ошибка: `{type(e).__name__}`.")

# --- КОНЕЦ ПОЛНОЙ ФУНКЦИИ analyze_chat ---

# --- ОБРАБОТЧИК КОМАНДЫ /analyze_pic (ПЕРЕПИСАН ПОД VISION МОДЕЛЬ) ---
async def analyze_pic(update: Update | None, context: ContextTypes.DEFAULT_TYPE, direct_chat_id: int | None = None, direct_user: User | None = None, direct_file_id: str | None = None) -> None:
     # --->>> НАЧАЛО НОВОЙ ПРОВЕРКИ ТЕХРАБОТ <<<---
# Проверяем наличие update и message - без них проверка невозможна
    if not update or not update.message or not update.message.from_user or not update.message.chat:
        logger.warning(f"Не могу проверить техработы - нет данных в update ({__name__})") # Логгируем имя текущей функции
        # Если это важная команда, можно тут вернуть ошибку пользователю
        # await context.bot.send_message(chat_id=update.effective_chat.id, text="Ошибка проверки данных.")
        return # Или просто выйти

    real_chat_id = update.message.chat.id
    real_user_id = update.message.from_user.id
    real_chat_type = update.message.chat.type

    loop = asyncio.get_running_loop()
    maintenance_active = await is_maintenance_mode(loop) # Вызываем функцию проверки

    # Блокируем, если техработы ВКЛЮЧЕНЫ и это НЕ админ в ЛС
    if maintenance_active and (real_user_id != ADMIN_USER_ID or real_chat_type != 'private'):
        logger.info(f"Команда отклонена из-за режима техработ в чате {real_chat_id}")
        try: # Пытаемся ответить и удалить команду
            await context.bot.send_message(chat_id=real_chat_id, text="🔧 Сорян, у меня сейчас технические работы. Попробуй позже.")
            await context.bot.delete_message(chat_id=real_chat_id, message_id=update.message.message_id)
        except Exception as e:
            logger.warning(f"Не удалось ответить/удалить сообщение о техработах: {e}")
        return # ВЫХОДИМ ИЗ ФУНКЦИИ
# --->>> КОНЕЦ НОВОЙ ПРОВЕРКИ ТЕХРАБОТ <<<---
    # Получаем chat_id, user, user_name, image_file_id (из update или аргументов)
    image_file_id = None; chat_id = None; user = None; user_name = "Фотограф хуев"
    retry_key = f'retry_pic_{direct_chat_id or (update.message.chat_id if update and update.message else None)}'
    if direct_chat_id and direct_user and direct_file_id: # Вызов из retry
        chat_id = direct_chat_id; user = direct_user; image_file_id = direct_file_id
        user_name = user.first_name if user else user_name
        logger.info(f"Получен file_id {image_file_id} напрямую для /retry.")
        context.bot_data.pop(retry_key, None) # Очищаем сразу
    elif update and update.message and update.message.reply_to_message and update.message.reply_to_message.photo: # Обычный вызов
        chat_id = update.message.chat_id; user = update.message.from_user
        user_name = user.first_name if user else user_name
        reply_msg = update.message.reply_to_message; photo_large = reply_msg.photo[-1]; image_file_id = photo_large.file_id
        logger.info(f"Получен file_id {image_file_id} из reply_to_message.")
    else:
        error_chat_id = update.message.chat_id if update and update.message else None
        if error_chat_id: await context.bot.send_message(chat_id=error_chat_id, text="Ответь этой командой на КАРТИНКУ!")
        else: logger.error("analyze_pic вызвана некорректно!")
        return
    if not image_file_id: logger.error("Не удалось получить file_id!"); await context.bot.send_message(chat_id=chat_id, text="Не нашел ID картинки."); return
    logger.info(f"Пользователь '{user_name}' запросил анализ картинки (ID: {image_file_id}) через {IONET_VISION_MODEL_ID}")
    try: # Скачивание и вызов ИИ
        logger.info(f"Скачивание картинки {image_file_id}...")
        photo_file = await context.bot.get_file(image_file_id, read_timeout=60)
        photo_bytes_io = await photo_file.download_as_bytearray(read_timeout=60)
        photo_bytes = bytes(photo_bytes_io)
        if not photo_bytes: raise ValueError("Скачаны пустые байты картинки")
        logger.info(f"Картинка скачана, размер: {len(photo_bytes)} байт.")
        image_prompt_text = (
            f"Ты - стендап-комик с ОЧЕНЬ черным юмором, циник и мастер саркастических замечаний. Тебе показали КАРТИНКУ. Забудь про техническое качество фото. Сосредоточься на **СОДЕРЖАНИИ**: что за нелепая, тупая, смешная или просто странная хуйня там происходит? "
            f"Твоя задача: Выдай **КОРОТКИЙ (1-3 предложения), УБИЙСТВЕННО СМЕШНОЙ и ЕДКИЙ** комментарий к сюжету/объектам на картинке. Используй черный юмор, абсурд, неожиданные сравнения и **МАТ** для комического эффекта. Высмеивай происходящее.\n\n"
            f"ВАЖНО: Будь дерзким и злым, но остроумным. НЕ РАССУЖДАЙ о задании. НЕ пиши вступлений. СРАЗУ начинай ответ с `🗿 `.\n\n"
            f"Пример (кот в коробке): '🗿 Бля, кошак косплеит Диогена? Или просто готовится к отправке на живодерню? Выглядит решительно.'\n"
            f"Пример (пикник): '🗿 О, человеки вывезли свои жирные жопы пожрать на травке. Наверное, обсуждают смысл бытия между закидыванием мазика и пивасика.'\n"
            f"Пример (смешная собака): '🗿 Это что за генетический выродок? Помесь мопса с Чужим? Его бы на опыты сдать, а не фоткать.'\n"
            f"Пример (еда): '🗿 Фу, блядь, кто-то сфоткал остатки вчерашнего ужина? Или это уже переваренное? Выглядит одинаково хуево.'\n\n"
            f"Твой ЧЕРНО-ЮМОРНОЙ и САРКАСТИЧНЫЙ комментарий к приложенной картинке (НАЧИНАЙ С 🗿):"
        )
        # --->>> КОНЕЦ НОВОГО ПРОМПТА <<<---

        base64_image = base64.b64encode(photo_bytes).decode('utf-8')
        messages_for_api = [{"role": "user","content": [ {"type": "text", "text": image_prompt_text}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}} ]}]

        thinking_message = await context.bot.send_message(chat_id=chat_id, text=f"Так-так, блядь, ща посмотрим ({IONET_VISION_MODEL_ID.split('/')[0]} видит!)...") # Заменили имя модели
        sarcastic_comment = await _call_ionet_api(messages_for_api, IONET_VISION_MODEL_ID, 300, 0.75) or "[Попиздяка промолчал]" # Уменьшили max_tokens и температуру
        if not sarcastic_comment.startswith("🗿") and not sarcastic_comment.startswith("["): sarcastic_comment = "🗿 " + sarcastic_comment
        try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass

        MAX_MESSAGE_LENGTH = 4096;
        if len(sarcastic_comment) > MAX_MESSAGE_LENGTH: sarcastic_comment = sarcastic_comment[:MAX_MESSAGE_LENGTH - 3] + "..."

        sent_message = await context.bot.send_message(chat_id=chat_id, text=sarcastic_comment)
        logger.info(f"Отправлен коммент к картинке ai.io.net '{sarcastic_comment[:50]}...'")
        if sent_message: # Запись для /retry
             reply_doc = {"chat_id": chat_id, "message_id": sent_message.message_id, "analysis_type": "pic", "source_file_id": image_file_id, "timestamp": datetime.datetime.now(datetime.timezone.utc)}
             try: loop = asyncio.get_running_loop(); await loop.run_in_executor(None, lambda: last_reply_collection.update_one({"chat_id": chat_id}, {"$set": reply_doc}, upsert=True))
             except Exception as e: logger.error(f"Ошибка записи /retry (pic) в MongoDB: {e}")
    except Exception as e: # Общая ошибка
        logger.error(f"ПИЗДЕЦ в analyze_pic: {e}", exc_info=True)
        try:
            if 'thinking_message' in locals(): await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass
        await context.bot.send_message(chat_id=chat_id, text=f"Бля, {user_name}, я обосрался при анализе картинки. Ошибка: `{type(e).__name__}`.")

# --- ОСТАЛЬНЫЕ ФУНКЦИИ С ВЫЗОВОМ ИИ (ПЕРЕПИСАНЫ) ---

# --- ПОЛНАЯ ФУНКЦИЯ ДЛЯ КОМАНДЫ /retry (ВЕРСИЯ ДЛЯ БД, БЕЗ FAKE UPDATE) ---
async def retry_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
         # --->>> НАЧАЛО НОВОЙ ПРОВЕРКИ ТЕХРАБОТ <<<---
# Проверяем наличие update и message - без них проверка невозможна
    if not update or not update.message or not update.message.from_user or not update.message.chat:
        logger.warning(f"Не могу проверить техработы - нет данных в update ({__name__})") # Логгируем имя текущей функции
        # Если это важная команда, можно тут вернуть ошибку пользователю
        # await context.bot.send_message(chat_id=update.effective_chat.id, text="Ошибка проверки данных.")
        return # Или просто выйти

    real_chat_id = update.message.chat.id
    real_user_id = update.message.from_user.id
    real_chat_type = update.message.chat.type

    loop = asyncio.get_running_loop()
    maintenance_active = await is_maintenance_mode(loop) # Вызываем функцию проверки

    # Блокируем, если техработы ВКЛЮЧЕНЫ и это НЕ админ в ЛС
    if maintenance_active and (real_user_id != ADMIN_USER_ID or real_chat_type != 'private'):
        logger.info(f"Команда отклонена из-за режима техработ в чате {real_chat_id}")
        try: # Пытаемся ответить и удалить команду
            await context.bot.send_message(chat_id=real_chat_id, text="🔧 Сорян, у меня сейчас технические работы. Попробуй позже.")
            await context.bot.delete_message(chat_id=real_chat_id, message_id=update.message.message_id)
        except Exception as e:
            logger.warning(f"Не удалось ответить/удалить сообщение о техработах: {e}")
        return # ВЫХОДИМ ИЗ ФУНКЦИИ
# --->>> КОНЕЦ НОВОЙ ПРОВЕРКИ ТЕХРАБОТ <<<---
    """Повторяет последний анализ (текста, картинки, стиха и т.д.), читая данные из MongoDB и вызывая нужную функцию напрямую."""
    if not update.message or not update.message.reply_to_message:
        await context.bot.send_message(chat_id=update.message.chat_id, text="Надо ответить этой командой на тот МОЙ высер, который ты хочешь переделать.")
        return

    chat_id = update.message.chat_id
    user_command_message_id = update.message.message_id
    replied_message_id = update.message.reply_to_message.message_id
    replied_message_user_id = update.message.reply_to_message.from_user.id
    bot_id = context.bot.id
    user_who_requested_retry = update.message.from_user # Юзер, который вызвал /retry

    logger.info(f"Пользователь '{user_who_requested_retry.first_name or 'ХЗ кто'}' запросил /retry в чате {chat_id}, отвечая на сообщение {replied_message_id}")

    if replied_message_user_id != bot_id:
        logger.warning("Команда /retry вызвана не в ответ на сообщение бота.")
        await context.bot.send_message(chat_id=chat_id, text="Эээ, ты ответил не на МОЕ сообщение.")
        try: await context.bot.delete_message(chat_id=chat_id, message_id=user_command_message_id)
        except Exception: pass
        return

    last_reply_data = None
    try:
        loop = asyncio.get_running_loop()
        last_reply_data = await loop.run_in_executor(None, lambda: last_reply_collection.find_one({"chat_id": chat_id}))
    except Exception as e:
        logger.error(f"Ошибка чтения /retry из MongoDB для чата {chat_id}: {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text="Бля, не смог залезть в свою память (БД).")
        try: await context.bot.delete_message(chat_id=chat_id, message_id=user_command_message_id)
        except Exception: pass
        return

    if not last_reply_data or last_reply_data.get("message_id") != replied_message_id:
        saved_id = last_reply_data.get("message_id") if last_reply_data else 'None'
        logger.warning(f"Не найдена запись /retry для чата {chat_id} или ID ({replied_message_id}) не совпадает ({saved_id}).")
        await context.bot.send_message(chat_id=chat_id, text="Не помню свой последний высер или ты ответил не на тот. Не могу переделать.")
        try: await context.bot.delete_message(chat_id=chat_id, message_id=user_command_message_id)
        except Exception: pass
        return

    analysis_type_to_retry = last_reply_data.get("analysis_type")
    source_file_id_to_retry = last_reply_data.get("source_file_id") # Для картинок
    target_name_to_retry = last_reply_data.get("target_name")       # Для стихов и роастов
    target_id_to_retry = last_reply_data.get("target_id")           # Для роастов
    gender_hint_to_retry = last_reply_data.get("gender_hint")       # Для роастов

    logger.info(f"Повторяем анализ типа '{analysis_type_to_retry}' для чата {chat_id}...")

    # Удаляем старые сообщения
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=replied_message_id)
        logger.info(f"Удален старый ответ бота {replied_message_id}")
        await context.bot.delete_message(chat_id=chat_id, message_id=user_command_message_id)
        logger.info(f"Удалена команда /retry {user_command_message_id}")
    except Exception as e:
        logger.error(f"Ошибка при удалении старых сообщений в /retry: {e}")
        await context.bot.send_message(chat_id=chat_id, text="Бля, не смог удалить старое, но попробую переделать.")

    # Вызываем нужную функцию анализа НАПРЯМУЮ
    try:
        if analysis_type_to_retry == 'text':
            logger.info("Вызов analyze_chat для /retry...")
            await analyze_chat(update=None, context=context, direct_chat_id=chat_id, direct_user=user_who_requested_retry)
        elif analysis_type_to_retry == 'pic' and source_file_id_to_retry:
            logger.info(f"Вызов analyze_pic для /retry с file_id {source_file_id_to_retry}...")
            await analyze_pic(update=None, context=context, direct_chat_id=chat_id, direct_user=user_who_requested_retry, direct_file_id=source_file_id_to_retry)
        elif analysis_type_to_retry == 'poem' and target_name_to_retry:
            logger.info(f"Вызов generate_poem для /retry для имени '{target_name_to_retry}'...")
            # Передаем имя через фейковый update - самый простой способ не менять generate_poem сильно
            fake_text = f"/poem {target_name_to_retry}"
            fake_msg = {'message_id': 1, 'date': int(datetime.datetime.now(datetime.timezone.utc).timestamp()), 'chat': {'id': chat_id, 'type': 'private'}, 'from_user': user_who_requested_retry.to_dict(), 'text': fake_text}
            fake_upd = Update.de_json({'update_id': 1, 'message': fake_msg}, context.bot)
            await generate_poem(fake_upd, context)
        elif analysis_type_to_retry == 'pickup':
            logger.info("Вызов get_pickup_line для /retry...")
            # Ему не нужны доп. данные, но нужен update для chat_id и user
            fake_msg = {'message_id': 1, 'date': int(datetime.datetime.now(datetime.timezone.utc).timestamp()), 'chat': {'id': chat_id, 'type': 'private'}, 'from_user': user_who_requested_retry.to_dict()}
            fake_upd = Update.de_json({'update_id': 1, 'message': fake_msg}, context.bot)
            await get_pickup_line(fake_upd, context)
        elif analysis_type_to_retry == 'roast' and target_name_to_retry and target_id_to_retry:
            logger.info(f"Вызов roast_user для /retry для '{target_name_to_retry}'...")
            # Передаем все напрямую
            await roast_user(update=None, context=context,
                             direct_chat_id=chat_id,
                             direct_user=user_who_requested_retry, # Кто ЗАКАЗАЛ повтор
                             # А вот target_user нам взять неоткуда без запроса к API или БД юзеров
                             # Поэтому передадим ЗАГЛУШКУ ДЛЯ ROAST RETRY
                             direct_gender_hint=gender_hint_to_retry or "неизвестен")
                             # Функция roast_user теперь должна уметь работать без target_user, если вызвано из retry
                             # Или мы пишем заглушку тут:
            await context.bot.send_message(chat_id=chat_id, text=f"🗿 Пережарка для **{target_name_to_retry}** пока не работает нормально. Хуй тебе.")
            # TODO: Реализовать нормальный retry для roast, если надо (например, убрать mention_html)

        # Добавь сюда elif для других типов анализа, если они появятся

        else:
            logger.error(f"Неизвестный/неполный тип анализа для /retry: {analysis_type_to_retry}")
            await context.bot.send_message(chat_id=chat_id, text="Хуй пойми, что я там делал. Не могу повторить.")
    except Exception as e:
         logger.error(f"Ошибка в /retry при вызове анализа ({analysis_type_to_retry}): {e}", exc_info=True)
         await context.bot.send_message(chat_id=chat_id, text=f"Обосрался при /retry: {type(e).__name__}")

# --- КОНЕЦ ПОЛНОЙ ФУНКЦИИ /retry ---

async def generate_poem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
         # --->>> НАЧАЛО НОВОЙ ПРОВЕРКИ ТЕХРАБОТ <<<---
# Проверяем наличие update и message - без них проверка невозможна
    if not update or not update.message or not update.message.from_user or not update.message.chat:
        logger.warning(f"Не могу проверить техработы - нет данных в update ({__name__})") # Логгируем имя текущей функции
        # Если это важная команда, можно тут вернуть ошибку пользователю
        # await context.bot.send_message(chat_id=update.effective_chat.id, text="Ошибка проверки данных.")
        return # Или просто выйти

    real_chat_id = update.message.chat.id
    real_user_id = update.message.from_user.id
    real_chat_type = update.message.chat.type

    loop = asyncio.get_running_loop()
    maintenance_active = await is_maintenance_mode(loop) # Вызываем функцию проверки

    # Блокируем, если техработы ВКЛЮЧЕНЫ и это НЕ админ в ЛС
    if maintenance_active and (real_user_id != ADMIN_USER_ID or real_chat_type != 'private'):
        logger.info(f"Команда отклонена из-за режима техработ в чате {real_chat_id}")
        try: # Пытаемся ответить и удалить команду
            await context.bot.send_message(chat_id=real_chat_id, text="🔧 Сорян, у меня сейчас технические работы. Попробуй позже.")
            await context.bot.delete_message(chat_id=real_chat_id, message_id=update.message.message_id)
        except Exception as e:
            logger.warning(f"Не удалось ответить/удалить сообщение о техработах: {e}")
        return # ВЫХОДИМ ИЗ ФУНКЦИИ
# --->>> КОНЕЦ НОВОЙ ПРОВЕРКИ ТЕХРАБОТ <<<---
    """Генерирует саркастичный стишок про указанное имя."""
    # --->>> ЗАМЕНЯЕМ КОММЕНТАРИЙ НА РЕАЛЬНЫЙ КОД <<<---
    chat_id = None
    user = None
    target_name = None
    user_name = "Поэт хуев" # Дефолтное имя запросившего

    # Определяем chat_id и user из update (должен быть всегда, т.к. это обработчик)
    if update and update.message:
        chat_id = update.message.chat_id
        user = update.message.from_user
        if user:
            user_name = user.first_name or user_name # Обновляем имя запросившего, если есть

        # Определяем target_name из команды или текста
        if update.message.text:
            if update.message.text.startswith('/poem'):
                command_parts = update.message.text.split(maxsplit=1)
                if len(command_parts) >= 2 and command_parts[1].strip():
                    target_name = command_parts[1].strip()
            else: # Если не команда /poem, ищем в тексте
                match = re.search(r'(?i).*(?:стих|стишок|поэма)\s+(?:про|для|об)\s+([А-Яа-яЁё\s\-]+)', update.message.text)
                if match:
                    target_name = match.group(1).strip()

    # Проверяем, смогли ли мы получить нужные данные
    if not chat_id or not user:
        logger.error("Не удалось определить chat_id или user в generate_poem.")
        # Пытаемся ответить хоть куда-то, если есть ID
        err_chat_id = update.effective_chat.id if update and update.effective_chat else None
        if err_chat_id: await context.bot.send_message(chat_id=err_chat_id, text="Внутренняя ошибка получения данных.")
        return

    if not target_name:
        await context.bot.send_message(chat_id=chat_id, text="Не понял, про кого стих писать. `/poem Имя` или 'Бот стих про Имя'.")
        return

    if len(target_name) > 50:
        await context.bot.send_message(chat_id=chat_id, text="Слишком длинное имя.")
        return
    # --->>> КОНЕЦ РЕАЛЬНОГО КОДА ПОЛУЧЕНИЯ ПЕРЕМЕННЫХ <<<---

    logger.info(f"Пользователь '{user_name}' запросил стих про '{target_name}' в чате {chat_id}")
    poem_prompt = (
        f"Ты - пиздец какой циничный и злой поэт-матершинник. Твоя задача - НАПИСАТЬ КОРОТКИЙ (4-8 строк), смешной, саркастичный и ОБИДНЫЙ стишок про человека по имени **{target_name}**. "
        f"Используй черный юмор, мат, высмеивай стереотипы или просто придумывай нелепые ситуации с этим именем. Сделай так, чтобы было одновременно смешно и пиздец как токсично. Не бойся жести.\n\n"
        f"ВАЖНО: Стишок должен быть именно про имя '{target_name}'. НЕ пиши никаких вступлений или заключений. Только сам стих.\n\n"
        f"ВАЖНО: Стихотворение должно быть в рифму!\n"
        f"Пример (для Стаса):\n"
        f"Наш Стасик - парень неплохой,\n"
        f"Но вечно с кислой ебалой.\n"
        f"Он думает, что он философ,\n"
        f"А сам - как хуй что перед носом.\n\n"
        f"Пример (для Насти):\n"
        f"Ах, Настя, Настя, где твой мозг?\n"
        f"В башке лишь ветер, да навоз.\n"
        f"Мечтает Настя о Мальдивах,\n"
        f"Пока сосет хуй в перерывах.\n\n"
        f"Напиши ПОДОБНЫЙ стишок про **{target_name}**:"
    )
    try:
        thinking_message = await context.bot.send_message(chat_id=chat_id, text=f"Так, блядь, ща рифму подберу для '{target_name}'...")
        poem_text = await _call_ionet_api([{"role": "user", "content": poem_prompt}], IONET_TEXT_MODEL_ID, 150, 0.9) or f"[Стих про {target_name} не родился]"
        if not poem_text.startswith("🗿") and not poem_text.startswith("["): poem_text = "🗿 " + poem_text
        try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass
        MAX_MESSAGE_LENGTH = 4096; # Обрезка
        if len(poem_text) > MAX_MESSAGE_LENGTH: poem_text = poem_text[:MAX_MESSAGE_LENGTH - 3] + "..."
        sent_message = await context.bot.send_message(chat_id=chat_id, text=poem_text)
        logger.info(f"Отправлен стих про {target_name}.")
        if sent_message: # Запись для /retry
            reply_doc = { "chat_id": chat_id, "message_id": sent_message.message_id, "analysis_type": "poem", "target_name": target_name, "timestamp": datetime.datetime.now(datetime.timezone.utc) }
            try: loop = asyncio.get_running_loop(); await loop.run_in_executor(None, lambda: last_reply_collection.update_one({"chat_id": chat_id}, {"$set": reply_doc}, upsert=True))
            except Exception as e: logger.error(f"Ошибка записи /retry (poem) в MongoDB: {e}")
    except Exception as e: logger.error(f"ПИЗДЕЦ при генерации стиха про {target_name}: {e}", exc_info=True); await context.bot.send_message(chat_id=chat_id, text=f"Бля, {user_name}, не могу сочинить про '{target_name}'. Ошибка: `{type(e).__name__}`.")

async def get_prediction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
         # --->>> НАЧАЛО НОВОЙ ПРОВЕРКИ ТЕХРАБОТ <<<---
# Проверяем наличие update и message - без них проверка невозможна
    if not update or not update.message or not update.message.from_user or not update.message.chat:
        logger.warning(f"Не могу проверить техработы - нет данных в update ({__name__})") # Логгируем имя текущей функции
        # Если это важная команда, можно тут вернуть ошибку пользователю
        # await context.bot.send_message(chat_id=update.effective_chat.id, text="Ошибка проверки данных.")
        return # Или просто выйти

    real_chat_id = update.message.chat.id
    real_user_id = update.message.from_user.id
    real_chat_type = update.message.chat.type

    loop = asyncio.get_running_loop()
    maintenance_active = await is_maintenance_mode(loop) # Вызываем функцию проверки

    # Блокируем, если техработы ВКЛЮЧЕНЫ и это НЕ админ в ЛС
    if maintenance_active and (real_user_id != ADMIN_USER_ID or real_chat_type != 'private'):
        logger.info(f"Команда отклонена из-за режима техработ в чате {real_chat_id}")
        try: # Пытаемся ответить и удалить команду
            await context.bot.send_message(chat_id=real_chat_id, text="🔧 Сорян, у меня сейчас технические работы. Попробуй позже.")
            await context.bot.delete_message(chat_id=real_chat_id, message_id=update.message.message_id)
        except Exception as e:
            logger.warning(f"Не удалось ответить/удалить сообщение о техработах: {e}")
        return # ВЫХОДИМ ИЗ ФУНКЦИИ
# --->>> КОНЕЦ НОВОЙ ПРОВЕРКИ ТЕХРАБОТ <<<---
    if not update.message or not update.message.from_user: return
    chat_id = update.message.chat_id; user = update.message.from_user; user_name = user.first_name or "Любопытная Варвара"
    logger.info(f"Пользователь '{user_name}' запросил предсказание в чате {chat_id}")
    is_positive = random.random() < 0.01; prediction_prompt = ""; final_prefix = "🗿 "; thinking_text = f"🗿 Так, {user_name}, ща посмотрю в шар..."
    if is_positive: final_prefix = "✨ "; thinking_text = f"✨ Так, {user_name}, ща че-нить хорошее скажу..."; prediction_prompt = (f"Ты - внезапно подобревший... Выдай ОДНО ДОБРОЕ предсказание для {user_name}:")
    else: prediction_prompt = (
        f"Ты - ехидный и циничный оракул с черным юмором. Тебя попросили сделать предсказание для пользователя по имени {user_name}. "
        f"Придумай ОДНО КОРОТКОЕ (1-2 предложения), максимально саркастичное, матерное, обескураживающее или просто абсурдное предсказание на сегодня/ближайшее будущее. "
        f"Сделай его неожиданным и злым. Используй мат для усиления эффекта. Не пиши банальностей и позитива. НЕ ПИШИ никаких вступлений типа 'Я предсказываю...' или 'Для {user_name}...'. СРАЗУ выдавай само предсказание.\n\n"
        f"Примеры:\n"
        f"- Похоже, сегодня твой максимум - дойти до холодильника и обратно. Не перенапрягись, герой.\n"
        f"- Вселенная приготовила тебе сюрприз... пиздюлей, скорее всего.\n"
        f"- Звезды сошлись так, что тебе лучше бы сидеть тихо и не отсвечивать, а то прилетит.\n"
        f"- Твоя финансовая удача сегодня выглядит как дырка от бублика. Зато стабильно, блядь.\n"
        f"- Жди встречи со старым другом... который потребует вернуть долг.\n\n"
        f"Выдай ОДНО такое предсказание для {user_name}:"
    )
    try:
        thinking_message = await context.bot.send_message(chat_id=chat_id, text=thinking_text)
        messages_for_api = [{"role": "user", "content": prediction_prompt}]
        prediction_text = await _call_ionet_api(messages_for_api, IONET_TEXT_MODEL_ID, 100, (0.6 if is_positive else 0.9)) or "[Предсказание потерялось]"
        if not prediction_text.startswith(("🗿", "✨", "[")): prediction_text = final_prefix + prediction_text
        try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass
        MAX_MESSAGE_LENGTH = 4096;
        if len(prediction_text) > MAX_MESSAGE_LENGTH: prediction_text = prediction_text[:MAX_MESSAGE_LENGTH - 3] + "..."
        await context.bot.send_message(chat_id=chat_id, text=prediction_text)
        logger.info(f"Отправлено предсказание для {user_name}.")
        # Запись для /retry не делаем для предсказаний, т.к. оно рандомное
    except Exception as e: logger.error(f"ПИЗДЕЦ при генерации предсказания для {user_name}: {e}", exc_info=True); await context.bot.send_message(chat_id=chat_id, text=f"Бля, {user_name}, мой шар треснул. Ошибка: `{type(e).__name__}`.")

# --- ПЕРЕДЕЛАННАЯ get_pickup_line (С КОНТЕКСТОМ И ОТВЕТОМ НА СООБЩЕНИЕ) ---
async def get_pickup_line(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Генерирует кринжовый подкат к пользователю, на сообщение которого ответили, с учетом контекста."""

    # 1. Проверка техработ (ОБЯЗАТЕЛЬНО!)
    if not update or not update.message or not update.message.from_user or not update.message.chat:
         logger.warning("get_pickup_line: нет данных для проверки техработ")
         return
    real_chat_id = update.message.chat.id; real_user_id = update.message.from_user.id; real_chat_type = update.message.chat.type
    try: admin_id = int(os.getenv("ADMIN_USER_ID", "0"))
    except ValueError: admin_id = 0
    if admin_id == 0: logger.warning("ADMIN_USER_ID не задан!")
    loop = asyncio.get_running_loop(); maintenance_active = await is_maintenance_mode(loop)
    if maintenance_active and (real_user_id != admin_id or real_chat_type != 'private'):
        logger.info(f"Команда pickup отклонена из-за техработ в чате {real_chat_id}")
        try: await context.bot.send_message(chat_id=real_chat_id, text="🔧 Техработы. Не до подкатов сейчас.")
        except Exception: pass
        # Удалим команду, если можем
        try: await context.bot.delete_message(chat_id=real_chat_id, message_id=update.message.message_id)
        except Exception: pass
        return

    # 2. Проверка, что это ответ на сообщение и не на бота
    if (not update.message.reply_to_message or
            not update.message.reply_to_message.from_user or
            update.message.reply_to_message.from_user.id == context.bot.id):
        await context.bot.send_message(chat_id=chat_id, text="Ответь этой командой на сообщение того/той, к кому хочешь подкатить (но не ко мне!).")
        return

    # 3. Собираем инфу
    target_user = update.message.reply_to_message.from_user # К кому катим
    target_name = target_user.first_name or target_user.username or "прекрасная незнакомка/незнакомец"
    chat_id = update.message.chat.id
    user = update.message.from_user # Кто катит
    user_name = user.first_name or "Пикап-мастер"

    logger.info(f"Пользователь '{user_name}' запросил подкат к '{target_name}' (ID: {target_user.id}). Ищем контекст...")

    # 4. Читаем контекст цели из БД (как в roast_user)
    user_context = "[Недавно ничего не писал(а)]"
    USER_CONTEXT_LIMIT_PICKUP = 3 # Достаточно пары последних фраз
    try:
        query = {"chat_id": chat_id, "user_id": target_user.id}
        sort_order = [("timestamp", pymongo.DESCENDING)]
        user_hist_cursor = await loop.run_in_executor(None, lambda: history_collection.find(query).sort(sort_order).limit(USER_CONTEXT_LIMIT_PICKUP))
        user_messages = list(user_hist_cursor)[::-1]
        if user_messages:
            context_lines = [msg.get('text', '[...]') for msg in user_messages]
            user_context = "\n".join(context_lines)
            logger.info(f"Найден контекст ({len(user_messages)} сообщ.) для {target_name}.")
        else: logger.info(f"Контекст для {target_name} не найден.")
    except Exception as db_e: logger.error(f"Ошибка чтения контекста для подката из MongoDB: {db_e}")

    # 5. Формируем промпт для Gemini/io.net
    logger.info(f"Генерация подката к '{target_name}' с учетом контекста...")

    # --->>> НОВЫЙ ПРОМПТ ДЛЯ КОНТЕКСТНОГО ПОДКАТА <<<---
    pickup_prompt = (
        f"Ты - Попиздяка, бот с ОЧЕНЬ СПЕЦИФИЧЕСКИМ чувством юмора, немного пошлый и саркастичный. Тебе нужно придумать **ОДНУ КОРОТКУЮ (1-2 предложения) фразу для ПОДКАТА (pickup line)** к пользователю по имени **{target_name}**. "
        f"Вот последние несколько сообщений этого пользователя (если есть):\n"
        f"```\n{user_context}\n```\n"
        f"Твоя задача: Придумай подкат, который будет **СМЕШНО или НЕОЖИДАННО обыгрывать что-то из его/ее НЕДАВНИХ СООБЩЕНИЙ** (если они есть и информативны) ИЛИ просто его/ее **ИМЯ**. Подкат должен быть **КРИНЖОВЫМ, НЕУКЛЮЖИМ, САРКАСТИЧНЫМ или ЧУТЬ ПОШЛЫМ**, но НЕ откровенно оскорбительным (ты пытаешься типа 'подкатить', а не прожарить). Используй немного мата для стиля. Начинай ответ с `🗿 `.\n\n"
        f"Пример (Контекст: 'Обожаю пиццу'; Имя: Лена): '🗿 Лена, ты такая же горячая и желанная, как последний кусок пиццы... только от тебя жопа не слипнется (наверное).'\n"
        f"Пример (Контекст: 'Устал как собака'; Имя: Макс): '🗿 Макс, вижу ты устал... Может, приляжешь? Желательно на меня. 😉 (Блядь, хуйню сморозил, прости)'\n"
        f"Пример (Контекста нет; Имя: Оля): '🗿 Оля, у тебя красивое имя. Почти такое же красивое, как мои намерения затащить тебя в постель (или хотя бы в канаву).'\n\n"
        f"Придумай ОДИН такой КРИНЖОВЫЙ подкат для **{target_name}**, по возможности используя контекст:"
    )
    # --->>> КОНЕЦ НОВОГО ПРОМПТА <<<---

    try:
        thinking_message = await context.bot.send_message(chat_id=chat_id, text=f"🗿 Подбираю ключи к сердцу (или ширинке) '{target_name}'...")
        messages_for_api = [{"role": "user", "content": pickup_prompt}]
        # Вызов ИИ (_call_ionet_api или model.generate_content_async)
        pickup_line_text = await _call_ionet_api( # ИЛИ model.generate_content_async
            messages=messages_for_api, model_id=IONET_TEXT_MODEL_ID, max_tokens=100, temperature=1.0 # Высокая температура для креатива
        ) or f"[Подкат к {target_name} провалился]"
        if not pickup_line_text.startswith(("🗿", "[")): pickup_line_text = "🗿 " + pickup_line_text
        try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass

        MAX_MESSAGE_LENGTH = 4096; # Обрезка
        if len(pickup_line_text) > MAX_MESSAGE_LENGTH: pickup_line_text = pickup_line_text[:MAX_MESSAGE_LENGTH - 3] + "..."

        # Отправляем подкат (НЕ как ответ, а просто в чат, упоминая цель)
        target_mention = target_user.mention_html() if target_user.username else f"<b>{target_name}</b>"
        final_text = f"Подкат для {target_mention} от {user.mention_html()}:\n\n{pickup_line_text}"
        await context.bot.send_message(chat_id=chat_id, text=final_text, parse_mode='HTML')
        logger.info(f"Отправлен подкат к {target_name}.")
        # Запись для /retry (если нужна, с type='pickup', target_id, target_name)
        # ...

    except Exception as e:
        logger.error(f"ПИЗДЕЦ при генерации подката к {target_name}: {e}", exc_info=True)
        try:
            if 'thinking_message' in locals(): await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass
        await context.bot.send_message(chat_id=chat_id, text=f"Бля, {user_name}, не смог подкатить к '{target_name}'. Видимо, он(а) слишком хорош(а) для такого говна, как я. Ошибка: `{type(e).__name__}`.")

# --- КОНЕЦ ПЕРЕДЕЛАННОЙ get_pickup_line ---


# --- ПЕРЕПИСАННАЯ roast_user (С КОНТЕКСТОМ ИЗ БД) ---
async def roast_user(update: Update | None, context: ContextTypes.DEFAULT_TYPE, direct_chat_id: int | None = None, direct_user: User | None = None, direct_gender_hint: str | None = None) -> None:
    # --->>> НАЧАЛО НОВОЙ ПРОВЕРКИ ТЕХРАБОТ <<<---
# Проверяем наличие update и message - без них проверка невозможна
    if not update or not update.message or not update.message.from_user or not update.message.chat:
        logger.warning(f"Не могу проверить техработы - нет данных в update ({__name__})") # Логгируем имя текущей функции
        # Если это важная команда, можно тут вернуть ошибку пользователю
        # await context.bot.send_message(chat_id=update.effective_chat.id, text="Ошибка проверки данных.")
        return # Или просто выйти

    real_chat_id = update.message.chat.id
    real_user_id = update.message.from_user.id
    real_chat_type = update.message.chat.type

    loop = asyncio.get_running_loop()
    maintenance_active = await is_maintenance_mode(loop) # Вызываем функцию проверки

    # Блокируем, если техработы ВКЛЮЧЕНЫ и это НЕ админ в ЛС
    if maintenance_active and (real_user_id != ADMIN_USER_ID or real_chat_type != 'private'):
        logger.info(f"Команда отклонена из-за режима техработ в чате {real_chat_id}")
        try: # Пытаемся ответить и удалить команду
            await context.bot.send_message(chat_id=real_chat_id, text="🔧 Сорян, у меня сейчас технические работы. Попробуй позже.")
            await context.bot.delete_message(chat_id=real_chat_id, message_id=update.message.message_id)
        except Exception as e:
            logger.warning(f"Не удалось ответить/удалить сообщение о техработах: {e}")
        return # ВЫХОДИМ ИЗ ФУНКЦИИ
# --->>> КОНЕЦ НОВОЙ ПРОВЕРКИ ТЕХРАБОТ <<<---
    target_user = None; target_name = "это хуйло"; gender_hint = "неизвестен"; chat_id = None; user = None; user_name = "Заказчик"
    is_retry = False # Пока не трогаем retry для roast

    # Определяем chat_id, user (кто заказал), target_user (кого жарим)
    if direct_chat_id and direct_user: # Вызов из /roastme (жарим себя)
        chat_id = direct_chat_id; user = direct_user; target_user = user # Жарить будем себя
        user_name = user.first_name or user_name; target_name = target_user.first_name or target_user.username or target_name
    elif update and update.message and update.message.reply_to_message and update.message.reply_to_message.from_user: # Обычный вызов /roast
        chat_id = update.message.chat_id; user = update.message.from_user; target_user = update.message.reply_to_message.from_user
        user_name = user.first_name or user_name; target_name = target_user.first_name or target_user.username or target_name
        # Угадываем пол
        if update.message.text:
            user_command_text = update.message.text.lower()
            if "его" in user_command_text or "этого" in user_command_text: gender_hint = "мужской"
            elif "ее" in user_command_text or "эё" in user_command_text or "эту" in user_command_text: gender_hint = "женский"
    else: logger.error("roast_user вызвана некорректно!"); return

    if target_user.id == context.bot.id: await context.bot.send_message(chat_id=chat_id, text="🗿 Себя жарить не буду."); return

    logger.info(f"Пользователь '{user_name}' запросил прожарку для '{target_name}' (ID: {target_user.id}). Ищем контекст...")

    # --- ЧТЕНИЕ КОНТЕКСТА (ПОСЛЕДНИХ СООБЩЕНИЙ ЦЕЛИ) ИЗ БД ---
    user_context = "[Недавних сообщений не найдено]"
    USER_CONTEXT_LIMIT = 20 # Сколько последних сообщений цели брать
    try:
        loop = asyncio.get_running_loop()
        # Ищем сообщения ИМЕННО ЭТОГО ЮЗЕРА (target_user.id) в ЭТОМ ЧАТЕ
        query = {"chat_id": chat_id, "user_id": target_user.id}
        sort_order = [("timestamp", pymongo.DESCENDING)]
        user_hist_cursor = await loop.run_in_executor(
            None, lambda: history_collection.find(query).sort(sort_order).limit(USER_CONTEXT_LIMIT)
        )
        user_messages = list(user_hist_cursor)[::-1] # Переворачиваем для хронологии
        if user_messages:
            # Формируем контекст как текст
            context_lines = [msg.get('text', '[пустое сообщение]') for msg in user_messages]
            user_context = "\n".join(context_lines)
            logger.info(f"Найден контекст ({len(user_messages)} сообщ.) для {target_name}.")
        else:
             logger.info(f"Контекст для {target_name} не найден.")

    except Exception as db_e:
        logger.error(f"Ошибка чтения контекста для роаста из MongoDB: {db_e}")
        # Продолжим без контекста
    # --- КОНЕЦ ЧТЕНИЯ КОНТЕКСТА ---

    logger.info(f"Генерация роаста для '{target_name}' с учетом контекста (или без)...")

    # --->>> НОВЫЙ ПРОМПТ ДЛЯ РОАСТА С КОНТЕКСТОМ <<<---
    roast_prompt = (
            f"Ты - Попиздяка, гений черного юмора, сарказма и стендапа в жанре 'roast'. Твоя задача - **УНИЧТОЖИТЬ** человека по имени **{target_name}** (пол: {gender_hint}, если известен, иначе 'неизвестен') своим остроумием. Тебе предоставлены его/ее ПОСЛЕДНИЕ НЕСКОЛЬКО СООБЩЕНИЙ (контекст).\n\n"
            f"Контекст от {target_name}:\n"
            f"```\n{user_context}\n```\n\n"
            f"Инструкции для разъеба:\n"
            f"1.  **ВНИМАТЕЛЬНО ПРОЧИТАЙ КОНТЕКСТ.** Ищи там тупые высказывания, смешные опечатки, банальности, противоречия, высокомерие, нытье, странные интересы или просто что-то, за что можно зацепиться и обстебать.\n"
            f"2.  Если в контексте есть что-то интересное, **ПОСТРОЙ СВОЙ РОАСТ ВОКРУГ ЭТОГО**. Процитируй (можно неточно) или перескажи его/ее мысль и потом разъеби ее своим сарказмом и матом.\n"
            f"3.  Если контекст пустой или абсолютно неинтересный (например, одни стикеры или 'привет как дела'), ТОГДА **ПРИДУМАЙ РОАСТ ПРОСТО НА ОСНОВЕ ИМЕНИ `{target_name}`** и, возможно, подсказки о поле. Можешь пофантазировать о его/ее тупости, никчемности, странных привычках и т.д.\n"
            f"4.  Роаст должен быть **КОРОТКИМ (2-4 предложения)**, МАКСИМАЛЬНО ЕДКИМ, СМЕШНЫМ и с ИЗОБРЕТАТЕЛЬНЫМ МАТОМ.\n"
            f"5.  Цель - чтобы все поржали, а объект роаста пошел плакать в подушку (но втайне восхитился твоим остроумием).\n"
            f"6.  Начинай свой ответ с `🗿 `.\n\n"
            f"Пример (Контекст от Васи: 'Я считаю, что Земля плоская!'; Имя: Вася):\n"
            f"🗿 Васян тут заявил, что Земля плоская. Блядь, Вася, ты когда эту хуйню придумал, у тебя что, шапочка из фольги на глаза сползла? Такой интеллект даже для амебы - позор.\n\n"
            f"Пример (Контекст от Лены: 'Купила новые туфли, смотрите!'; Имя: Лена):\n"
            f"🗿 Лена хвастается новыми туфлями. Охуеть достижение. Лен, ты бы лучше мозги себе купила, а то туфли есть, а ходить в них, похоже, скоро будет некуда, кроме как на панель.\n\n"
            f"Пример (Контекста нет или он тупой; Имя: Дима):\n"
            f"🗿 А вот и Димасик! Говорят, его единственное достижение в жизни - это то, что он до сих пор не разучился дышать самостоятельно. Хотя, судя по его ебалу, это ему дается с трудом.\n\n"
            f"Сочини свой УНИЧТОЖАЮЩИЙ роаст для **{target_name}**, используя контекст или имя:"
        )
    # --->>> КОНЕЦ НОВОГО ПРОМПТА <<<---

    try:
        thinking_message = await context.bot.send_message(chat_id=chat_id, text=f"🗿 Изучаю под микроскопом высеры '{target_name}'... Ща будет прожарка.")
        messages_for_api = [{"role": "user", "content": roast_prompt}]
        # Используем твой вызов ИИ (_call_ionet_api или model.generate_content_async)
        roast_text = await _call_ionet_api( # ИЛИ model.generate_content_async
            messages=messages_for_api, model_id=IONET_TEXT_MODEL_ID, max_tokens=200, temperature=0.85
        ) or f"[Роаст для {target_name} не удался]"
        if not roast_text.startswith(("🗿", "[")): roast_text = "🗿 " + roast_text
        try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass

        # Отправка и запись для /retry (оставляем ЗАГЛУШКУ для retry)
        target_mention = f"<b>{target_name}</b>" # НЕ делаем mention_html, т.к. target_user может быть не тот в retry
        final_text = f"Прожарка для {target_mention}:\n\n{roast_text}"
        MAX_MESSAGE_LENGTH = 4096 # Обрезка
        if len(final_text) > MAX_MESSAGE_LENGTH: final_text = final_text[:MAX_MESSAGE_LENGTH-3] + "..." # Упрощенная обрезка
        sent_message = await context.bot.send_message(chat_id=chat_id, text=final_text, parse_mode='HTML')
        logger.info(f"Отправлен роаст для {target_name}.")
        if sent_message: # Запись для /retry (теперь с target_id и gender_hint!)
             reply_doc = { "chat_id": chat_id, "message_id": sent_message.message_id, "analysis_type": "roast", "target_name": target_name, "target_id": target_user.id, "gender_hint": gender_hint, "timestamp": datetime.datetime.now(datetime.timezone.utc) }
             try: loop = asyncio.get_running_loop(); await loop.run_in_executor(None, lambda: last_reply_collection.update_one({"chat_id": chat_id}, {"$set": reply_doc}, upsert=True))
             except Exception as e: logger.error(f"Ошибка записи /retry (roast) в MongoDB: {e}")

    except Exception as e:
        logger.error(f"ПИЗДЕЦ при генерации роаста для {target_name}: {e}", exc_info=True)
        try:
            if 'thinking_message' in locals(): await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass
        await context.bot.send_message(chat_id=chat_id, text=f"Бля, {user_name}, не смог прожарить '{target_name}'. Ошибка: `{type(e).__name__}`.")

# --- КОНЕЦ ПЕРЕПИСАННОЙ roast_user ---

import random # Убедись, что импортирован
import asyncio # Убедись, что импортирован
# Убедись, что logger, chat_activity_collection, _call_ionet_api, IONET_TEXT_MODEL_ID определены ВЫШЕ

# --- ПРАВИЛЬНАЯ reply_to_bot_handler (С ДЕТЕКТОРОМ СПАМА/БАЙТА и вызовом ai.io.net) ---
# --- ФИНАЛЬНАЯ reply_to_bot_handler (КОНТЕКСТ + СПАМ + ТЕХРАБОТЫ + AI.IO.NET) ---
async def reply_to_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Анализирует ответ на сообщение бота с учетом контекста юзера, детектит спам, отвечает через ИИ."""

    # --->>> 1. ПРОВЕРКА ТЕХРАБОТ (В САМОМ НАЧАЛЕ!) <<<---
    if not update or not update.message or not update.message.from_user or not update.message.chat:
         logger.warning("reply_to_bot_handler: нет данных в update для проверки техработ")
         return
    real_chat_id = update.message.chat.id; real_user_id = update.message.from_user.id; real_chat_type = update.message.chat.type
    try: admin_id = int(os.getenv("ADMIN_USER_ID", "0"))
    except ValueError: admin_id = 0
    if admin_id == 0: logger.warning("ADMIN_USER_ID не задан!")
    loop = asyncio.get_running_loop()
    maintenance_active = await is_maintenance_mode(loop)
    if maintenance_active and (real_user_id != admin_id or real_chat_type != 'private'):
        logger.info(f"reply_to_bot_handler отклонен из-за техработ в чате {real_chat_id}")
        # Тихо выходим, не отвечаем на ответ во время техработ (кроме админа в ЛС)
        return
    # --->>> КОНЕЦ ПРОВЕРКИ ТЕХРАБОТ <<<---

    # 2. Базовые проверки сообщения (ответ боту, есть текст, не команда и т.д.)
    if (not update.message.reply_to_message or not update.message.reply_to_message.from_user or
            update.message.reply_to_message.from_user.id != context.bot.id or not update.message.text or
            update.message.text.startswith('/') or len(update.message.text) > 500): # Оставим лимит 500
        return

    # 3. Собираем инфу
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    user_text_input = update.message.text.strip()
    user_name = update.message.from_user.first_name or "Умник Дохуя"
    bot_original_message_text = update.message.reply_to_message.text or "[мой старый высер]"
    bot_original_short = bot_original_message_text[:150] + ('...' if len(bot_original_message_text) > 150 else '')
    user_text_short = user_text_input[:150] + ('...' if len(user_text_input) > 150 else '')

    logger.info(f"Пользователь {user_name} ({user_id}) ответил ('{user_text_short}...') на сообщение бота в чате {chat_id}.")

    # 4. Детектор спама/байта (читаем прошлый ответ, проверяем, обновляем текущий)
    last_user_reply = None
    is_spam = False
    try:
        activity_doc = await loop.run_in_executor(None, lambda: chat_activity_collection.find_one({"chat_id": chat_id}))
        if activity_doc and "last_user_replies" in activity_doc and str(user_id) in activity_doc["last_user_replies"]:
             last_user_reply = activity_doc["last_user_replies"][str(user_id)]
        if last_user_reply and len(user_text_input.split()) <= 2 and user_text_input.lower() == last_user_reply.lower():
            is_spam = True; logger.info(f"Обнаружен спам/байт от {user_name}.")
        # Обновляем В ЛЮБОМ СЛУЧАЕ
        update_field = f"last_user_replies.{user_id}"; await loop.run_in_executor( None, lambda: chat_activity_collection.update_one( {"chat_id": chat_id}, {"$set": {update_field: user_text_input}}, upsert=True ) )
        logger.debug(f"Обновлен последний ответ для user {user_id} в чате {chat_id}")
    except Exception as e: logger.error(f"Ошибка MongoDB в spam check для чата {chat_id}: {e}")

    # Если спам - отвечаем коротко и выходим
    if is_spam:
        comeback_text = random.choice(["🗿 Ок.", "🗿 И чо?", "🗿 Заебал.", "🗿 Сам такой."])
        try: await update.message.reply_text(text=comeback_text); logger.info(f"Отправлен короткий ответ на спам.")
        except Exception as e: logger.error(f"Ошибка при отправке ответа на спам: {e}")
        return

    # --- 5. ЕСЛИ НЕ СПАМ - ПОЛУЧАЕМ КОНТЕКСТ ЮЗЕРА ИЗ БД ---
    user_context = "[Не найдено недавних сообщений этого пользователя]"
    USER_CONTEXT_LIMIT_REPLY = 5 # Сколько последних сообщений юзера брать
    try:
        query = {"chat_id": chat_id, "user_id": user_id} # Ищем по юзеру и чату
        sort_order = [("timestamp", pymongo.DESCENDING)]
        user_hist_cursor = await loop.run_in_executor(
            None, lambda: history_collection.find(query).sort(sort_order).limit(USER_CONTEXT_LIMIT_REPLY)
        )
        user_messages = list(user_hist_cursor)[::-1] # Переворачиваем
        if user_messages:
            context_lines = [f"- {msg.get('text', '[пусто]')}" for msg in user_messages] # Форматируем контекст
            user_context = "\n".join(context_lines)
            logger.info(f"Найден контекст ({len(user_messages)} сообщ.) для {user_name}.")
        else:
             logger.info(f"Контекст для {user_name} не найден.")
    except Exception as db_e:
        logger.error(f"Ошибка чтения контекста юзера из MongoDB: {db_e}")
    # --- КОНЕЦ ПОЛУЧЕНИЯ КОНТЕКСТА ---


    # --- 6. Генерируем "умный" ответ через ai.io.net С УЧЕТОМ КОНТЕКСТА ---
    logger.info(f"Генерируем КОНТЕКСТНЫЙ ответ на ответ боту...")

    # --->>> НОВЫЙ ПРОМПТ С КОНТЕКСТОМ <<<---
    comeback_prompt = (
        f"Ты - Попиздяка, саркастичный и матерный телеграм-бот. Пользователь '{user_name}' только что ответил на твое сообщение «{bot_original_short}» своей фразой: «{user_text_input}».\n"
        f"Вот что этот пользователь писал В ЭТОМ ЧАТЕ незадолго до этого (для контекста):\n"
        f"```\n{user_context}\n```\n\n"
        f"Твоя задача:\n"
        f"1.  Проанализируй фразу пользователя «{user_text_input}» С УЧЕТОМ контекста его предыдущих сообщений.\n"
        f"2.  Определи намерение: это наезд/тупость ИЛИ осмысленный запрос/вопрос?\n"
        f"3.  Если наезд/тупость: Придумай КОРОТКОЕ дерзкое ОГРЫЗАНИЕ, возможно, ССЫЛАЯСЬ на его предыдущие сообщения из контекста для усиления стеба.\n"
        f"4.  Если запрос: Попробуй ВЫПОЛНИТЬ его (или саркастично ОТКАЖИ), также можешь тонко СЪЯЗВИТЬ, используя контекст его прошлых сообщений.\n"
        f"5.  Ответ должен быть КОРОТКИМ (1-3 предложения). Начинай с `🗿 `.\n\n"
        f"Пример (Контекст: 'Как же заебала работа'; Ответ юзера: 'бот тупой'): '🗿 Тебя работа заебала, а виноват я? Иди проспись, работяга хуев.'\n"
        f"Пример (Контекст: 'Хочу в отпуск'; Ответ юзера: 'расскажи анекдот'): '🗿 Тебе анекдот или билет нахуй с этой работы? Могу только первое, но он будет про таких же неудачников, как ты.'\n\n"
        f"Твой КОНТЕКСТНО-ЗАВИСИМЫЙ ответ на фразу «{user_text_input}» (начиная с 🗿):"
    )
    # --->>> КОНЕЦ НОВОГО ПРОМПТА <<<---

    try:
        await asyncio.sleep(random.uniform(0.5, 1.5))
        messages_for_api = [{"role": "user", "content": comeback_prompt}]
        # Вызов _call_ionet_api (или аналога Gemini)
        response_text = await _call_ionet_api(
            messages=messages_for_api, model_id=IONET_TEXT_MODEL_ID, max_tokens=200, temperature=0.8
        ) or f"[Не смог обработать твой ответ, {user_name}]"

        if not response_text.startswith(("🗿", "[")): response_text = "🗿 " + response_text
        MAX_MESSAGE_LENGTH = 4096;
        if len(response_text) > MAX_MESSAGE_LENGTH: response_text = response_text[:MAX_MESSAGE_LENGTH - 3] + "..."
        await update.message.reply_text(text=response_text)
        logger.info(f"Отправлен контекстный ответ на ответ боту в чате {chat_id}")

    except Exception as e:
        logger.error(f"ПИЗДЕЦ при генерации контекстного огрызания: {e}", exc_info=True)
        try: await update.message.reply_text("🗿 Ошибка. Мозги плавятся от вашего контекста.")
        except Exception: pass

# --- КОНЕЦ ФИНАЛЬНОЙ reply_to_bot_handler ---
# --- ПОЛНАЯ ФУНКЦИЯ ДЛЯ ФОНОВОЙ ЗАДАЧИ (ГЕНЕРАЦИЯ ФАКТОВ) ---

# --- ПОЛНАЯ ИСПРАВЛЕННАЯ ФУНКЦИЯ ДЛЯ ФОНОВОЙ ЗАДАЧИ (ГЕНЕРАЦИЯ ФАКТОВ) ---
async def check_inactivity_and_shitpost(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверяет неактивные чаты и постит рандомный ебанутый факт от ИИ."""
    logger.info("Запуск фоновой проверки неактивности чатов для постинга факта...")
    # Пороги времени в секундах
    INACTIVITY_THRESHOLD = 60 * 60 * 2 # 2 часа тишины
    MIN_TIME_BETWEEN_SHITPOSTS = 60 * 60 * 4 # Не чаще раза в 4 часа

    now = datetime.datetime.now(datetime.timezone.utc)
    inactive_threshold_time = now - datetime.timedelta(seconds=INACTIVITY_THRESHOLD)
    shitpost_threshold_time = now - datetime.timedelta(seconds=MIN_TIME_BETWEEN_SHITPOSTS)

    # --->>> ВЕСЬ КОД ДОЛЖЕН БЫТЬ ВНУТРИ ЭТОГО TRY <<<---
    try:
        loop = asyncio.get_running_loop()
        # Ищем чаты, где последнее сообщение было давно И последний высер бота был еще давнее
        query = {
            "last_message_time": {"$lt": inactive_threshold_time},
            "last_bot_shitpost_time": {"$lt": shitpost_threshold_time}
        }
        # Получаем список ID таких чатов
        inactive_chat_docs = await loop.run_in_executor(
            None,
            lambda: list(chat_activity_collection.find(query, {"chat_id": 1, "_id": 0}))
        )
        # --->>> ОПРЕДЕЛЯЕМ ПЕРЕМЕННУЮ ЗДЕСЬ <<<---
        inactive_chat_ids = [doc["chat_id"] for doc in inactive_chat_docs]

        # --->>> ПРОВЕРЯЕМ ПЕРЕМЕННУЮ ПОСЛЕ ОПРЕДЕЛЕНИЯ <<<---
        if not inactive_chat_ids:
            logger.info("Не найдено подходящих неактивных чатов для факта.")
            return # Выходим, если чатов нет

        logger.info(f"Найдены неактивные чаты ({len(inactive_chat_ids)}). Выбираем один для постинга факта...")
        target_chat_id = random.choice(inactive_chat_ids) # Берем один случайный чат

        # --->>> ГЕНЕРАЦИЯ ФАКТА ЧЕРЕЗ ИИ (Gemini или ai.io.net) <<<---
        fact_prompt = (
                "Придумай ОДИН короткий (1-2 предложения) совершенно ЕБАНУТЫЙ, АБСУРДНЫЙ, ЛЖИВЫЙ, но НАУКООБРАЗНЫЙ 'факт'. "
                "Он должен звучать максимально бредово, но подаваться с серьезным ебалом, как будто это реальное научное открытие или малоизвестная истина. Можно с матом или черным юмором для усиления эффекта.\n\n"
                "ВАЖНО: НЕ ПИШИ никаких вступлений типа 'Знаете ли вы...' или 'Интересный факт:'. СРАЗУ выдавай сам 'факт'. Будь креативным в своем бреде!\n\n"
                "Примеры такого пиздеца:\n"
                "- Квантовые флуктуации в жопе у хомяка могут спонтанно генерировать миниатюрные черные дыры, но хомяк этого обычно не замечает.\n"
                "- Среднестатистический человек во сне съедает до 8 пауков... и около 3 носков, но только если они достаточно грязные.\n"
                "- Пингвины тайно управляют мировым рынком анчоусов через подставные фирмы на Каймановых островах.\n"
                "- У жирафов на самом деле шея короткая, просто они очень сильно вытягивают ебало вверх от охуевания происходящим.\n"
                "- Если крикнуть 'Блядь!' в черную дыру, она может икнуть сингулярностью.\n"
                "- Кошки мурчат не от удовольствия, а заряжают свои внутренние лазеры для захвата мира.\n\n"
                "Придумай ПОДОБНЫЙ АБСУРДНЫЙ И ЛЖИВЫЙ 'факт':"
            )
        logger.info(f"Отправка запроса к ИИ для генерации ебанутого факта для чата {target_chat_id}...")

        # Используем твой текущий ИИ (замени _call_ionet_api на вызов Gemini, если ты на нем)
        # ВАЖНО: Убедись, что переменная IONET_TEXT_MODEL_ID определена, если используешь _call_ionet_api
        fact_text = await _call_ionet_api( # Или await model.generate_content_async(...) для Gemini
            messages=[{"role": "user", "content": fact_prompt}],
            model_id=IONET_TEXT_MODEL_ID, # ИЛИ НЕ ИСПОЛЬЗУЙ ЭТОТ ПАРАМЕТР ДЛЯ GEMINI
            max_tokens=150,
            temperature=1.1
        ) or "[Генератор бреда сломался]"

        # Добавляем префикс и обрабатываем ошибки API (если _call_ionet_api их возвращает как строки)
        if not fact_text.startswith(("🗿", "[")):
            fact_text = "🗿 " + fact_text
        elif fact_text.startswith("["): # Если _call_ionet_api вернул ошибку
             logger.warning(f"Ошибка генерации факта от API: {fact_text}")
             # Можно не постить ошибку API в чат, а просто пропустить этот раз
             # return
        # --->>> КОНЕЦ ГЕНЕРАЦИИ ФАКТА <<<---

        # Обрезаем, если надо
        MAX_MESSAGE_LENGTH = 4096
        if len(fact_text) > MAX_MESSAGE_LENGTH:
            fact_text = fact_text[:MAX_MESSAGE_LENGTH - 3] + "..."

        # --->>> Отправка и обновление БД (ВНУТРИ TRY...EXCEPT НА ОТПРАВКУ) <<<---
        try:
            # Отправляем факт
            await context.bot.send_message(chat_id=target_chat_id, text=fact_text)
            logger.info(f"Отправлен рандомный факт в НЕАКТИВНЫЙ чат {target_chat_id}")

            # ОБНОВЛЯЕМ ВРЕМЯ ПОСЛЕДНЕГО ВЫСЕРА БОТА в БД ТОЛЬКО ЕСЛИ ОТПРАВКА УСПЕШНА
            await loop.run_in_executor( None, lambda: chat_activity_collection.update_one( {"chat_id": target_chat_id}, {"$set": {"last_bot_shitpost_time": now}} ) )
            logger.info(f"Обновлено время последнего высера для чата {target_chat_id}")

        except (telegram.error.Forbidden, telegram.error.BadRequest) as e:
             logger.warning(f"Не удалось отправить факт в чат {target_chat_id}: {e}. Возможно, бот кикнут.")
        except Exception as send_e:
            logger.error(f"Неизвестная ошибка при отправке факта в чат {target_chat_id}: {send_e}", exc_info=True)
        # --->>> КОНЕЦ TRY...EXCEPT НА ОТПРАВКУ <<<---

    # Этот except ловит ошибки ДО отправки (например, при поиске в БД или ошибку самого ИИ, если _call_ionet_api ее бросает)
    except Exception as e:
        logger.error(f"Ошибка в фоновой задаче check_inactivity_and_shitpost (основной блок): {e}", exc_info=True)

# --- КОНЕЦ ПОЛНОЙ ИСПРАВЛЕННОЙ ФУНКЦИИ ---

# --- ФУНКЦИЯ ДЛЯ /help ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
         # --->>> НАЧАЛО НОВОЙ ПРОВЕРКИ ТЕХРАБОТ <<<---
# Проверяем наличие update и message - без них проверка невозможна
    if not update or not update.message or not update.message.from_user or not update.message.chat:
        logger.warning(f"Не могу проверить техработы - нет данных в update ({__name__})") # Логгируем имя текущей функции
        # Если это важная команда, можно тут вернуть ошибку пользователю
        # await context.bot.send_message(chat_id=update.effective_chat.id, text="Ошибка проверки данных.")
        return # Или просто выйти

    real_chat_id = update.message.chat.id
    real_user_id = update.message.from_user.id
    real_chat_type = update.message.chat.type

    loop = asyncio.get_running_loop()
    maintenance_active = await is_maintenance_mode(loop) # Вызываем функцию проверки

    # Блокируем, если техработы ВКЛЮЧЕНЫ и это НЕ админ в ЛС
    if maintenance_active and (real_user_id != ADMIN_USER_ID or real_chat_type != 'private'):
        logger.info(f"Команда отклонена из-за режима техработ в чате {real_chat_id}")
        try: # Пытаемся ответить и удалить команду
            await context.bot.send_message(chat_id=real_chat_id, text="🔧 Сорян, у меня сейчас технические работы. Попробуй позже.")
            await context.bot.delete_message(chat_id=real_chat_id, message_id=update.message.message_id)
        except Exception as e:
            logger.warning(f"Не удалось ответить/удалить сообщение о техработах: {e}")
        return # ВЫХОДИМ ИЗ ФУНКЦИИ
# --->>> КОНЕЦ НОВОЙ ПРОВЕРКИ ТЕХРАБОТ <<<---
    """Отправляет сообщение со справкой о возможностях бота и реквизитами для доната."""
    user_name = update.message.from_user.first_name or "щедрый ты мой"
    logger.info(f"Пользователь '{user_name}' запросил справку (/help)")

    # РЕКВИЗИТЫ ДЛЯ ДОНАТА (ЗАМЕНИ НА СВОИ ИЛИ ЧИТАЙ ИЗ ENV!)
    MIR_CARD_NUMBER = os.getenv("MIR_CARD_NUMBER", "2200000000000000")
    TON_WALLET_ADDRESS = os.getenv("TON_WALLET_ADDRESS", "UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA...")
    USDC_WALLET_ADDRESS = os.getenv("USDC_WALLET_ADDRESS", "TXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
    USDC_NETWORK = os.getenv("USDC_NETWORK", "TRC20") # Сеть для USDC

    help_text = f"""
🗿 Слышь, {user_name}! Я Попиздяка, главный токсик и тролль этого чата. Вот че я умею:

*Анализ чата:*
Напиши <code>/analyze</code> или "<code>Попиздяка анализируй</code>".
Я прочитаю последние <b>{MAX_MESSAGES_TO_ANALYZE}</b> сообщений и выдам вердикт.

*Анализ картинок:*
Ответь на картинку <code>/analyze_pic</code> или "<code>Попиздяка зацени пикчу</code>".
Я попробую ее обосрать (используя Vision модель!).

*Стишок-обосрамс:*
Напиши <code>/poem Имя</code> или "<code>Бот стих про Имя</code>".
Я попробую сочинить токсичный стишок.

*Предсказание (хуевое):*
Напиши <code>/prediction</code> или "<code>Бот предскажи</code>".
Я выдам тебе рандомное (или позитивное с 1% шансом) пророчество.

*Подкат от Попиздяки:*
Напиши <code>/pickup</code> или "<code>Бот подкати</code>".
Я сгенерирую уебищную фразу для знакомства.

*Прожарка друга (Roast):*
Ответь на сообщение бедолаги <code>/roast</code> или "<code>Бот прожарь его/ее</code>".
Я сочиню уничижительный стендап про этого человека.

*Переделать высер:*
Ответь <code>/retry</code> или "<code>Бот переделай</code>" на МОЙ последний ответ от анализа/стиха/прожарки/предсказания/подката/картинки.

*Новости (Автопостинг):*
Раз в несколько часов я буду постить подборку свежих новостей со своими охуенными комментариями. Не нравится - жалуйся админам.

*Похвала (Саркастичная):*
Ответь на сообщение человека <code>/praise</code> или "<code>Бот похвали его/ее</code>".
Я попробую выдать неоднозначный "комплимент".

*Установить Никнейм:*
Напиши <code>/set_name ТвойНик</code> или "<code>Бот меня зовут Повелитель Мух</code>".
Я буду использовать этот ник в анализе чата вместо твоего имени из Telegram.

*Кто ты, воин?:*
Напиши <code>/whoami</code> или "<code>Бот кто я</code>".
Я покажу твой текущий ник, количество сообщений (которое я видел) и твое почетное (или не очень) звание в банде Попиздяки.


*Писькомер от Попиздяки:*
Напиши <code>/grow_penis</code> или "<code>Бот писька расти</code>" (можно раз в 6 часов). Твой агрегат немного подрастет.
Напиши <code>/my_penis</code> или "<code>Бот моя писька</code>", чтобы узнать текущие ТТХ и звание.
Размер также показывается в <code>/whoami</code>.


*Эта справка:*
Напиши <code>/help</code> или "<code>Попиздяка кто ты?</code>".

*Важно:*
- Дайте <b>админку</b>, чтобы я видел весь ваш пиздеж.
- Иногда я несу хуйню - я работаю на нейросетях.
- Иногда, если в чате тихо, я могу ВНЕЗАПНО кого-то похвалить (в своем стиле) или выдать ебанутый "факт".

*💰 Подкинуть на пиво Попиздяке:*
Если тебе нравится мой бред, можешь закинуть копеечку:

- <b>Карта МИР:</b> <code>{MIR_CARD_NUMBER}</code>
- <b>TON:</b> <code>{TON_WALLET_ADDRESS}</code>
- <b>USDC ({USDC_NETWORK}):</b> <code>{USDC_WALLET_ADDRESS}</code>

Спасибо, блядь! 🗿
    """
    try:
        await context.bot.send_message(chat_id=update.message.chat_id, text=help_text.strip(), parse_mode='HTML')
    except Exception as e:
        logger.error(f"Не удалось отправить /help: {e}", exc_info=True)
        try: await context.bot.send_message(chat_id=update.message.chat_id, text="Справка сломалась. Команды: /analyze, /analyze_pic, /poem, /prediction, /pickup, /roast, /retry, /help.")
        except Exception: pass

# --- ФУНКЦИИ-ОБЕРТКИ ДЛЯ РУССКИХ КОМАНД (Если нужны) ---
# Можно вызывать основные функции напрямую из Regex хэндлеров, если не нужна доп. логика
# async def handle_text_analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await analyze_chat(update, context)
# async def handle_text_analyze_pic_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await analyze_pic(update, context)
# ... и т.д.



# --- АСИНХРОННАЯ ЧАСТЬ И ТОЧКА ВХОДА ---
app = Flask(__name__)
@app.route('/')
def index():
    logger.info("GET / -> OK")
    return "Popizdyaka is alive (probably)."

async def run_bot_async(application: Application) -> None: # Запускает и корректно останавливает бота
    try:
        logger.info("Init TG App..."); await application.initialize()
        if not application.updater: logger.critical("No updater!"); return
        logger.info("Start polling..."); await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Start TG App..."); await application.start()
        logger.info("Bot started (idle)..."); await asyncio.Future() # Ожидаем вечно
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError): logger.info("Stop signal received.")
    except Exception as e: logger.critical(f"ERROR in run_bot_async: {e}", exc_info=True)
    finally: # Shutdown
        logger.info("Stopping bot...");
        if application.running: await application.stop(); logger.info("App stopped.")
        if application.updater and application.updater.is_running: await application.updater.stop(); logger.info("Updater stopped.")
        await application.shutdown(); logger.info("Bot stopped.")

# --- ФУНКЦИИ ДЛЯ УПРАВЛЕНИЯ ТЕХРАБОТАМИ (ТОЛЬКО АДМИН В ЛС) ---
async def maintenance_on(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Включает режим техработ (только админ в ЛС)."""
    user_id = update.message.from_user.id
    chat_type = update.message.chat.type
    if user_id == ADMIN_USER_ID and chat_type == 'private':
        loop = asyncio.get_running_loop()
        success = await set_maintenance_mode(True, loop)
        await update.message.reply_text(f"🔧 Режим техработ {'УСПЕШНО ВКЛЮЧЕН' if success else 'НЕ УДАЛОСЬ ВКЛЮЧИТЬ (ошибка БД)'}.")
    else:
        await update.message.reply_text("Эта команда доступна только админу в личной переписке.")

async def maintenance_off(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выключает режим техработ (только админ в ЛС)."""
    user_id = update.message.from_user.id
    chat_type = update.message.chat.type
    if user_id == ADMIN_USER_ID and chat_type == 'private':
        loop = asyncio.get_running_loop()
        success = await set_maintenance_mode(False, loop)
        await update.message.reply_text(f"✅ Режим техработ {'УСПЕШНО ВЫКЛЮЧЕН' if success else 'НЕ УДАЛОСЬ ВЫКЛЮЧИТЬ (ошибка БД)'}.")
    else:
        await update.message.reply_text("Эта команда доступна только админу в личной переписке.")

# --- КОНЕЦ ФУНКЦИЙ ТЕХРАБОТ ---

# --- ФУНКЦИЯ ПОЛУЧЕНИЯ И КОММЕНТИРОВАНИЯ НОВОСТЕЙ (GNEWS) ---
async def fetch_and_comment_news(context: ContextTypes.DEFAULT_TYPE) -> list[tuple[str, str, str | None]]:
    """Запрашивает новости с GNews.io и генерирует комменты через ИИ."""
    if not GNEWS_API_KEY: return []

    news_list_with_comments = []
    # Формируем URL для GNews API (смотри их документацию для точных параметров!)
    # Пример для top-headlines:
    news_url = f"https://gnews.io/api/v4/top-headlines?category=general&lang={NEWS_LANG}&country={NEWS_COUNTRY}&max={NEWS_COUNT * 2}&apikey={GNEWS_API_KEY}"

    try:
        logger.info(f"Запрос новостей с GNews.io: {news_url.replace(GNEWS_API_KEY, '***')}")
        loop = asyncio.get_running_loop()
        # Используем requests внутри executor'а
        response = await loop.run_in_executor(None, lambda: requests.get(news_url, timeout=15)) # Увеличим таймаут
        response.raise_for_status()
        news_data = response.json()
        articles = news_data.get('articles', [])
        logger.info(f"Получено {len(articles)} новостей с GNews.io.")

        if not articles: return []

        # Отбираем N новостей и генерируем комменты
        count = 0
        for article in articles:
            if count >= NEWS_COUNT: break
            title = article.get('title', 'Без заголовка')
            url = article.get('url', '#')
            # Описание может быть полезно для комментария ИИ
            description = article.get('description', '')
            # Источник
            source_name = article.get('source', {}).get('name', 'Неизвестный источник')

            # Убираем имя источника из заголовка, если оно там есть в конце
            if title.endswith(f" - {source_name}"):
                 title = title[:-len(f" - {source_name}")].strip()

            # Пропускаем новости без заголовка
            if not title or title == '[Removed]': continue

            # --- Генерируем комментарий через ИИ ---
            # Промпт можно сделать чуть лучше, дав краткое описание новости
            comment_prompt = (
                 f"Ты - Попиздяка, циничный и матерный комментатор новостей. Тебе дали новость от '{source_name}':\n"
                 f"Заголовок: «{title}»\n"
                 f"Описание: «{description[:200]}...»\n\n" # Дадим краткое описание для контекста
                 f"Напиши ОДНО КОРОТКОЕ (1 предложение) максимально едкое, саркастичное или черно-юморное мнение об этой новости. Используй мат. Не пиши вступлений. Начинай с `🗿`."
                 f"\nТвой комментарий к новости «{title}»:"
            )
            messages_for_api = [{"role": "user", "content": comment_prompt}]
            # Используем ТЕКСТОВУЮ модель (io.net или Gemini)
            comment_text = await _call_ionet_api( # ИЛИ model.generate_content_async
                messages=messages_for_api,
                model_id=IONET_TEXT_MODEL_ID, # Твоя текстовая модель
                max_tokens=300,
                temperature=0.8
            ) or "[Комментарий не родился]"
            if not comment_text.startswith(("🗿", "[")): comment_text = "🗿 " + comment_text
            # --->>> КОНЕЦ ГЕНЕРАЦИИ КОММЕНТАРИЯ <<<---

            news_list_with_comments.append((title, url, comment_text))
            count += 1
            await asyncio.sleep(0.5) # Пауза

        return news_list_with_comments

    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса к GNews.io: {e}")
        return []
    except Exception as e:
        logger.error(f"Ошибка при получении/обработке новостей GNews: {e}", exc_info=True)
        return []

# --- КОНЕЦ ПЕРЕПИСАННОЙ ФУНКЦИИ ---

# --- ПЕРЕДЕЛАННАЯ post_news_job (С ПРОВЕРКОЙ ТЕХРАБОТ) ---
async def post_news_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Получает новости с комментами и постит их (с учетом техработ)."""
    if not GNEWS_API_KEY: return # Используй GNEWS_API_KEY, если ты на GNews!

    logger.info("Запуск задачи постинга новостей...")
    news_to_post = await fetch_and_comment_news(context)

    if not news_to_post:
        logger.info("Нет новостей для постинга."); return

    # Формируем сообщение (как было)
    message_parts = ["🗿 **Свежие высеры из мира новостей (и мое мнение):**\n"];
    for title, url, comment in news_to_post:
        safe_title = title.replace('<', '<').replace('>', '>').replace('&', '&')
        safe_comment = comment.replace('<', '<').replace('>', '>').replace('&', '&')
        message_parts.append(f"\n- <a href='{url}'>{safe_title}</a>\n  {safe_comment}")
    final_message = "\n".join(message_parts)
    MAX_MESSAGE_LENGTH = 4096
    if len(final_message) > MAX_MESSAGE_LENGTH: final_message = final_message[:MAX_MESSAGE_LENGTH - 3] + "..."

    # Получаем список ВСЕХ активных чатов из БД
    active_chat_ids = []
    try:
        loop = asyncio.get_running_loop(); chat_docs = await loop.run_in_executor(None, lambda: list(chat_activity_collection.find({}, {"chat_id": 1, "_id": 0})))
        active_chat_ids = [doc["chat_id"] for doc in chat_docs]
        logger.info(f"Найдено {len(active_chat_ids)} активных чатов для возможного постинга.")
    except Exception as e: logger.error(f"Ошибка получения списка чатов из MongoDB: {e}"); return

    if not active_chat_ids: logger.info("Нет активных чатов в БД."); return

    # --->>> ПРОВЕРКА РЕЖИМА ТЕХРАБОТ <<<---
    loop = asyncio.get_running_loop()
    maintenance_active = await is_maintenance_mode(loop)
    target_chat_ids_to_post = [] # Список ID, куда будем реально постить

    if maintenance_active:
        logger.warning("РЕЖИМ ТЕХРАБОТ АКТИВЕН! Новости будут отправлены только админу в ЛС (если он есть в активных чатах).")
        try: admin_id = int(os.getenv("ADMIN_USER_ID", "0"))
        except ValueError: admin_id = 0

        if admin_id in active_chat_ids: # Проверяем, есть ли админ в списке чатов, где бот активен
             target_chat_ids_to_post.append(admin_id) # Добавляем только ID админа
             logger.info(f"Админ ID {admin_id} найден в активных чатах, отправляем новость ему в ЛС.")
        else:
             logger.warning(f"Админ ID {admin_id} НЕ найден в активных чатах ИЛИ не задан. Новости НЕ будут отправлены НИКУДА.")

    else: # Если техработы не активны - постим во все активные чаты
        logger.info("Режим техработ не активен. Постим новости во все активные чаты.")
        target_chat_ids_to_post = active_chat_ids
    # --->>> КОНЕЦ ПРОВЕРКИ РЕЖИМА ТЕХРАБОТ <<<---

    # --- ОТПРАВЛЯЕМ НОВОСТИ В ЦЕЛЕВЫЕ ЧАТЫ ---
    if not target_chat_ids_to_post:
        logger.info("Нет целевых чатов для постинга новостей после проверки техработ.")
        return

    logger.info(f"Начинаем отправку новостей в {len(target_chat_ids_to_post)} чатов...")
    for chat_id in target_chat_ids_to_post: # Итерируемся по ОТФИЛЬТРОВАННОМУ списку
        try:
            await context.bot.send_message(chat_id=chat_id, text=final_message, parse_mode='HTML', disable_web_page_preview=True)
            logger.info(f"Новости успешно отправлены в чат {chat_id}")
            await asyncio.sleep(1) # Пауза
        except (telegram.error.Forbidden, telegram.error.BadRequest) as e:
             logger.warning(f"Не удалось отправить новости в чат {chat_id}: {e}.")
        except Exception as e:
             logger.error(f"Неизвестная ошибка при отправке новостей в чат {chat_id}: {e}", exc_info=True)

# --- КОНЕЦ ПЕРЕДЕЛАННОЙ post_news_job ---

# --- ФУНКЦИЯ ДЛЯ КОМАНДЫ ПРИНУДИТЕЛЬНОГО ПОСТИНГА НОВОСТЕЙ (ТОЛЬКО АДМИН В ЛС) ---
async def force_post_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Принудительно запускает постинг новостей (только админ в ЛС)."""
    # Проверка на админа и ЛС
    try: admin_id = int(os.getenv("ADMIN_USER_ID", "0"))
    except ValueError: admin_id = 0
    if update.message.from_user.id != admin_id or update.message.chat.type != 'private':
        await update.message.reply_text("Только админ может форсить новости в ЛС.")
        return
    if not GNEWS_API_KEY:
         await update.message.reply_text("Ключ NewsAPI не настроен, не могу постить новости.")
         return

    logger.info("Админ запросил принудительный постинг новостей.")
    await update.message.reply_text("Окей, запускаю сбор и постинг новостей сейчас...")
    # Просто вызываем ту же функцию, что и планировщик
    await post_news_job(context)
    await update.message.reply_text("Попытка постинга новостей завершена. Смотри логи.")

# --- ПЕРЕДЕЛАННАЯ praise_user (С КОНТЕКСТОМ И ОТВЕТОМ НА СООБЩЕНИЕ) ---
async def praise_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Генерирует саркастическую 'похвалу' пользователю (на кого ответили) с учетом контекста."""

    # --->>> НАЧАЛО НОВОЙ ПРОВЕРКИ ТЕХРАБОТ <<<---
# Проверяем наличие update и message - без них проверка невозможна
    if not update or not update.message or not update.message.from_user or not update.message.chat:
        logger.warning(f"Не могу проверить техработы - нет данных в update ({__name__})") # Логгируем имя текущей функции
        # Если это важная команда, можно тут вернуть ошибку пользователю
        # await context.bot.send_message(chat_id=update.effective_chat.id, text="Ошибка проверки данных.")
        return # Или просто выйти

    real_chat_id = update.message.chat.id
    real_user_id = update.message.from_user.id
    real_chat_type = update.message.chat.type

    loop = asyncio.get_running_loop()
    maintenance_active = await is_maintenance_mode(loop) # Вызываем функцию проверки

    # Блокируем, если техработы ВКЛЮЧЕНЫ и это НЕ админ в ЛС
    if maintenance_active and (real_user_id != ADMIN_USER_ID or real_chat_type != 'private'):
        logger.info(f"Команда отклонена из-за режима техработ в чате {real_chat_id}")
        try: # Пытаемся ответить и удалить команду
            await context.bot.send_message(chat_id=real_chat_id, text="🔧 Сорян, у меня сейчас технические работы. Попробуй позже.")
            await context.bot.delete_message(chat_id=real_chat_id, message_id=update.message.message_id)
        except Exception as e:
            logger.warning(f"Не удалось ответить/удалить сообщение о техработах: {e}")
        return # ВЫХОДИМ ИЗ ФУНКЦИИ
# --->>> КОНЕЦ НОВОЙ ПРОВЕРКИ ТЕХРАБОТ <<<---

    # 2. Проверка, что это ответ на сообщение и не на бота
    if (not update.message or not update.message.reply_to_message or
            not update.message.reply_to_message.from_user or
            update.message.reply_to_message.from_user.id == context.bot.id):
        await context.bot.send_message(chat_id=update.message.chat_id, text="Ответь этой командой на сообщение того, кого хочешь 'похвалить'.")
        return

    # 3. Собираем инфу
    target_user = update.message.reply_to_message.from_user # Кого хвалим
    target_name = target_user.first_name or target_user.username or "этот уникум"
    chat_id = update.message.chat.id
    user = update.message.from_user # Кто хвалит
    user_name = user.first_name or "Главный Льстец"

    logger.info(f"Пользователь '{user_name}' запросил похвалу для '{target_name}' (ID: {target_user.id}). Ищем контекст...")

    # 4. Читаем контекст цели из БД (как в roast_user)
    user_context = "[Недавних сообщений не найдено]"
    USER_CONTEXT_LIMIT_PRAISE = 3 # Хватит 3 сообщений
    try:
        loop = asyncio.get_running_loop()
        query = {"chat_id": chat_id, "user_id": target_user.id}
        sort_order = [("timestamp", pymongo.DESCENDING)]
        user_hist_cursor = await loop.run_in_executor(None, lambda: history_collection.find(query).sort(sort_order).limit(USER_CONTEXT_LIMIT_PRAISE))
        user_messages = list(user_hist_cursor)[::-1]
        if user_messages:
            context_lines = [msg.get('text', '[...]') for msg in user_messages]
            user_context = "\n".join(context_lines)
            logger.info(f"Найден контекст ({len(user_messages)} сообщ.) для {target_name}.")
        else: logger.info(f"Контекст для {target_name} не найден.")
    except Exception as db_e: logger.error(f"Ошибка чтения контекста для похвалы из MongoDB: {db_e}")

    # 5. Формируем промпт для ИИ
    logger.info(f"Генерация похвалы для '{target_name}' с учетом контекста...")

    # --->>> НОВЫЙ ПРОМПТ ДЛЯ КОНТЕКСТНОЙ "ПОХВАЛЫ" <<<---
    praise_prompt = (
        f"Ты - Попиздяка, саркастичный бот, который притворяется, что хочет похвалить пользователя по имени **{target_name}**. "
        f"Вот последние несколько сообщений этого пользователя:\n"
        f"```\n{user_context}\n```\n\n"
        f"Твоя задача: Придумай **КОРОТКУЮ (1-3 предложения) НЕОДНОЗНАЧНУЮ 'ПОХВАЛУ'**. Она должна звучать формально положительно или нейтрально, но содержать **СКРЫТЫЙ САРКАЗМ, ИРОНИЮ или СТЕБ**, по возможности **обыгрывая что-то из его/ее НЕДАВНИХ СООБЩЕНИЙ** или просто **ИМЯ**. Используй немного мата для стиля Попиздяки. Цель - чтобы человек не понял, похвалили его или тонко обосрали. Начинай ответ с `🗿 `.\n\n"
        f"Пример (Контекст: 'Я сегодня пробежал 10 км!'; Имя: Вася): '🗿 Вася, 10 км! Нихуя себе ты лось! Не порвал себе очко от натуги? Молодец, блядь, продолжай в том же духе (к инфаркту).'\n"
        f"Пример (Контекст: 'Сделала новую прическу'; Имя: Лена): '🗿 Ого, Лена, новый образ! Смело. Очень смело. Тебе... идет? Наверное. Выглядишь почти так же хуево, как обычно, но по-новому!'\n"
        f"Пример (Контекста нет; Имя: Дима): '🗿 Дима! Само твое присутствие в этом чате - уже повод для гордости... наверное. Не каждый может так стабильно существовать.'\n\n"
        f"Придумай подобную САРКАСТИЧНУЮ, НЕОДНОЗНАЧНУЮ ПОХВАЛУ для **{target_name}**, по возможности используя контекст:"
    )
    # --->>> КОНЕЦ НОВОГО ПРОМПТА <<<---

    try:
        thinking_message = await context.bot.send_message(chat_id=chat_id, text=f"🗿 Пытаюсь найти, за что 'похвалить' '{target_name}'...")
        messages_for_api = [{"role": "user", "content": praise_prompt}]
        # Вызов ИИ (_call_ionet_api или model.generate_content_async)
        praise_text = await _call_ionet_api( # ИЛИ model.generate_content_async
            messages=messages_for_api, model_id=IONET_TEXT_MODEL_ID, max_tokens=100, temperature=0.85
        ) or f"[Похвала для {target_name} не придумалась]"
        if not praise_text.startswith(("🗿", "[")): praise_text = "🗿 " + praise_text
        try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass

        MAX_MESSAGE_LENGTH = 4096; # Обрезка
        if len(praise_text) > MAX_MESSAGE_LENGTH: praise_text = praise_text[:MAX_MESSAGE_LENGTH - 3] + "..."

        # Отправляем "похвалу"
        target_mention = target_user.mention_html() if target_user.username else f"<b>{target_name}</b>"
        final_text = f"Типа похвала для {target_mention} от {user.mention_html()}:\n\n{praise_text}"
        await context.bot.send_message(chat_id=chat_id, text=final_text, parse_mode='HTML')
        logger.info(f"Отправлена похвала для {target_name}.")
        # Запись для /retry (если нужна, с type='praise')
        # ...

    except Exception as e:
        logger.error(f"ПИЗДЕЦ при генерации похвалы для {target_name}: {e}", exc_info=True)
        try:
            if 'thinking_message' in locals(): await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass
        await context.bot.send_message(chat_id=chat_id, text=f"Бля, {user_name}, не могу похвалить '{target_name}'. Видимо, не за что. Ошибка: `{type(e).__name__}`.")

# --- КОНЕЦ ПЕРЕДЕЛАННОЙ praise_user ---

# --- ОБНОВЛЕННАЯ get_user_profile_data ---
async def get_user_profile_data(user: User | None) -> dict:
    """Получает данные профиля, включая данные для писькомера."""
    # Дефолтные значения, ЕСЛИ ПРОФИЛЯ НЕТ В БД
    default_profile_values = {
        "custom_nickname": None,
        "message_count": 0,
        "current_title": None,
        "penis_size": 0,
        "last_penis_growth": datetime.datetime.fromtimestamp(0, datetime.timezone.utc),
        "current_penis_title": None,
        "tg_first_name": user.first_name if user else "Аноним", # Добавим для единообразия
        "tg_username": user.username if user else None
    }

    if not user:
        # Если нет юзера, возвращаем совсем дефолт
        return {
            "display_name": "Анонимный Хуй",
            "message_count": 0, "current_title": "Призрак Чата",
            "penis_size": 0, "current_penis_title": "Микроб",
            "profile_doc": None # Означает, что профиля в БД нет
        }

    # Имя по умолчанию - из ТГ
    display_name = user.first_name or "Безымянный"
    profile_in_db = None # Сам документ из БД

    try:
        loop = asyncio.get_running_loop()
        profile_in_db = await loop.run_in_executor(
            None,
            lambda: user_profiles_collection.find_one({"user_id": user.id})
        )

        if profile_in_db:
            # Если профиль есть, берем данные из него
            custom_nickname = profile_in_db.get("custom_nickname")
            if custom_nickname: display_name = custom_nickname
            message_count = profile_in_db.get("message_count", 0)
            current_title = profile_in_db.get("current_title")
            penis_size = profile_in_db.get("penis_size", 0)
            last_penis_growth = profile_in_db.get("last_penis_growth", datetime.datetime.fromtimestamp(0, datetime.timezone.utc))
            current_penis_title = profile_in_db.get("current_penis_title")
            return {
                "display_name": display_name, "message_count": message_count,
                "current_title": current_title, "penis_size": penis_size,
                "last_penis_growth": last_penis_growth, "current_penis_title": current_penis_title,
                "profile_doc": profile_in_db # Сам документ, если нужен где-то еще
            }
        else:
            # Если профиля нет в БД, возвращаем дефолтные, но с именем из ТГ
            return {
                "display_name": display_name, # Имя из ТГ, т.к. кастомного нет
                "message_count": 0, "current_title": "Новобранец",
                "penis_size": 0, "current_penis_title": "Зародыш",
                "last_penis_growth": datetime.datetime.fromtimestamp(0, datetime.timezone.utc),
                "profile_doc": None # Профиля нет
            }
    except Exception as e:
        logger.error(f"Ошибка чтения профиля user_id {user.id} из MongoDB: {e}")
        # Возвращаем дефолтные в случае ошибки
        return {
            "display_name": display_name, "message_count": 0, "current_title": "Ошибка Профиля",
            "penis_size": 0, "current_penis_title": "Ошибка Письки",
            "last_penis_growth": datetime.datetime.fromtimestamp(0, datetime.timezone.utc),
            "profile_doc": None
        }
# --- КОНЕЦ ОБНОВЛЕННОЙ get_user_profile_data ---

# --- ФУНКЦИЯ ДЛЯ УСТАНОВКИ НИКНЕЙМА ---
async def set_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Устанавливает кастомный никнейм для пользователя."""
    if not update.message or not update.message.from_user: return
    user = update.message.from_user
    chat_id = update.message.chat.id

    # Извлекаем никнейм
    nickname = ""
    if update.message.text.startswith('/set_name'):
        command_parts = update.message.text.split(maxsplit=1)
        if len(command_parts) >= 2: nickname = command_parts[1].strip()
    else: # Если русский аналог
        match = re.search(r'(?i).*(?:зовут|ник|никнейм)\s+([А-Яа-яЁё\w\s\-]+)', update.message.text) # Разрешаем буквы, цифры, пробелы, дефис
        if match: nickname = match.group(1).strip()

    if not nickname:
        await context.bot.send_message(chat_id=chat_id, text="Хуйню несешь. Напиши `/set_name Твой Крутой Ник` или 'Бот меня зовут Вася Пупкин'.")
        return

    # Ограничим длину ника
    if len(nickname) > 32:
        await context.bot.send_message(chat_id=chat_id, text="Ник слишком длинный, максимум 32 символа, угомонись.")
        return
    # Проверка на плохие символы (можно добавить)
    # if re.search(r"[^\w\s\-]", nickname): ...

    try:
        loop = asyncio.get_running_loop()
        # Обновляем или создаем профиль с новым ником
        await loop.run_in_executor(
            None,
            lambda: user_profiles_collection.update_one(
                {"user_id": user.id}, # Фильтр
                {"$set": {"custom_nickname": nickname, "tg_first_name": user.first_name, "tg_username": user.username},
                 "$setOnInsert": {"user_id": user.id, "message_count": 0, "current_title": None, "penis_size": 0, "last_penis_growth": datetime.datetime.fromtimestamp(0, datetime.timezone.utc), "current_penis_title": None}},
                upsert=True # <--- ТЕПЕРЬ ЭТА СТРОКА ВНУТРИ update_one()!
            ) # <--- Скобка от lambda закрывается здесь
        )
        logger.info(f"Пользователь {user.id} ({user.first_name}) установил никнейм: {nickname}")
        await context.bot.send_message(chat_id=chat_id, text=f"🗿 Записал, отныне ты будешь зваться '<b>{nickname}</b>'. Смотри не обосрись с таким погонялом.", parse_mode='HTML')
        # --->>> ВСТАВЛЯЕМ ВЫЗОВ ФОНОВОГО ОБНОВЛЕНИЯ ИСТОРИИ <<<---
        try:
            # Запускаем обновление истории в фоне, чтобы не ждать его завершения
            asyncio.create_task(update_history_with_new_name(user.id, nickname, context))
            logger.info(f"Запущена задача обновления истории для ника '{nickname}' (user_id: {user.id})")
        except Exception as task_e:
            # Логируем, если даже запустить задачу не удалось
            logger.error(f"Ошибка запуска задачи update_history_with_new_name: {task_e}")
        # --->>> КОНЕЦ ВСТАВКИ <<<---
    except Exception as e:
        logger.error(f"Ошибка сохранения никнейма для user_id {user.id} в MongoDB: {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text="Бля, не смог записать твой ник в свою память (БД). Попробуй позже.")

# --- КОНЕЦ ФУНКЦИИ УСТАНОВКИ НИКНЕЙМА ---

# --- ФУНКЦИЯ ДЛЯ КОМАНДЫ /whoami ---
async def who_am_i(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает инфу о пользователе: ник, кол-во сообщений, звание."""
    if not update.message or not update.message.from_user: return
    user = update.message.from_user
    chat_id = update.message.chat.id

    logger.info(f"Пользователь {user.id} ({user.first_name}) запросил /whoami")

    profile = await get_user_profile(user.id, chat_id) # Используем вспомогательную функцию

    nickname = profile.get("custom_nickname") if profile else None
    display_name = nickname if nickname else user.first_name or "Безымянный Хуй"
    message_count = profile.get("message_count", 0) if profile else 0
    current_title = profile.get("current_title", "Новоприбывший Шкет") if profile else "Неучтенный Призрак"

    # Определяем текущее звание по счетчику (даже если оно не записано в профиле)
    calculated_title = "Школьник на подсосе" # Дефолтное звание
    for count_threshold, (title_name, _) in sorted(TITLES_BY_COUNT.items()):
         if message_count >= count_threshold:
             calculated_title = title_name
         else:
             break # Дальше пороги выше

    reply_text = f"🗿 Ты у нас кто?\n\n"
    reply_text += f"<b>Имя/Ник:</b> {display_name}"
    if nickname: reply_text += f" (в Telegram: {user.first_name or 'ХЗ'})"
    reply_text += f"\n<b>ID:</b> <code>{user.id}</code>"
    reply_text += f"\n<b>Сообщений в моих чатах (с момента появления БД):</b> {message_count}"
    reply_text += f"\n<b>Твое погоняло в банде Попиздяки:</b> {calculated_title}"
    # --->>> ДОБАВЛЯЕМ ИНФУ О ПИСЬКЕ <<<---
    if profile: # Если профиль есть
        current_penis_size = profile.get("penis_size", 0)
        calculated_penis_title = "Неизмеряемый отросток"
        for size_threshold, (title_name, _) in sorted(PENIS_TITLES_BY_SIZE.items()):
             if current_penis_size >= size_threshold:
                 calculated_penis_title = title_name
             else: break

        reply_text += f"\n\n<b>Твой Боевой Агрегат:</b>"
        reply_text += f"\n<b>Длина:</b> {current_penis_size} см"
        reply_text += f"\n<b>Писько-Звание:</b> {calculated_penis_title}"
    # --->>> КОНЕЦ ДОБАВЛЕНИЯ <<<---
    if profile and profile.get("current_title") and profile.get("current_title") != calculated_title:
         reply_text += f"\n(Кстати, твое официально присвоенное звание '{profile.get('current_title')}' уже устарело, скоро обновится!)"
    elif not profile:
         reply_text += f"\n(Пока не видел твоих сообщений, чтобы записать профиль)"

    await context.bot.send_message(chat_id=chat_id, text=reply_text, parse_mode='HTML')

# --- КОНЕЦ ФУНКЦИИ /whoami ---

# Убедись, что импорты asyncio, logging и коллекция history_collection определены выше

# --- ФОНОВАЯ ЗАДАЧА ОБНОВЛЕНИЯ ИМЕНИ В ИСТОРИИ ---
async def update_history_with_new_name(user_id: int, new_nickname: str, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Начинаю фоновое обновление имени на '{new_nickname}' в истории для user_id {user_id}...")
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: history_collection.update_many(
                {"user_id": user_id}, # Найти все сообщения этого юзера
                {"$set": {"user_name": new_nickname}} # Заменить user_name на новый ник
            )
        )
        logger.info(f"Обновление имени в истории для user_id {user_id} завершено: Найдено={result.matched_count}, Обновлено={result.modified_count}")
    except Exception as e:
        logger.error(f"Ошибка фонового обновления имени в истории для user_id {user_id}: {e}", exc_info=True)
# --- КОНЕЦ ФОНОВОЙ ЗАДАЧИ ---

# --- ИСПРАВЛЕННАЯ grow_penis ---
async def grow_penis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user: return
    user = update.message.from_user
    chat_id = update.message.chat.id
    loop = asyncio.get_running_loop()

    # --->>> ИСПОЛЬЗУЕМ get_user_profile_data <<<---
    profile_data = await get_user_profile_data(user) # Получаем ВСЕ данные профиля
    user_name = profile_data["display_name"]
    last_growth_time = profile_data["last_penis_growth"] # Берем из словаря
    current_penis_size = profile_data["penis_size"]     # Берем из словаря
    current_penis_title_from_profile = profile_data["current_penis_title"] # Звание из профиля
    # --->>> КОНЕЦ <<<---

    logger.info(f"Пользователь '{user_name}' (ID: {user.id}) пытается отрастить писюн. Текущий: {current_penis_size} см.")

    current_time = datetime.datetime.now(datetime.timezone.utc)
    time_since_last_growth = (current_time - last_growth_time).total_seconds()

    if time_since_last_growth < PENIS_GROWTH_COOLDOWN_SECONDS:
        # ... (код кулдауна как был) ...
        await context.bot.send_message(chat_id=chat_id, text=f"🗿 {user_name}, твой стручок еще не восстановился...")
        return

    growth = random.randint(1, 30)
    new_size = current_penis_size + growth # Теперь правильно

    try:
        # Обновляем в БД ТОЛЬКО нужные поля
        update_result = await loop.run_in_executor(
            None,
            lambda: user_profiles_collection.find_one_and_update(
                {"user_id": user.id}, # Фильтр
                {
                    # Обновляем всегда:
                    "$set": {"penis_size": new_size, "last_penis_growth": current_time},
                    # Устанавливаем ТОЛЬКО ПРИ СОЗДАНИИ (upsert) те поля, которые не меняются через $set
                    # --->>> УБИРАЕМ penis_size и last_penis_growth ОТСЮДА <<<---
                    "$setOnInsert": {
                        "user_id": user.id,
                        "custom_nickname": None, # или user.first_name, если хочешь дефолт
                        "message_count": 0,      # Начальный message_count
                        "current_title": None,
                        "current_penis_title": None
                        # penis_size и last_penis_growth будут установлены через $set
                    }
                    # --->>> КОНЕЦ ИСПРАВЛЕНИЯ <<<---
                },
                projection={"penis_size": 1, "current_penis_title": 1},
                 upsert=True, return_document=pymongo.ReturnDocument.AFTER
                )
            )
        if not update_result:
            logger.error(f"Не удалось обновить penis_size для {user_name}"); await context.bot.send_message(chat_id=chat_id, text=f"Бля, {user_name}, хуйня с базой."); return

        logger.info(f"Писюн {user_name} вырос на {growth} см, теперь {new_size} см.")
        await context.bot.send_message(chat_id=chat_id, text=f"🗿 {user_name}, твой хуец подрос на <b>{growth} см</b>! Теперь он <b>{new_size} см</b>!", parse_mode='HTML')

        # Проверка на новое писечное звание
        old_penis_title = update_result.get("current_penis_title") # Берем СТАРЫЙ титул из обновленного документа (если был)
        new_penis_title_achieved = None; new_penis_title_message = ""
        for size_threshold, (title_name, achievement_message) in sorted(PENIS_TITLES_BY_SIZE.items()):
            if new_size >= size_threshold: new_penis_title_achieved = title_name; new_penis_title_message = achievement_message
            else: break

        if new_penis_title_achieved and new_penis_title_achieved != old_penis_title:
             logger.info(f"{user_name} достиг писечного звания: {new_penis_title_achieved} ({new_size} см)")
             await loop.run_in_executor(None, lambda: user_profiles_collection.update_one({"user_id": user.id},{"$set": {"current_penis_title": new_penis_title_achieved}}))
             mention = user.mention_html(); achievement_text = new_penis_title_message.format(mention=mention, size=new_size)
             await context.bot.send_message(chat_id=chat_id, text=achievement_text, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Ошибка при увеличении письки для {user_name}: {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text=f"Бля, {user_name}, ебанина, хуй не вырос.")

# --- КОНЕЦ ИСПРАВЛЕННОЙ grow_penis ---

# --- ФУНКЦИЯ ПОКАЗА ПИСЬКИ ---
async def show_my_penis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает текущий размер члена и писечное звание."""
    if not update.message or not update.message.from_user: return
    user = update.message.from_user
    chat_id = update.message.chat.id
    loop = asyncio.get_running_loop()

    profile_data = await get_user_profile_data(user)
    user_name = profile_data["display_name"]
    logger.info(f"Пользователь '{user_name}' (ID: {user.id}) запросил инфу о своем писюне.")

    current_penis_size = 0
    current_penis_title = "Микроскопический отросток" # Дефолтное писечное звание
    profile_doc = profile_data.get("profile_doc")
    if profile_doc:
        current_penis_size = profile_doc.get("penis_size", 0)
        # Определяем звание по текущему размеру
        for size_threshold, (title_name, _) in sorted(PENIS_TITLES_BY_SIZE.items()):
             if current_penis_size >= size_threshold:
                 current_penis_title = title_name
             else: break
        # Можно также взять сохраненное звание, если оно актуально
        # current_penis_title = profile_doc.get("current_penis_title") or current_penis_title


    reply_text = f"🗿 Итак, {user_name}, твоя писяндра:\n\n"
    reply_text += f"<b>Длина:</b> {current_penis_size} см.\n"
    reply_text += f"<b>Звание:</b> {current_penis_title}.\n\n"

    if current_penis_size == 0:
        reply_text += "Похоже, ты его еще не растил, или он у тебя отсох. Попробуй команду 'Бот писька расти'!"
    elif current_penis_size < 10:
        reply_text += "Мда, с таким даже муравья не напугаешь. Работай усерднее!"
    elif current_penis_size < 50:
        reply_text += "Неплохо, но до мирового господства еще далеко."
    else:
        reply_text += "Охуеть! Таким можно гвозди забивать (или сердца разбивать, если повезет)."

    await context.bot.send_message(chat_id=chat_id, text=reply_text, parse_mode='HTML')

# --- КОНЕЦ ФУНКЦИИ ПОКАЗА ПИСЬКИ ---

# Дальше идет async def main() или другие функции...

async def main() -> None:
    logger.info("Starting main()...")
    logger.info("Building Application...")
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Запуск фоновой задачи
    if application.job_queue:
        # Задача для рандомных высеров в тишине
        application.job_queue.run_repeating(check_inactivity_and_shitpost, interval=900, first=60)
        logger.info("Фоновая задача проверки неактивности запущена.")

        # --->>> ЗАПУСК ЗАДАЧИ НОВОСТЕЙ <<<---
        if GNEWS_API_KEY: # Запускаем, только если есть ключ
            application.job_queue.run_repeating(post_news_job, interval=60 * 60 * 6, first=60 * 60 * 6) # Например, каждые 6 часов, первый раз через 2 мин
            logger.info(f"Фоновая задача постинга новостей запущена (каждые {NEWS_POST_INTERVAL/3600} ч).")
        else:
            logger.warning("Задача постинга новостей НЕ запущена (нет NEWSAPI_KEY).")
            # --->>> КОНЕЦ ЗАПУСКА ЗАДАЧИ НОВОСТЕЙ <<<---
    else:
        logger.warning("Не удалось получить job_queue, фоновые задачи не запущены!")

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("maintenance_on", maintenance_on))
    application.add_handler(CommandHandler("maintenance_off", maintenance_off))
    application.add_handler(CommandHandler("analyze", analyze_chat))
    application.add_handler(CommandHandler("analyze_pic", analyze_pic))
    application.add_handler(CommandHandler("poem", generate_poem))
    application.add_handler(CommandHandler("prediction", get_prediction))
    application.add_handler(CommandHandler("roast", roast_user))
    application.add_handler(CommandHandler("retry", retry_analysis))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("post_news", force_post_news))
    application.add_handler(CommandHandler("set_name", set_nickname))
    application.add_handler(CommandHandler("whoami", who_am_i))
    application.add_handler(CommandHandler("grow_penis", grow_penis)) # Можно назвать /grow
    application.add_handler(CommandHandler("my_penis", show_my_penis))  # Можно назвать /myp



    # Добавляем обработчики русских фраз (вызывают ТЕ ЖЕ функции)
    # Можно добавить больше синонимов
    analyze_pattern = r'(?i).*(попиздяка|бот).*(анализ|анализируй|проанализируй|комментируй|обосри|скажи|мнение).*'
    application.add_handler(MessageHandler(filters.Regex(analyze_pattern) & filters.TEXT & ~filters.COMMAND, analyze_chat)) # Прямой вызов

    analyze_pic_pattern = r'(?i).*(попиздяка|бот).*(зацени|опиши|обосри|скажи про).*(пикч|картинк|фот|изображен|это).*'
    application.add_handler(MessageHandler(filters.Regex(analyze_pic_pattern) & filters.TEXT & filters.REPLY & ~filters.COMMAND, analyze_pic)) # Прямой вызов

    poem_pattern = r'(?i).*(?:бот|попиздяка).*(?:стих|стишок|поэма)\s+(?:про|для|об)\s+([А-Яа-яЁё\s\-]+)' # Оставили группу для имени
    application.add_handler(MessageHandler(filters.Regex(poem_pattern) & filters.TEXT & ~filters.COMMAND, generate_poem)) # Прямой вызов

    prediction_pattern = r'(?i).*(?:бот|попиздяка).*(?:предскажи|что ждет|прогноз|предсказание|напророчь).*'
    application.add_handler(MessageHandler(filters.Regex(prediction_pattern) & filters.TEXT & ~filters.COMMAND, get_prediction)) # Прямой вызов


    roast_pattern = r'(?i).*(?:бот|попиздяка).*(?:прожарь|зажарь|обосри|унизь)\s+(?:его|ее|этого|эту).*'
    application.add_handler(MessageHandler(filters.Regex(roast_pattern) & filters.TEXT & filters.REPLY & ~filters.COMMAND, roast_user)) # Прямой вызов

    retry_pattern = r'(?i).*(попиздяка|бот).*(переделай|повтори|перепиши|хуйня|другой вариант).*'
    application.add_handler(MessageHandler(filters.Regex(retry_pattern) & filters.TEXT & filters.REPLY & ~filters.COMMAND, retry_analysis)) # Прямой вызов

    help_pattern = r'(?i).*(попиздяка|попиздоний|бот).*(ты кто|кто ты|что умеешь|хелп|помощь|справка|команды).*'
    application.add_handler(MessageHandler(filters.Regex(help_pattern) & filters.TEXT & ~filters.COMMAND, help_command)) # Прямой вызов

    news_pattern = r'(?i).*(попиздяка|попиздоний|бот).*(новости|че там|мир).*'
    application.add_handler(MessageHandler(filters.Regex(news_pattern) & filters.TEXT & ~filters.COMMAND, force_post_news)) # Прямой вызов

    # --->>> ДОБАВЛЯЕМ РУССКИЕ АНАЛОГИ <<<---
    set_name_pattern = r'(?i).*(?:бот|попиздяка).*(?:меня зовут|мой ник|никнейм)\s+([А-Яа-яЁё\w\s\-]+)'
    application.add_handler(MessageHandler(filters.Regex(set_name_pattern) & filters.TEXT & ~filters.COMMAND, set_nickname))
    whoami_pattern = r'(?i).*(?:бот|попиздяка).*(?:кто я|мой ник|мой статус|мое звание|whoami).*'
    application.add_handler(MessageHandler(filters.Regex(whoami_pattern) & filters.TEXT & ~filters.COMMAND, who_am_i))
    # --->>> КОНЕЦ ДОБАВЛЕНИЯ <<<---

# Добавляем НОВЫЕ обработчики, которые требуют ОТВЕТА на сообщение
    application.add_handler(CommandHandler("pickup", get_pickup_line, filters=filters.REPLY)) # Только в ответе
    application.add_handler(CommandHandler("pickup_line", get_pickup_line, filters=filters.REPLY)) # Только в ответе
    pickup_pattern = r'(?i).*(?:бот|попиздяка).*(?:подкат|пикап|склей|познакомься|замути).*'
    application.add_handler(MessageHandler(filters.Regex(pickup_pattern) & filters.TEXT & filters.REPLY & ~filters.COMMAND, get_pickup_line)) # Только в ответе
    # --->>> КОНЕЦ ИЗМЕНЕНИЙ <<<---

     # --->>> ИЗМЕНЯЕМ ОБРАБОТЧИКИ ПОХВАЛЫ <<<---
    # Убираем старые CommandHandler("praise"...) и MessageHandler(praise_pattern...) если они были
    application.add_handler(CommandHandler("praise", praise_user, filters=filters.REPLY)) # Только в ответе
    praise_pattern = r'(?i).*(?:бот|попиздяка).*(?:похвали|молодец|красавчик)\s+(?:его|ее|этого|эту).*'
    application.add_handler(MessageHandler(filters.Regex(praise_pattern) & filters.TEXT & filters.REPLY & ~filters.COMMAND, praise_user)) # Только в ответе
    # --->>> КОНЕЦ ИЗМЕНЕНИЙ <<<---


    # --->>> ДОБАВЛЯЕМ РУССКИЕ АНАЛОГИ ДЛЯ ТЕХРАБОТ <<<---
    # Regex для ВКЛючения техработ
    maint_on_pattern = r'(?i).*(?:бот|попиздяка).*(?:техработ|ремонт|на ремонт|обслуживание|админ вкл).*'
    # Ловим ТОЛЬКО текст, БЕЗ команд, в ЛЮБОМ чате (проверка админа и ЛС будет ВНУТРИ функции)
    application.add_handler(MessageHandler(filters.Regex(maint_on_pattern) & filters.TEXT & ~filters.COMMAND, maintenance_on)) # Вызываем ту же функцию!

    # Regex для ВЫКЛючения техработ
    maint_off_pattern = r'(?i).*(?:бот|попиздяка).*(?:работай|работать|кончил|закончил|ремонт окончен|админ выкл).*'
    application.add_handler(MessageHandler(filters.Regex(maint_off_pattern) & filters.TEXT & ~filters.COMMAND, maintenance_off)) # Вызываем ту же функцию!
    # --->>> КОНЕЦ ДОБАВЛЕНИЙ <<<---

    # --->>> ДОБАВЛЯЕМ РУССКИЕ АНАЛОГИ ДЛЯ ПИСЬКОМЕРА <<<---
    grow_penis_pattern = r'(?i).*(?:бот|попиздяка).*(?:писька|хуй|член|пенис|елда|стручок|агрегат|змея)\s*(?:расти|отрасти|увеличь|подрасти|накачай|больше|плюс)?.*'
    application.add_handler(MessageHandler(filters.Regex(grow_penis_pattern) & filters.TEXT & ~filters.COMMAND, grow_penis))

    my_penis_pattern = r'(?i).*(?:бот|попиздяка).*(?:моя писька|мой хуй|мой член|мой пенис|какой у меня|что с моей пиписькой).*'
    application.add_handler(MessageHandler(filters.Regex(my_penis_pattern) & filters.TEXT & ~filters.COMMAND, show_my_penis))
    # --->>> КОНЕЦ ДОБАВЛЕНИЯ <<<---

    # Обработчик ответов боту (должен идти ПОСЛЕ regex для команд!)
    application.add_handler(MessageHandler(filters.TEXT & filters.REPLY & ~filters.COMMAND, reply_to_bot_handler))

    # --->>> ВОТ ЭТИ ПЯТЬ СТРОК НУЖНЫ <<<---
    # 1. Только для ТЕКСТА (без команд)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, store_message))
    # 2. Только для ФОТО
    application.add_handler(MessageHandler(filters.PHOTO, store_message))
    # 3. Только для СТИКЕРОВ
    application.add_handler(MessageHandler(filters.Sticker.ALL, store_message))
    # 4. Только для ВИДЕО
    application.add_handler(MessageHandler(filters.VIDEO, store_message))
    # 5. Только для ГОЛОСА
    application.add_handler(MessageHandler(filters.VOICE, store_message))
    # --->>> КОНЕЦ <<<---

    logger.info("Обработчики Telegram добавлены.")

    # Настройка и запуск Hypercorn + бота
    port = int(os.environ.get("PORT", 8080)); hypercorn_config = hypercorn.config.Config();
    hypercorn_config.bind = [f"0.0.0.0:{port}"]; hypercorn_config.worker_class = "asyncio"; hypercorn_config.shutdown_timeout = 60.0
    logger.info(f"Конфиг Hypercorn: {hypercorn_config.bind}, worker={hypercorn_config.worker_class}")
    logger.info("Запуск задач Hypercorn и Telegram бота...")
    shutdown_event = asyncio.Event(); bot_task = asyncio.create_task(run_bot_async(application), name="TelegramBotTask")
    server_task = asyncio.create_task(hypercorn_async_serve(app, hypercorn_config, shutdown_trigger=shutdown_event.wait), name="HypercornServerTask")

    # Ожидание и обработка завершения
    done, pending = await asyncio.wait([bot_task, server_task], return_when=asyncio.FIRST_COMPLETED)
    logger.warning(f"Задача завершилась! Done: {done}, Pending: {pending}")
    if server_task in pending: logger.info("Остановка Hypercorn..."); shutdown_event.set()
    logger.info("Отмена остальных задач..."); [task.cancel() for task in pending]
    await asyncio.gather(*pending, return_exceptions=True)
    for task in done: # Проверка ошибок
        logger.info(f"Проверка завершенной задачи: {task.get_name()}")
        try: await task
        except asyncio.CancelledError: logger.info(f"Задача {task.get_name()} отменена.")
        except Exception as e: logger.error(f"Задача {task.get_name()} не удалась: {e}", exc_info=True)
    logger.info("main() закончена.")

# --- Точка входа в скрипт ---
if __name__ == "__main__":
    logger.info(f"Запуск скрипта bot.py...")
    # Создаем .env шаблон, если надо
    if not os.path.exists('.env') and not os.getenv('RENDER'):
        logger.warning("Файл .env не найден...")
        try:
            with open('.env', 'w') as f: f.write(f"TELEGRAM_BOT_TOKEN=...\nIO_NET_API_KEY=...\nMONGO_DB_URL=...\n# MIR_CARD_NUMBER=...\n# TON_WALLET_ADDRESS=...\n# USDC_WALLET_ADDRESS=...\n# USDC_NETWORK=TRC20\n")
            logger.warning("Создан ШАБЛОН файла .env...")
        except Exception as e: logger.error(f"Не удалось создать шаблон .env: {e}")
    # Проверка ключей
    if not TELEGRAM_BOT_TOKEN or not IO_NET_API_KEY or not MONGO_DB_URL: logger.critical("ОТСУТСТВУЮТ КЛЮЧЕВЫЕ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ!"); exit(1)
    # Запуск
    try: logger.info("Запускаю asyncio.run(main())..."); asyncio.run(main()); logger.info("asyncio.run(main()) завершен.")
    except Exception as e: logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: {e}", exc_info=True); exit(1)
    finally: logger.info("Скрипт bot.py завершает работу.")

# --- КОНЕЦ АБСОЛЮТНО ПОЛНОГО КОДА BOT.PY (AI.IO.NET ВЕРСИЯ - ФИНАЛ v2) ---