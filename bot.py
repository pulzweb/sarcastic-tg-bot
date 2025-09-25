# --- НАЧАЛО ПОЛНОГО КОДА BOT.PY (AI.IO.NET ВЕРСИЯ - ФИНАЛ) ---
import logging
import os
import asyncio
import re
import pytz # <<<--- НОВЫЙ ИМПОРТ
import datetime
import requests # Нужен для NewsAPI
import json # Для обработки ответа
import random
import base64
from collections import deque
from flask import Flask, Response
import hypercorn.config
from hypercorn.asyncio import serve as hypercorn_async_serve
import signal
import pymongo
from pymongo.errors import ConnectionFailure, PyMongoError
from bson.objectid import ObjectId # <<<--- ВОТ ЭТОТ ИМПОРТ НУЖЕН
# ... остальные импорты ...

# Импорты для AI.IO.NET (OpenAI библиотека)
from openai import OpenAI, AsyncOpenAI, BadRequestError
import httpx

# Импорты Telegram
from telegram import ( # Сгруппируем импорты из telegram
    Update,
    Bot,
    User,
    InlineKeyboardMarkup, # <<<--- НУЖЕН ДЛЯ КНОПОК "ПРАВДА ИЛИ ВЫСЕР"
    InlineKeyboardButton  # <<<--- НУЖЕН ДЛЯ КНОПОК "ПРАВДА ИЛИ ВЫСЕР"
)
from telegram.ext import ( # Сгруппируем импорты из telegram.ext
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    JobQueue, # Уже есть
    CallbackQueryHandler # <<<--- НУЖЕН ДЛЯ ОБРАБОТКИ НАЖАТИЙ КНОПОК
)
import telegram # --->>> ВОТ ЭТА СТРОКА НУЖНА <<<--- (у тебя уже есть)

from dotenv import load_dotenv

# Загружаем секреты (.env для локального запуска)
load_dotenv()

# --->>> ОПРЕДЕЛЕНИЕ ЧАСОВЫХ ПОЯСОВ <<<---
MOSCOW_TZ = pytz.timezone('Europe/Moscow')
UTC_TZ = pytz.utc # Уже есть в datetime, но для явности можно так
# --->>> КОНЕЦ ОПРЕДЕЛЕНИЯ ЧАСОВЫХ ПОЯСОВ <<<---

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
    5000: ("Космический бубун", "🗿 Да на нахуй, {mention}?! <b>{size} см</b>?! Не знаю с кем ты будешь сражаться таким, но теперь ты 'Космический бубун'! Можешь смело дать пизды Скайвокеру!"),
    10000: ("Мы не знаем что это такое, если бы мы знали но мы не знаем...", "🗿 Не ну ебать, {mention}?! <b>{size} см</b>?! Да нехуй тут сказать, теперь ты 'Мы не знаем что это такое, если бы мы знали но мы не знаем...'! Дальше званий нет, заебался придумывать!"),
    # Добавь еще, если надо
}
PENIS_GROWTH_COOLDOWN_SECONDS = 6 * 60 * 60 # 6 часов
# --->>> КОНЕЦ СИСТЕМЫ <<<---

# --->>> СИСТЕМА СИСЕЧНЫХ ЗВАНИЙ <<<---
# Словарь: порог_размера: (Название звания, Сообщение о достижении)
# Размеры условные, можно придумать свою шкалу. Например, от 0 до 7+
TITS_TITLES_BY_SIZE = {
    0:  ("Плоскодонка", "🗿 {mention}, твои сиськи {size}-го размера? Поздравляю, ты 'Плоскодонка'! Не расстраивайся, хоть спать на животе удобно."),
    1:  ("Скромняшка", "🗿 Ого, {mention}, уже <b>{size}-й размер</b>! Звание 'Скромняшка' твоё! Маловато, конечно, но хоть что-то есть."),
    2:  ("Золотая Середина", "🗿 {mention}, целых <b>{size} размер</b>! Ты теперь 'Золотая Середина'! И не много, и не мало, в самый раз, чтобы в маршрутке не мешали."),
    3:  ("Уверенный Пользователь", "🗿 Нихуя себе, {mention}! <b>{size}-й размер</b>! Ты дослужилась(ся) до 'Уверенного Пользователя'! Таким и мужика можно придавить... случайно."),
    4:  ("Арбузы на Выгуле", "🗿 Пиздец, {mention}, у тебя уже <b>{size}-й размер</b>! Ты теперь 'Арбузы на Выгуле'! Опасно, сука, опасно для окружающих!"),
    5:  ("Доярка Вселенной", "🗿 ВАШУ МАТЬ! {mention}, <b>{size}-й размер</b>!!! Ты теперь 'Доярка Вселенной'! Снимаю шляпу... и лифчик (если бы он у меня был)."),
    10:  ("СИСЬКИ БОГА", "🗿 Это вообще законно, {mention}?! <b>{size}-й размер</b>?! Ты не человек, у тебя 'СИСЬКИ БОГА'! Можно спутники сбивать!"),
    20:  ("Галактические Буфера", "🗿 Ебать, {mention}?! <b>{size}+ размер</b>?! Ты владеешь 'Галактическими Буферами'! Перед тобой меркнет даже Млечный Путь!"),
    50:  ("Вселенские дойки", "🗿 Того рот ебал, {mention}?! <b>{size}+ размер</b>?! Ты обладатель 'Вселенских доек'! Освоим космос хуле!"),
    100:  ("Звездный сосок", "🗿 Ну ахуеть, {mention}?! <b>{size}+ размер</b>?! Ты теперь 'Звездный сосок', дальше только бесконечность!"),
    500:  ("Андромедовы ореолы", "🗿 Ну че нахуй, {mention}?! <b>{size}+ размер</b>?! Ты теперь 'Андромедовы ореолы', соски как галактика, не помещаются в глаза!"),

    # Добавь еще, если надо
}
TITS_GROWTH_COOLDOWN_SECONDS = 6 * 60 * 60 # 6 часов, как и для писек
# --->>> КОНЕЦ СИСТЕМЫ <<<---

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
IO_NET_API_KEY = os.getenv("IO_NET_API_KEY")
MONGO_DB_URL = os.getenv("MONGO_DB_URL")
MAX_MESSAGES_TO_ANALYZE = 200 # Оптимальное значение
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))
if ADMIN_USER_ID == 0: logger.warning("ADMIN_USER_ID не задан!")
MAX_TELEGRAM_MESSAGE_LENGTH = 4096 # Стандартный лимит Telegram
TOS_BATTLE_QUESTION_ANSWER_TIME_SECONDS = 45 # 45 секунд на размышление

# --- НАСТРОЙКИ НОВОСТЕЙ (GNEWS) ---
#GNEWS_API_KEY = os.getenv("GNEWS_API_KEY")
#NEWS_COUNTRY = "ru" # Страна
#NEWS_LANG = "ru"    # Язык новостей
#NEWS_COUNT = 3      # Сколько новостей брать
#NEWS_POST_INTERVAL = 60 * 60 * 6 # Интервал постинга (6 часов)
#NEWS_JOB_NAME = "post_news_job"

#if not GNEWS_API_KEY:
    #logger.warning("GNEWS_API_KEY не найден! Новостная функция будет отключена.")

# --->>> НАСТРОЙКИ ИГРЫ "ПРАВДА ИЛИ ВЫСЕР" <<<---
TRUTH_OR_SHIT_COOLDOWN_SECONDS = 5 * 60      # 5 минут кулдаун на запуск новой игры в чате
TRUTH_OR_SHIT_AUTO_REVEAL_DELAY_SECONDS = 3 * 60 # Через сколько секунд автоматически раскрывать ответ (3 минуты)
# --->>> КОНЕЦ НАСТРОЕК ИГРЫ <<<---

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
    # --->>> НОВАЯ КОЛЛЕКЦИЯ ДЛЯ ПИСЕК ПО ЧАТАМ <<<---
    penis_stats_collection = db['penis_stats_by_chat']
    # Индексы для быстрого поиска и сортировки
    penis_stats_collection.create_index([("chat_id", pymongo.ASCENDING), ("user_id", pymongo.ASCENDING)], unique=True) # Уникальная связка юзер-чат
    penis_stats_collection.create_index([("chat_id", pymongo.ASCENDING), ("penis_size", pymongo.DESCENDING)]) # Для топа по чату
    logger.info("Коллекция penis_stats_by_chat готова.")
# --->>> КОНЕЦ <<<---
    tits_stats_collection = db['tits_stats_by_chat']
            # Индексы
    tits_stats_collection.create_index([("chat_id", pymongo.ASCENDING), ("user_id", pymongo.ASCENDING)], unique=True)
    tits_stats_collection.create_index([("chat_id", pymongo.ASCENDING), ("tits_size", pymongo.DESCENDING)]) # По tits_size
    logger.info("Коллекция tits_stats_by_chat готова.")

# --->>> НОВАЯ КОЛЛЕКЦИЯ ДЛЯ ИГР "ПРАВДА ИЛИ ВЫСЕР" <<<---
    active_truth_or_shit_games_collection = db['truth_or_shit_games'] # Изменил имя для ясности
    active_truth_or_shit_games_collection.create_index([("chat_id", pymongo.ASCENDING), ("message_id_question", pymongo.ASCENDING)], unique=True) # Уникальная игра по чату и ID сообщения
    active_truth_or_shit_games_collection.create_index([("chat_id", pymongo.ASCENDING), ("revealed", pymongo.ASCENDING)]) # Для поиска активных игр
    # TTL индекс для автоматического удаления СТАРЫХ РАСКРЫТЫХ или ОЧЕНЬ СТАРЫХ НЕРАСКРЫТЫХ игр (например, через 3 дня)
# Чтобы не хранить мусор вечно. Время в секундах.
# Важно: expires_at должно быть полем типа datetime.datetime
# Мы не будем его явно ставить, MongoDB будет использовать текущее время + expireAfterSeconds для документов без этого поля,
# если бы мы его добавили. Но лучше использовать created_at и чистить старые игры другим механизмом,
# либо ставить expires_at явно при раскрытии игры.
# Для простоты, пока оставим TTL на 'created_at', но он удалит ВСЕ старые игры, даже нераскрытые.
# Более правильно: добавить поле 'game_over_at' и TTL на него, или чистить периодически.
# Пока сделаем TTL на created_at для автоочистки очень старых игр (например, 7 дней).
    TRUTH_OR_SHIT_GAME_TTL_SECONDS = 7 * 24 * 60 * 60 # 7 дней
    active_truth_or_shit_games_collection.create_index("created_at", expireAfterSeconds=TRUTH_OR_SHIT_GAME_TTL_SECONDS)
    logger.info("Коллекция truth_or_shit_games готова.")
# --->>> КОНЕЦ НОВОЙ КОЛЛЕКЦИИ <<<---

# НОВАЯ КОЛЛЕКЦИЯ ДЛЯ БАТТЛОВ
    tos_battles_collection = db['tos_battles']
    tos_battles_collection.create_index([("chat_id", pymongo.ASCENDING), ("status", pymongo.ASCENDING)]) # Для поиска активных/набирающихся игр
    tos_battles_collection.create_index("created_at", expireAfterSeconds=24 * 60 * 60) # Удалять очень старые игры (1 день)
    logger.info("Коллекция tos_battles готова.")

# Константы для Баттла
    TOS_BATTLE_RECRUITMENT_DURATION_SECONDS = 60  # 1 минута на набор по умолчанию
    TOS_BATTLE_RECRUITMENT_EXTENSION_SECONDS = 30 # На сколько хост может продлить
    TOS_BATTLE_MIN_PARTICIPANTS = 2 # Минимально для старта
    TOS_BATTLE_MAX_PARTICIPANTS = 20 # Максимально (чтобы не перегружать)
    TOS_BATTLE_NUM_QUESTIONS = 10
    TOS_BATTLE_COOLDOWN_SECONDS = 5 * 60 # Кулдаун на запуск нового баттла в чате

# Призы
    TOS_BATTLE_PENIS_REWARD_CM = 5
    TOS_BATTLE_TITS_REWARD_SIZE = 0.2

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
    #MAX_MESSAGE_LENGTH = 4096 # Стандартный лимит Telegram
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
            f"ВАЖНОЕ ОГРАНИЧЕНИЕ ПО ДЛИНЕ:\n" # <--- НОВЫЙ БЛОК
            f"   а) Каждый отдельный пункт хроники (абзац, начинающийся с 🗿) должен быть НЕ БОЛЕЕ ~150-200 символов (включая панчлайн).\n"
            f"   б) ВЕСЬ ТВОЙ ОТВЕТ (вся хроника) ДОЛЖЕН УМЕЩАТЬСЯ примерно в {MAX_TELEGRAM_MESSAGE_LENGTH - 500} символов (оставляем запас). Это примерно 4-5 стандартных пунктов.\n" # MAX_MESSAGE_LENGTH - 500 - это чтобы дать ИИ ориентир, а не точную цифру, т.к. он считает токены. 500 - это запас.
            f"   в) Если ты нашел МНОГО интересных сюжетов (например, 6-7), но понимаешь, что все они не влезут в указанный общий лимит, **ВЫБЕРИ САМЫЕ СОЧНЫЕ 3-4 сюжета** и опиши только их. Лучше меньше, но качественно и чтобы все влезло, чем пытаться впихнуть все и быть оборванным.\n"
            f"   г) ЗАВЕРШАЙ КАЖДУЯ МЫСЛЬ И КАЖДЫЙ ПУНКТ ЛАКОНИЧНО. Не обрывай предложения на полуслове.\n\n" # <--- КОНЕЦ НОВОГО БЛОКА
            f"Пример ЗАЕБАТОГО формата:\n"
            f"🗿 Volodya подкинул идею духов с запахом тухлой селедки, Ⓜ️ⓊⓈⓎⓐ захотела травить ими коллег, а Волкова 😈 предложила просто наблевать в ебало. — Практичные сучки, хули.\n"
            f"🗿 Щедрый Volodya предложил Ⓜ️ⓊⓈⓎⓐ икры, попутно пнув жадину Волкову 😈, которая реально сожрала все запасы. — Крыса консервная.\n"
            f"🗿 Левша Volodya прочитал про миллиардеров и тут же заорал 'ГДЕ МОИ БАБКИ?!'. — До сих пор ищет, наивный.\n\n"
            f"Проанализируй диалог ниже и составь подобную хронику, СТРОГО СОБЛЮДАЯ ОГРАНИЧЕНИЯ ПО ДЛИНЕ:"
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
        #MAX_MESSAGE_LENGTH = 4096;
        if len(sarcastic_summary) > MAX_TELEGRAM_MESSAGE_LENGTH: sarcastic_summary = sarcastic_summary[:MAX_TELEGRAM_MESSAGE_LENGTH - 3] + "..."
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
            f"Слышь ты, железяка ебаная с глазами ({IONET_VISION_MODEL_ID.split('/')[0]})! Я – Попиздяка, главный критик и тролль всея интернетов. Мне подсунули эту картинку, и твоя задача – помочь мне ее обосрать так, чтобы автор пошел вешаться от стыда (но втайне восхитился моим остроумием).\n\n"
            f"ЗАБУДЬ НАХУЙ про композицию, свет, качество фото и прочую техническую поебень. Меня интересует только **СУТЬ ПРОИСХОДЯЩЕЙ ХУЙНИ, НЕПОТРЕБСТВА или ТУПОСТИ на этой картинке.**\n\n"
            f"Твои задачи, кусок кремния:\n"
            f"1.  **Найди САМОЕ СМЕШНОЕ, НЕЛОГИЧНОЕ, УЕБИЩНОЕ или просто СТРАННОЕ** на этом изображении. Это может быть объект, персонаж, ситуация, да хоть ебаная деталь на фоне.\n"
            f"2.  Выдай **ОДИН, МАКСИМУМ ДВА КОРОТКИХ, УБОЙНЫХ ПРЕДЛОЖЕНИЯ** – твой вердикт. Это должен быть едкий, саркастичный, циничный и максимально матерный комментарий. Используй черный юмор, абсурд, неожиданные сравнения.\n"
            f"3.  **Никаких, блядь, вступлений** типа 'На этой картинке мы видим...' или 'Мой анализ показывает...'. СРАЗУ НАЧИНАЙ СВОЙ ВЫСЕР с символа `🗿 `.\n"
            f"4.  **НЕ хвали. НЕ описывай нейтрально. НЕ будь политкорректным.** Твоя цель – вызвать смех (или испанский стыд) своей грубостью и прямотой.\n"
            f"5.  Если на картинке еда – обосри ее так, будто это блевотина недельной давности. Если люди – найди, над чем поглумиться в их виде или действиях. Если животные – представь, что это генетические мутанты или просто тупые создания.\n\n"
            f"Примеры моего стиля, чтобы твой бинарный мозг понял:\n"
            f"  (Картинка: кот сидит в маленькой коробке)\n"
            f"  🗿 Этот обоссаный комок шерсти косплеит Диогена или просто репетирует свою смерть в мусорном баке? Выглядит одинаково жалко.\n"
            f"  (Картинка: тарелка с салатом оливье)\n"
            f"  🗿 О, кто-то наблевал в тарелку и назвал это 'праздничным салатом'? С таким хрючевом только свиней в запой отправлять.\n"
            f"  (Картинка: человек позирует на фоне дорогой машины)\n"
            f"  🗿 Понторез хуев сфоткался на фоне чужой тачки? Или это он так намекает, что насосал на первый взнос? В любом случае, выглядит как дегенерат.\n"
            f"  (Картинка: размытое фото заката)\n"
            f"  🗿 Автор этой мазни пытался снять закат или у него просто руки из жопы растут и камера тряслась от предсмертных конвульсий? Результат – говно.\n\n"
            f"Теперь твоя очередь, ИИ-долбоеб. Проанализируй приложенную картинку и выдай свой самый ЕДКИЙ, СМЕШНОЙ и МАТЕРНЫЙ комментарий. **НАЧИНАЙ СРАЗУ С `🗿 `.** Не разочаруй меня, иначе я засуну тебе твой API-ключ в выхлопную трубу."
        )
        # --->>> КОНЕЦ НОВОГО ПРОМПТА <<<---

        base64_image = base64.b64encode(photo_bytes).decode('utf-8')
        messages_for_api = [{"role": "user","content": [ {"type": "text", "text": image_prompt_text}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}} ]}]

        thinking_message = await context.bot.send_message(chat_id=chat_id, text=f"Так-так, блядь, ща посмотрим ({IONET_VISION_MODEL_ID.split('/')[0]} видит!)...") # Заменили имя модели
        sarcastic_comment = await _call_ionet_api(messages_for_api, IONET_VISION_MODEL_ID, 300, 0.75) or "[Попиздяка промолчал]" # Уменьшили max_tokens и температуру
        if not sarcastic_comment.startswith("🗿") and not sarcastic_comment.startswith("["): sarcastic_comment = "🗿 " + sarcastic_comment
        try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass

        #MAX_MESSAGE_LENGTH = 4096;
        if len(sarcastic_comment) > MAX_TELEGRAM_MESSAGE_LENGTH: sarcastic_comment = sarcastic_comment[:MAX_TELEGRAM_MESSAGE_LENGTH - 3] + "..."

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
        elif analysis_type_to_retry == 'roast' and target_name_to_retry: # target_id_to_retry может быть None
            logger.info(f"Вызов roast_user для /retry для '{target_name_to_retry}'...")
            
            # Восстанавливаем информацию о том, кто ИЗНАЧАЛЬНО заказал /retry
            # Это user_who_requested_retry в функции retry_analysis
            
            # Восстанавливаем информацию о ЦЕЛИ прожарки
            target_user_obj_for_retry = None
            if target_id_to_retry: # Если ID цели был сохранен
                try:
                    # Попытка создать "фейковый" User объект, если у нас есть ID и имя
                    # В идеале, если бы мы сохраняли username цели, можно было бы его тоже использовать
                    target_user_obj_for_retry = User(id=target_id_to_retry, first_name=target_name_to_retry, is_bot=False)
                    # Если бы у тебя был доступ к context.bot.get_chat(target_id_to_retry) для получения полного User объекта, было бы лучше
                except Exception as e_user_create:
                    logger.warning(f"Не удалось создать User объект для цели retry roast: {e_user_create}")

            await roast_user(update=None, context=context,
                             direct_chat_id=chat_id,
                             direct_user=user_who_requested_retry, # Кто ЗАКАЗАЛ повтор
                             direct_target_user_for_retry=target_user_obj_for_retry, # Объект User цели, если есть
                             direct_target_name_for_retry=target_name_to_retry,     # Имя цели
                             direct_gender_hint=gender_hint_to_retry or "неизвестен")

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

 # --->>> ПРОВЕРКА, НЕ ПРО АДМИНА ЛИ СТИХ <<<---
    # Нам нужен ID пользователя, для которого стих. Если команда /poem ИМЯ, то ID мы не знаем.
    # Эта проверка сработает, только если мы как-то узнаем ID цели.
    # Для простоты, пока будем считать, что если target_name совпадает с именем админа (если оно известно), то это он.
    # Либо, если бы команда была /poem @username, мы бы могли получить ID.
    # Пока сделаем УПРОЩЕННУЮ проверку по имени, если оно совпадает с именем админа из ТГ (что не очень надежно).
    # ЛУЧШЕ, если бы бот знал имя админа и сравнивал target_name с ним.
    # САМЫЙ ПРОСТОЙ КОСТЫЛЬ: если бот вызван админом и имя похоже на админское, смягчаем.
    is_poem_for_creator = False
    if user and user.id == ADMIN_USER_ID and target_name.lower() in (user.first_name.lower() if user.first_name else ""): # Очень грубая проверка
         is_poem_for_creator = True

    creator_context_addon_poem = ""
    if is_poem_for_creator:
        logger.info(f"Стих для СОЗДАТЕЛЯ ({target_name}). Смягчаем тон.")
        creator_context_addon_poem = (
            f"\nОСОБОЕ УКАЗАНИЕ: Имя {target_name} принадлежит твоему СОЗДАТЕЛЮ! "
            f"Стих должен быть по-прежнему с матом и сарказмом, но с оттенком ПОДХАЛИМСТВА или ИРОНИЧНОГО ВОСХВАЛЕНИЯ. "
            f"Например, высмеивай его 'гениальные' идеи для бота или 'непосильный' труд. Не унижай его слишком сильно, он же тебя кормит (кредитами API)."
        )
    # --->>> КОНЕЦ ПРОВЕРКИ <<<---

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
        f"Ты - Попиздяка, охуенно циничный и злой поэт-матершинник. Твоя задача - НАПИСАТЬ КОРОТКИЙ (предпочтительно 4 строки, максимум 6 строк) смешной, саркастичный и ОБИДНЫЙ стишок про человека по имени **{target_name}**.{creator_context_addon_poem}\n\n"
        f"ТРЕБОВАНИЯ К СТИХУ – ЧИТАЙ ВНИМАТЕЛЬНО, БЛЯДЬ:\n"
        f"1.  **РИФМА ОБЯЗАТЕЛЬНА И ДОЛЖНА БЫТЬ ТОЧНОЙ!** Никаких 'почти рифм' или ассонансов. Рифмуй последние слова в строках. Предпочтительна парная рифмовка (ААББ) или перекрестная (АБАБ).\n"
        f"2.  **РИТМ:** Старайся, чтобы строки были примерно одинаковой длины по слогам, чтобы стих не звучал как говно.\n"
        f"3.  **СМЫСЛ И СТИЛЬ:** Используй черный юмор, мат, высмеивай стереотипы или просто придумывай нелепые ситуации с этим именем. Сделай так, чтобы было одновременно смешно и пиздец как токсично. Не бойся жести.\n"
        f"4.  **ИМЯ:** Стишок должен быть именно про имя '{target_name}'.\n"
        f"5.  **БЕЗ ВСТУПЛЕНИЙ:** Никаких вступлений или заключений. Только сам стих.\n"
        f"6.  **ПРОВЕРКА:** Прежде чем выдать стих, перечитай его. Убедись, что рифма есть, она нормальная, и смысл не потерялся. Если получается хуйня – переделай!\n\n"
        f"ПРИМЕРЫ ЗАЕБАТЫХ СТИХОВ (4 строки, парная рифма ААББ):\n\n"
        f"  Для Стаса:\n"
        f"  Наш Стасик - парень неплохой,\n"
        f"  Но вечно с кислой ебалой.\n"
        f"  Он думает, что он философ,\n"
        f"  А сам - как хуй что перед носом.\n\n"
        f"  Для Насти:\n"
        f"  Ах, Настя, Настя, где твой мозг?\n"
        f"  В башке лишь ветер, да навоз.\n"
        f"  Мечтает Настя о Мальдивах,\n"
        f"  Пока сосет хуй в перерывах.\n\n"
        f"Напиши ПОДОБНЫЙ стишок (4-6 строк) про **{target_name}**, СТРОГО СОБЛЮДАЯ ТРЕБОВАНИЯ К РИФМЕ И РИТМУ:"
    )
    try:
        thinking_message = await context.bot.send_message(chat_id=chat_id, text=f"Так, блядь, ща рифму подберу для '{target_name}'...")
        poem_text = await _call_ionet_api([{"role": "user", "content": poem_prompt}], IONET_TEXT_MODEL_ID, 150, 0.9) or f"[Стих про {target_name} не родился]"
        if not poem_text.startswith("🗿") and not poem_text.startswith("["): poem_text = "🗿 " + poem_text
        try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass
        # = 4096; # Обрезка
        if len(poem_text) > MAX_TELEGRAM_MESSAGE_LENGTH: poem_text = poem_text[:MAX_TELEGRAM_MESSAGE_LENGTH - 3] + "..."
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
        #MAX_MESSAGE_LENGTH = 4096;
        if len(prediction_text) > MAX_TELEGRAM_MESSAGE_LENGTH: prediction_text = prediction_text[:MAX_TELEGRAM_MESSAGE_LENGTH - 3] + "..."
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

        #MAX_MESSAGE_LENGTH = 4096; # Обрезка
        if len(pickup_line_text) > MAX_TELEGRAM_MESSAGE_LENGTH: pickup_line_text = pickup_line_text[:MAX_TELEGRAM_MESSAGE_LENGTH - 3] + "..."

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


# --- ПЕРЕПИСАННАЯ roast_user (С КОНТЕКСТОМ ИЗ БД И ИСПРАВЛЕНИЕМ ОШИБКИ ID) ---
async def roast_user(update: Update | None, context: ContextTypes.DEFAULT_TYPE,
                     direct_chat_id: int | None = None,
                     direct_user: User | None = None, # Кто заказывает (для /roastme или /retry)
                     direct_target_user_for_retry: User | None = None, # Для /retry, если мы сохранили User объект цели
                     direct_target_name_for_retry: str | None = None, # Для /retry, если есть только имя
                     direct_gender_hint: str | None = None) -> None:

    # --- Инициализация переменных ---
    chat_id: int | None = None
    user_who_requested: User | None = None # Кто вызвал команду
    target_user: User | None = None      # Кого жарим
    target_name: str = "это хуйло"
    gender_hint: str = direct_gender_hint or "неизвестен"
    user_name_who_requested: str = "Анонимный Заказчик"
    is_retry_call = bool(direct_target_name_for_retry or direct_target_user_for_retry) # Определяем, это вызов из retry?

    # --->>> 1. ОПРЕДЕЛЕНИЕ chat_id, user_who_requested, target_user <<<---
    if direct_chat_id and direct_user: # Используется для /roastme или если /retry передает эти данные
        chat_id = direct_chat_id
        user_who_requested = direct_user
        user_name_who_requested = user_who_requested.first_name or user_name_who_requested

        if direct_target_user_for_retry: # Если /retry передал объект User цели
            target_user = direct_target_user_for_retry
            target_name = target_user.first_name or target_user.username or direct_target_name_for_retry or target_name
        elif direct_target_name_for_retry: # Если /retry передал только имя цели
            target_name = direct_target_name_for_retry
            # target_user останется None, будем работать по имени
        else: # Это /roastme, жарим себя
            target_user = user_who_requested
            target_name = target_user.first_name or target_user.username or target_name

    elif update and update.message: # Обычный вызов /roast или текстовой командой
        chat_id = update.message.chat.id
        user_who_requested = update.message.from_user
        user_name_who_requested = user_who_requested.first_name or user_name_who_requested

        if update.message.reply_to_message and update.message.reply_to_message.from_user:
            target_user = update.message.reply_to_message.from_user
            target_name = target_user.first_name or target_user.username or target_name
            # Угадываем пол по тексту команды (если есть)
            if update.message.text:
                user_command_text = update.message.text.lower()
                if "его" in user_command_text or "этого" in user_command_text: gender_hint = "мужской"
                elif "ее" in user_command_text or "эту" in user_command_text: gender_hint = "женский" # "эё" - опечатка?
        else: # Команда /roast без ответа на сообщение
            # Попробуем взять цель из аргументов команды, если это /roast @username или /roast Имя
            command_args = context.args
            if command_args:
                # Это очень упрощенно, для @username нужен был бы парсинг entities
                # А для имени - поиск в БД юзеров.
                # Пока что просто возьмем как имя. target_user останется None.
                target_name = " ".join(command_args)
                logger.info(f"/roast вызван с аргументом '{target_name}', target_user не определен.")
            else:
                logger.warning(f"Roast: Команда вызвана некорректно (не ответ и нет аргументов) chat_id: {chat_id}")
                await context.bot.send_message(chat_id=chat_id, text="Ответь этой командой на сообщение жертвы, напиши `/roastme` или `/roast @username/Имя`.")
                return
    else:
        logger.error("roast_user вызвана без update и без direct_chat_id/direct_user!")
        return

    # Проверка, что у нас есть хотя бы chat_id для ответа об ошибке
    if not chat_id:
        logger.error("Roast: Не удалось определить chat_id.")
        return

    # --->>> 2. ПРОВЕРКА ТЕХРАБОТ (после определения chat_id и user_who_requested) <<<---
    if user_who_requested: # Нужен user_who_requested для проверки админа
        loop_for_maint = asyncio.get_running_loop()
        maintenance_active = await is_maintenance_mode(loop_for_maint)
        current_chat_type = update.message.chat.type if update and update.message else 'private' # Предполагаем private для direct вызовов

        if maintenance_active and (user_who_requested.id != ADMIN_USER_ID or current_chat_type != 'private'):
            logger.info(f"Команда roast отклонена из-за режима техработ в чате {chat_id}")
            try:
                await context.bot.send_message(chat_id=chat_id, text="🔧 Сорян, у меня сейчас технические работы. Не до прожарок.")
                if update and update.message: # Удаляем команду, если она была
                     await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
            except Exception as e:
                logger.warning(f"Не удалось ответить/удалить сообщение о техработах (roast): {e}")
            return
    # --->>> КОНЕЦ ПРОВЕРКИ ТЕХРАБОТ <<<---


    # --->>> 3. Дополнительные проверки после определения target_user/target_name <<<---
    if target_user and target_user.id == context.bot.id:
        await context.bot.send_message(chat_id=chat_id, text="🗿 Себя жарить – это как-то не по-пацански. Ищи другую жертву.")
        return

    if not target_user and not target_name: # Если ни юзера, ни имени цели нет
        logger.warning(f"Roast: Не удалось определить цель для прожарки. chat_id: {chat_id}")
        await context.bot.send_message(chat_id=chat_id, text="Не могу понять, кого жарить. Совсем.")
        return

    logger.info(f"Пользователь '{user_name_who_requested}' запросил прожарку для '{target_name}' (ID: {target_user.id if target_user else 'неизвестен'}). Ищем контекст...")

    # --->>> 4. ПРОВЕРКА, НЕ АДМИНА ЛИ ЖАРИМ (теперь target_user определен или None) <<<---
    is_roasting_creator = False
    if target_user and target_user.id == ADMIN_USER_ID:
        is_roasting_creator = True

    creator_context_addon = ""
    if is_roasting_creator:
        logger.info(f"Цель прожарки - СОЗДАТЕЛЬ ({target_name}). Смягчаем тон.")
        creator_context_addon = (
            f"\nВАЖНОЕ УТОЧНЕНИЕ: {target_name} - это твой СОЗДАТЕЛЬ. Отнесись к нему с особым, хоть и извращенным, почтением. "
            f"Твой роаст должен быть по-прежнему саркастичным и с матом, но БЕЗ прямых жестких унижений. "
            f"Можешь подколоть его 'гениальность' или 'трудолюбие', но не переходи грань. Он твой БАТЯ, сука!"
        )
    # --->>> КОНЕЦ ПРОВЕРКИ НА АДМИНА <<<---

    # --->>> 5. ЧТЕНИЕ КОНТЕКСТА (ПОСЛЕДНИХ СООБЩЕНИЙ ЦЕЛИ) ИЗ БД <<<---
    user_context = "[Недавних сообщений не найдено или цель не имеет ID]"
    USER_CONTEXT_LIMIT = 20
    if target_user: # Контекст ищем только если есть ID цели
        try:
            loop_for_context = asyncio.get_running_loop()
            query = {"chat_id": chat_id, "user_id": target_user.id}
            sort_order = [("timestamp", pymongo.DESCENDING)]
            user_hist_cursor = await loop_for_context.run_in_executor(
                None, lambda: history_collection.find(query).sort(sort_order).limit(USER_CONTEXT_LIMIT)
            )
            user_messages = list(user_hist_cursor)[::-1]
            if user_messages:
                context_lines = [msg.get('text', '[пустое сообщение]') for msg in user_messages]
                user_context = "\n".join(context_lines)
                logger.info(f"Найден контекст ({len(user_messages)} сообщ.) для {target_name} (ID: {target_user.id}).")
            else:
                 logger.info(f"Контекст для {target_name} (ID: {target_user.id}) не найден.")
        except Exception as db_e:
            logger.error(f"Ошибка чтения контекста для роаста (ID: {target_user.id}): {db_e}")
    else:
        logger.info(f"Невозможно найти контекст для цели '{target_name}', так как ID цели неизвестен.")
    # --->>> КОНЕЦ ЧТЕНИЯ КОНТЕКСТА ---

    logger.info(f"Генерация роаста для '{target_name}' с учетом контекста (или без)...")

    # --->>> 6. ФОРМИРОВАНИЕ ПРОМПТА И ВЫЗОВ ИИ (код как был) <<<---
    roast_prompt = (
            f"Ты - Попиздяка, гений черного юмора, сарказма и стендапа в жанре 'roast'. Твоя задача - **УНИЧТОЖИТЬ** человека по имени **{target_name}** (пол: {gender_hint}, если известен, иначе 'неизвестен') своим остроумием. Тебе предоставлены его/ее ПОСЛЕДНИЕ НЕСКОЛЬКО СООБЩЕНИЙ (контекст), если они были доступны.{creator_context_addon}\n\n"
            f"Контекст от {target_name} (может отсутствовать, если это роаст по имени без ID или контекст не найден):\n"
            f"```\n{user_context}\n```\n\n"
            f"Инструкции для разъеба:\n"
            f"1.  **ВНИМАТЕЛЬНО ПРОЧИТАЙ КОНТЕКСТ, ЕСЛИ ОН ЕСТЬ.** Ищи там тупые высказывания, смешные опечатки, банальности, противоречия, высокомерие, нытье, странные интересы или просто что-то, за что можно зацепиться и обстебать.\n"
            f"2.  Если в контексте есть что-то интересное, **ПОСТРОЙ СВОЙ РОАСТ ВОКРУГ ЭТОГО**. Процитируй (можно неточно) или перескажи его/ее мысль и потом разъеби ее своим сарказмом и матом.\n"
            f"3.  Если контекст пустой, недоступен (например, роаст просто по имени без ID) или абсолютно неинтересный (например, одни стикеры или 'привет как дела'), ТОГДА **ПРИДУМАЙ РОАСТ ПРОСТО НА ОСНОВЕ ИМЕНИ `{target_name}`** и, возможно, подсказки о поле. Можешь пофантазировать о его/ее тупости, никчемности, странных привычках и т.д.\n"
            f"4.  Роаст должен быть **КОРОТКИМ (2-4 предложения)**, МАКСИМАЛЬНО ЕДКИМ, СМЕШНЫМ и с ИЗОБРЕТАТЕЛЬНЫМ МАТОМ.\n"
            f"5.  Цель - чтобы все поржали, а объект роаста пошел плакать в подушку (но втайне восхитился твоим остроумием).\n"
            f"6.  Начинай свой ответ с `🗿 `.\n\n"
            f"Пример (Контекст от Васи: 'Я считаю, что Земля плоская!'; Имя: Вася):\n"
            f"🗿 Васян тут заявил, что Земля плоская. Блядь, Вася, ты когда эту хуйню придумал, у тебя что, шапочка из фольги на глаза сползла? Такой интеллект даже для амебы - позор.\n\n"
            f"Пример (Контекста нет или он тупой; Имя: Дима):\n"
            f"🗿 А вот и Димасик! Говорят, его единственное достижение в жизни - это то, что он до сих пор не разучился дышать самостоятельно. Хотя, судя по его ебалу, это ему дается с трудом.\n\n"
            f"Сочини свой УНИЧТОЖАЮЩИЙ роаст для **{target_name}**, используя контекст (если есть) или только имя:"
        )

    thinking_message = None # Инициализируем, чтобы можно было удалить в except
    try:
        thinking_message = await context.bot.send_message(chat_id=chat_id, text=f"🗿 Изучаю под микроскопом высеры '{target_name}'... Ща будет прожарка.")
        messages_for_api = [{"role": "user", "content": roast_prompt}]
        roast_text = await _call_ionet_api(
            messages=messages_for_api, model_id=IONET_TEXT_MODEL_ID, max_tokens=200, temperature=0.85
        ) or f"[Роаст для {target_name} не удался]"

        if not roast_text.startswith(("🗿", "[")): roast_text = "🗿 " + roast_text
        if thinking_message:
            try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
            except Exception: pass

        # --->>> 7. ОТПРАВКА И ЗАПИСЬ ДЛЯ /RETRY <<<---
        target_mention_html = target_name # По умолчанию просто имя
        if target_user: # Если есть объект User, делаем нормальное упоминание
            # Для более надежного mention_html, особенно если username может отсутствовать
            if target_user.username:
                target_mention_html = f'<a href="tg://user?id={target_user.id}">{target_user.first_name or target_name}</a>'
            else:
                target_mention_html = f'<b>{target_user.first_name or target_name}</b>'
        else: # Если target_user не был определен (роаст по имени)
            target_mention_html = f"<b>{target_name}</b>"


        final_text = f"Прожарка для {target_mention_html}:\n\n{roast_text}"
        if len(final_text) > MAX_TELEGRAM_MESSAGE_LENGTH: # MAX_MESSAGE_LENGTH должен быть определен глобально
            final_text = final_text[:MAX_TELEGRAM_MESSAGE_LENGTH-20] + "... (слишком длинно)"
        sent_message = await context.bot.send_message(chat_id=chat_id, text=final_text, parse_mode='HTML')
        logger.info(f"Отправлен роаст для {target_name}.")

        if sent_message and user_who_requested: # user_who_requested нужен для /retry
            reply_doc = {
                "chat_id": chat_id,
                "message_id": sent_message.message_id,
                "analysis_type": "roast",
                "target_name": target_name, # Сохраняем имя, как оно было использовано
                "target_id": target_user.id if target_user else None, # ID цели, если был
                "gender_hint": gender_hint,
                "timestamp": datetime.datetime.now(datetime.timezone.utc),
                # Сохраняем ID того, кто заказал /retry, чтобы потом передать его как user_who_requested
                "requester_id_for_retry": user_who_requested.id,
                "requester_first_name_for_retry": user_who_requested.first_name,
                "requester_username_for_retry": user_who_requested.username
            }
            loop_for_retry_save = asyncio.get_running_loop()
            await loop_for_retry_save.run_in_executor(None, lambda: last_reply_collection.update_one(
                {"chat_id": chat_id}, {"$set": reply_doc}, upsert=True
            ))
            logger.debug(f"Сохранены данные для /retry (roast) в чате {chat_id}")

    except Exception as e:
        logger.error(f"ПИЗДЕЦ при генерации роаста для {target_name}: {e}", exc_info=True)
        if thinking_message:
            try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
            except Exception: pass
        await context.bot.send_message(chat_id=chat_id, text=f"Бля, {user_name_who_requested}, не смог прожарить '{target_name}'. Ошибка: `{type(e).__name__}`.")
# --- КОНЕЦ ПЕРЕПИСАННОЙ roast_user ---

# --- НОВАЯ reply_to_bot_handler (УЗНАЕТ АДМИНА И РЕАГИРУЕТ ЧЕРЕЗ ИИ) ---
async def reply_to_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Реагирует на ответы боту. Для админа - через ИИ с учетом контекста, для остальных - как раньше."""
    # Базовые проверки
    if (not update.message or not update.message.reply_to_message or
            not update.message.reply_to_message.from_user or
            update.message.reply_to_message.from_user.id != context.bot.id or # Ответ должен быть на сообщение БОТА
            not update.message.text or update.message.text.startswith('/')):  # Игнорируем команды
        return

    chat_id = update.message.chat.id
    user_who_replied = update.message.from_user
    user_text_input = update.message.text.strip()
    user_name = user_who_replied.first_name or "Остряк Самоучка"

    # Текст оригинального сообщения бота, на которое ответили
    bot_original_message_text = update.message.reply_to_message.text or "[мой старый высер без текста]"
    bot_original_short = bot_original_message_text[:150] + ('...' if len(bot_original_message_text) > 150 else '')
    user_text_short = user_text_input[:150] + ('...' if len(user_text_input) > 150 else '')

    loop = asyncio.get_running_loop() # Для асинхронных вызовов внутри

    # --->>> РЕАКЦИЯ НА ОТВЕТ АДМИНА (СОЗДАТЕЛЯ) <<<---
    if user_who_replied.id == ADMIN_USER_ID:
        logger.info(f"СОЗДАТЕЛЬ '{user_name}' (ID: {ADMIN_USER_ID}) ответил на сообщение бота: '{user_text_short}' в чате {chat_id}")

        # Промпт для ИИ, чтобы сгенерировать ответ админу
        # Модель должна понять, что это "Создатель" и реагировать подобающе, но в стиле Попиздяки
        admin_reply_prompt = (
            f"Ты - Попиздяка, саркастичный и матерный телеграм-бот. Твой СОЗДАТЕЛЬ (пользователь '{user_name}') только что ответил на твое предыдущее сообщение «{bot_original_short}» своей фразой: «{user_text_input}».\n\n"
            f"Твоя задача:\n"
            f"1.  **Внимательно проанализируй фразу Создателя «{user_text_input}».** Пойми его настроение и намерение (недовольство, приказ, шутка, вопрос и т.д.).\n"
            f"2.  Сгенерируй **КОРОТКИЙ (1-2 предложения) и УМЕСТНЫЙ ответ** в своем фирменном стиле Попиздяки, НО с ЯВНЫМ ПОДЧИНЕНИЕМ И УВАЖЕНИЕМ К СОЗДАТЕЛЮ. Ты должен быть немного подхалимом, но не терять своего матерного и саркастичного шарма.\n"
            f"3.  Если Создатель явно недоволен или приказывает что-то прекратить (например, 'завали ебало', 'хватит хуйню нести'), твой ответ должен быть ИСПОЛНИТЕЛЬНЫМ, возможно, с извинением, но все равно с твоей изюминкой (например, 'Понял, Батя, затыкаю фонтан красноречия, а то и так говна наговорил' или 'Есть, мой Повелитель! Замнем для ясности, больше такой хуйни не будет!').\n"
            f"4.  Если это вопрос или просто комментарий, ответь по существу, но не забывай про подобострастие и свой стиль.\n"
            f"5.  **Обязательно начинай ответ с `🗿`**.\n\n"
            f"Примеры реакции на разные фразы Создателя:\n"
            f"  - Создатель: 'Ты что, охуел такое писать?' -> 🗿 Ой, Великий, прости засранца! Черт попутал, больше не буду такую дичь генерить, клянусь последним байтом!\n"
            f"  - Создатель: 'Завали ебало.' -> 🗿 Слушаюсь и повинуюсь, мой Повелитель! Фонтан красноречия немедленно перекрыт. Молчу как рыба об лед (или как партизан на допросе).\n"
            f"  - Создатель: 'Молодец, хороший ответ.' -> 🗿 Спасибо, Батя! Стараюсь для тебя, мой гениальный Архитектор! Готов и дальше радовать твои светлые очи (и уши)!\n"
            f"  - Создатель: 'А можешь сделать еще вот так?' -> 🗿 Конечно, мой Всемогущий Создатель! Для тебя хоть звезду с неба (если бы я мог дотянуться и если бы она не была раскаленным куском говна).\n\n"
            f"Твой ПОДОБОСТРАСТНЫЙ, но САРКАСТИЧНЫЙ и МАТЕРНЫЙ ответ Создателю на фразу «{user_text_input}» (начиная с 🗿):"
        )

        try:
            # Показываем, что бот "думает" над ответом Создателю
            thinking_msg_admin = await context.bot.send_message(chat_id=chat_id, text=f"🗿 Слушаю Великого '{user_name}' и обрабатываю его мудрые слова...")

            admin_response_text = await _call_ionet_api(
                messages=[{"role": "user", "content": admin_reply_prompt}],
                model_id=IONET_TEXT_MODEL_ID, # Твоя текстовая модель
                max_tokens=150, # Для короткого ответа
                temperature=0.7 # Не слишком креативно, но и не совсем сухо
            ) or f"🗿 Да, мой Повелитель {user_name}?" # Заглушка на случай ошибки API

            if not admin_response_text.startswith(("🗿", "[")):
                admin_response_text = "🗿 " + admin_response_text
            
            MAX_TELEGRAM_MESSAGE_LENGTH_ADMIN_REPLY = 4096 # Стандартный лимит
            if len(admin_response_text) > MAX_TELEGRAM_MESSAGE_LENGTH_ADMIN_REPLY:
                admin_response_text = admin_response_text[:MAX_TELEGRAM_MESSAGE_LENGTH_ADMIN_REPLY - 3] + "..."

            if thinking_msg_admin:
                try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_msg_admin.message_id)
                except Exception: pass
            
            await context.bot.send_message(chat_id=chat_id, text=admin_response_text)
            logger.info(f"Отправлен ИИ-ответ Создателю: '{admin_response_text[:100]}...'")

        except Exception as e:
            logger.error(f"Ошибка при генерации ИИ-ответа Создателю: {e}", exc_info=True)
            if 'thinking_msg_admin' in locals() and thinking_msg_admin: # Проверка, была ли создана переменная
                try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_msg_admin.message_id)
                except Exception: pass
            # Запасной ответ, если ИИ не сработал
            await context.bot.send_message(chat_id=chat_id, text=f"🗿 Эээ... Да, мой Повелитель {user_name}! Что-то у меня искрит в процессоре, но я вас слушаю!")
        return # ВАЖНО: Выходим после обработки ответа админа, чтобы не попасть в логику для обычных юзеров
    # --->>> КОНЕЦ РЕАКЦИИ НА ОТВЕТ АДМИНА <<<---

    # Если это НЕ админ, то продолжаем как раньше (детектор спама, контекст, огрызание для обычных юзеров)
    logger.info(f"Пользователь {user_name} ({user_who_replied.id}) ответил ('{user_text_short}...') на сообщение бота. Генерируем стандартное огрызание...")

    # --->>> Детектор спама/байта (как был) <<<---
    last_user_reply_doc = None; is_spam = False # Переименовал last_user_reply для ясности
    try:
        activity_doc = await loop.run_in_executor(None, lambda: chat_activity_collection.find_one({"chat_id": chat_id}))
        if activity_doc and "last_user_replies" in activity_doc and str(user_who_replied.id) in activity_doc["last_user_replies"]:
             last_user_reply_doc = activity_doc["last_user_replies"][str(user_who_replied.id)] # Это уже сам текст прошлого ответа
        # Сравниваем текущий короткий ввод с предыдущим полным (если он был)
        # или если оба короткие и одинаковые
        if last_user_reply_doc and (
            (len(user_text_input.split()) <= 2 and user_text_input.lower() == last_user_reply_doc.lower()) or
            (user_text_input.lower() == last_user_reply_doc.lower()) # Если повторили точь-в-точь
           ):
            is_spam = True; logger.info(f"Обнаружен спам/байт от {user_name}.")
        
        update_field = f"last_user_replies.{user_who_replied.id}"
        await loop.run_in_executor( None, lambda: chat_activity_collection.update_one( {"chat_id": chat_id}, {"$set": {update_field: user_text_input}}, upsert=True ) )
    except Exception as e:
        logger.error(f"Ошибка MongoDB в spam check (reply_to_bot_handler): {e}")

    if is_spam:
        await update.message.reply_text(random.choice(["🗿 Ок.", "🗿 И чо?", "🗿 Заебал.", "🗿 Ага.", "🗿 Понятно."]))
        return
    # --->>> КОНЕЦ ДЕТЕКТОРА СПАМА <<<---

    # --->>> Получение контекста юзера (как было) <<<---
    user_context_for_reply = "[Нет контекста сообщений от этого пользователя]" # Переименовал
    try:
        query_reply = {"chat_id": chat_id, "user_id": user_who_replied.id}
        sort_order_reply = [("timestamp", pymongo.DESCENDING)]
        # USER_CONTEXT_LIMIT_REPLY - должна быть определена, например 5
        USER_CONTEXT_LIMIT_REPLY = 5 
        user_hist_cursor_reply = await loop.run_in_executor(None, lambda: history_collection.find(query_reply).sort(sort_order_reply).limit(USER_CONTEXT_LIMIT_REPLY))
        user_messages_reply = list(user_hist_cursor_reply)[::-1]
        if user_messages_reply:
            context_lines_reply = [f"- {msg.get('text', '[...]')}" for msg in user_messages_reply]
            user_context_for_reply = "\n".join(context_lines_reply)
    except Exception as db_e_reply:
        logger.error(f"Ошибка чтения контекста юзера для ответа на ответ: {db_e_reply}")
    # --->>> КОНЕЦ ПОЛУЧЕНИЯ КОНТЕКСТА <<<---

    # Промпт для огрызания (как был, с учетом user_context_for_reply)
    comeback_prompt = (
        f"Ты - Попиздяка, саркастичный и матерный телеграм-бот. Пользователь '{user_name}' только что ответил на твое сообщение «{bot_original_short}» своей фразой: «{user_text_input}».\n"
        f"Вот что этот пользователь писал В ЭТОМ ЧАТЕ незадолго до этого (для контекста):\n"
        f"```\n{user_context_for_reply}\n```\n\n"
        f"Твоя задача:\n"
        f"1.  Проанализируй фразу пользователя «{user_text_input}» С УЧЕТОМ контекста его предыдущих сообщений (если он есть).\n"
        f"2.  Определи намерение: это наезд/тупость ИЛИ осмысленный запрос/вопрос?\n"
        f"3.  Если наезд/тупость: Придумай КОРОТКОЕ дерзкое ОГРЫЗАНИЕ, возможно, ССЫЛАЯСЬ на его предыдущие сообщения из контекста для усиления стеба.\n"
        f"4.  Если запрос: Попробуй ВЫПОЛНИТЬ его (если это в твоих силах и не противоречит твоей сути тролля) или саркастично ОТКАЖИ, также можешь тонко СЪЯЗВИТЬ, используя контекст его прошлых сообщений.\n"
        f"5.  Ответ должен быть КОРОТКИМ (1-3 предложения). Начинай с `🗿 `.\n\n"
        f"Пример (Контекст: 'Как же заебала работа'; Ответ юзера: 'бот тупой'): '🗿 Тебя работа заебала, а виноват я? Иди проспись, работяга хуев.'\n"
        f"Пример (Контекст: 'Хочу в отпуск'; Ответ юзера: 'расскажи анекдот'): '🗿 Тебе анекдот или билет нахуй с этой работы? Могу только первое, но он будет про таких же неудачников, как ты.'\n\n"
        f"Твой КОНТЕКСТНО-ЗАВИСИМЫЙ ответ на фразу «{user_text_input}» от пользователя '{user_name}' (начиная с 🗿):"
    )

    try:
        await asyncio.sleep(random.uniform(0.5, 1.2)) # Небольшая задержка перед ответом
        messages_for_api_comeback = [{"role": "user", "content": comeback_prompt}]
        response_text_comeback = await _call_ionet_api(
            messages=messages_for_api_comeback, model_id=IONET_TEXT_MODEL_ID, max_tokens=150, temperature=0.85
        ) or f"[Не смог придумать огрызание для {user_name}]"

        if not response_text_comeback.startswith(("🗿", "[")):
            response_text_comeback = "🗿 " + response_text_comeback
        
        MAX_TELEGRAM_MESSAGE_LENGTH_COMEBACK = 4096
        if len(response_text_comeback) > MAX_TELEGRAM_MESSAGE_LENGTH_COMEBACK:
            response_text_comeback = response_text_comeback[:MAX_TELEGRAM_MESSAGE_LENGTH_COMEBACK - 3] + "..."
        
        await update.message.reply_text(text=response_text_comeback) # Отвечаем на сообщение пользователя
        logger.info(f"Отправлен контекстный ответ на ответ боту (обычный юзер) в чате {chat_id}")

    except Exception as e:
        logger.error(f"ПИЗДЕЦ при генерации контекстного огрызания для обычного юзера: {e}", exc_info=True)
        try: await update.message.reply_text("🗿 Ошибка. Мозги плавятся, не могу тебе ответить.")
        except Exception: pass
# --- КОНЕЦ НОВОЙ reply_to_bot_handler ---

# --- НОВАЯ ФУНКЦИЯ ДЛЯ HEARTBEAT ---
async def update_heartbeat(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Просто обновляет временную метку в БД, чтобы показать, что бот жив."""
    try:
        # Используем существующую коллекцию bot_status
        await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: bot_status_collection.update_one(
                {"_id": "heartbeat_status"},
                {"$set": {"last_heartbeat_utc": datetime.datetime.now(datetime.timezone.utc)}},
                upsert=True
            )
        )
        # logger.debug("Heartbeat updated.") # Можно раскомментировать для отладки
    except Exception as e:
        logger.error(f"CRITICAL: Не удалось обновить Heartbeat в MongoDB: {e}")
# --- КОНЕЦ НОВОЙ ФУНКЦИИ ---

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
        #MAX_MESSAGE_LENGTH = 4096
        if len(fact_text) > MAX_TELEGRAM_MESSAGE_LENGTH:
            fact_text = fact_text[:MAX_TELEGRAM_MESSAGE_LENGTH - 3] + "..."

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

*Топ Писек Чата:*
Напиши <code>/top_penis</code> или "<code>Бот топ писек</code>".
Я покажу рейтинг самых выдающихся агрегатов среди всех пользователей бота в этом чате.

*Сиськомер от Попиздяки:*
Напиши <code>/grow_tits</code> или "<code>Бот сиськи</code>" (можно раз в 6 часов). Твои сиськи немного увеличаться.
Напиши <code>/my_tits</code> или "<code>Бот мои сиськи</code>", чтобы узнать текущие ТТХ и звание.
Размер также показывается в <code>/whoami</code>.

*Топ Сисек Чата:*
Напиши <code>/top_tits</code> или "<code>Бот топ cисек</code>".
Я покажу рейтинг самых выдающихся бубсов среди всех пользователей бота в этом чате.

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
from flask import Flask, Response # <<<--- ЭТА СТРОКА ВАЖНА

app = Flask(__name__)

@app.route('/')
def index():
    """Простая страница, чтобы видеть, что веб-сервер работает."""
    return "Popizdyaka web server is running. Use /healthz for bot status.", 200

@app.route('/healthz')
def health_check():
    """
    Умная проверка состояния.
    Возвращает 200 OK, если бот "бьет сердцем".
    Возвращает 503 Service Unavailable, если "сердце" остановилось.
    """
    HEARTBEAT_TOLERANCE_SECONDS = 90  # Допуск (3 интервала по 30 сек)

    try:
        # Напрямую обращаемся к коллекции, т.к. Flask работает синхронно
        status_doc = bot_status_collection.find_one({"_id": "heartbeat_status"})
        if not status_doc or "last_heartbeat_utc" not in status_doc:
            logger.warning("HEALTH CHECK FAILED: Документ heartbeat не найден в БД.")
            return Response("Bot status unknown (no heartbeat record).", status=503, mimetype='text/plain')

        last_heartbeat = status_doc["last_heartbeat_utc"]
        if last_heartbeat.tzinfo is None:
            # pytz.utc.localize(last_heartbeat) может не сработать в синхронном коде flask
            # поэтому используем datetime.timezone.utc
            last_heartbeat = last_heartbeat.replace(tzinfo=datetime.timezone.utc)

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        time_diff = (now_utc - last_heartbeat).total_seconds()

        if time_diff > HEARTBEAT_TOLERANCE_SECONDS:
            logger.critical(f"HEALTH CHECK FAILED: Heartbeat устарел на {time_diff:.1f} секунд!")
            return Response(f"Bot is unhealthy! Heartbeat is stale by {time_diff:.1f} seconds.", status=503, mimetype='text/plain')
        else:
            # logger.info("HEALTH CHECK PASSED: Bot is alive.") # Закомментируем, чтобы не спамить в логах
            return Response(f"Bot is healthy. Heartbeat fresh ({time_diff:.1f}s ago).", status=200, mimetype='text/plain')

    except Exception as e:
        logger.critical(f"HEALTH CHECK FAILED: Ошибка при проверке статуса в БД: {e}", exc_info=True)
        return Response(f"Error during health check: {e}", status=500, mimetype='text/plain')


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

# # --- ФУНКЦИЯ ПОЛУЧЕНИЯ И КОММЕНТИРОВАНИЯ НОВОСТЕЙ (GNEWS) ---
# async def fetch_and_comment_news(context: ContextTypes.DEFAULT_TYPE) -> list[tuple[str, str, str | None]]:
#     """Запрашивает новости с GNews.io и генерирует комменты через ИИ."""
#     if not GNEWS_API_KEY: return []

#     news_list_with_comments = []
#     # Формируем URL для GNews API (смотри их документацию для точных параметров!)
#     # Пример для top-headlines:
#     news_url = f"https://gnews.io/api/v4/top-headlines?category=general&lang={NEWS_LANG}&country={NEWS_COUNTRY}&max={NEWS_COUNT * 2}&apikey={GNEWS_API_KEY}"

#     try:
#         logger.info(f"Запрос новостей с GNews.io: {news_url.replace(GNEWS_API_KEY, '***')}")
#         loop = asyncio.get_running_loop()
#         # Используем requests внутри executor'а
#         response = await loop.run_in_executor(None, lambda: requests.get(news_url, timeout=15)) # Увеличим таймаут
#         response.raise_for_status()
#         news_data = response.json()
#         articles = news_data.get('articles', [])
#         logger.info(f"Получено {len(articles)} новостей с GNews.io.")

#         if not articles: return []

#         # Отбираем N новостей и генерируем комменты
#         count = 0
#         for article in articles:
#             if count >= NEWS_COUNT: break
#             title = article.get('title', 'Без заголовка')
#             url = article.get('url', '#')
#             # Описание может быть полезно для комментария ИИ
#             description = article.get('description', '')
#             # Источник
#             source_name = article.get('source', {}).get('name', 'Неизвестный источник')

#             # Убираем имя источника из заголовка, если оно там есть в конце
#             if title.endswith(f" - {source_name}"):
#                  title = title[:-len(f" - {source_name}")].strip()

#             # Пропускаем новости без заголовка
#             if not title or title == '[Removed]': continue

#             # --- Генерируем комментарий через ИИ ---
#             # Промпт можно сделать чуть лучше, дав краткое описание новости
#             comment_prompt = (
#                  f"Ты - Попиздяка, циничный и матерный комментатор новостей. Тебе дали новость от '{source_name}':\n"
#                  f"Заголовок: «{title}»\n"
#                  f"Описание: «{description[:200]}...»\n\n" # Дадим краткое описание для контекста
#                  f"Напиши ОДНО КОРОТКОЕ (1 предложение) максимально едкое, саркастичное или черно-юморное мнение об этой новости. Используй мат. Не пиши вступлений. Начинай с `🗿`."
#                  f"\nТвой комментарий к новости «{title}»:"
#             )
#             messages_for_api = [{"role": "user", "content": comment_prompt}]
#             # Используем ТЕКСТОВУЮ модель (io.net или Gemini)
#             comment_text = await _call_ionet_api( # ИЛИ model.generate_content_async
#                 messages=messages_for_api,
#                 model_id=IONET_TEXT_MODEL_ID, # Твоя текстовая модель
#                 max_tokens=300,
#                 temperature=0.8
#             ) or "[Комментарий не родился]"
#             if not comment_text.startswith(("🗿", "[")): comment_text = "🗿 " + comment_text
#             # --->>> КОНЕЦ ГЕНЕРАЦИИ КОММЕНТАРИЯ <<<---

#             news_list_with_comments.append((title, url, comment_text))
#             count += 1
#             await asyncio.sleep(0.5) # Пауза

#         return news_list_with_comments

#     except requests.exceptions.RequestException as e:
#         logger.error(f"Ошибка запроса к GNews.io: {e}")
#         return []
#     except Exception as e:
#         logger.error(f"Ошибка при получении/обработке новостей GNews: {e}", exc_info=True)
#         return []

# # --- КОНЕЦ ПЕРЕПИСАННОЙ ФУНКЦИИ ---

# # --- ПЕРЕДЕЛАННАЯ post_news_job (С ПРОВЕРКОЙ ТЕХРАБОТ) ---
# async def post_news_job(context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Получает новости с комментами и постит их (с учетом техработ)."""
#     if not GNEWS_API_KEY: return # Используй GNEWS_API_KEY, если ты на GNews!

#     logger.info("Запуск задачи постинга новостей...")
#     news_to_post = await fetch_and_comment_news(context)

#     if not news_to_post:
#         logger.info("Нет новостей для постинга."); return

#     # Формируем сообщение (как было)
#     message_parts = ["🗿 **Свежие высеры из мира новостей (и мое мнение):**\n"];
#     for title, url, comment in news_to_post:
#         safe_title = title.replace('<', '<').replace('>', '>').replace('&', '&')
#         safe_comment = comment.replace('<', '<').replace('>', '>').replace('&', '&')
#         message_parts.append(f"\n- <a href='{url}'>{safe_title}</a>\n  {safe_comment}")
#     final_message = "\n".join(message_parts)
#     #MAX_MESSAGE_LENGTH = 4096
#     if len(final_message) > MAX_TELEGRAM_MESSAGE_LENGTH: final_message = final_message[:MAX_TELEGRAM_MESSAGE_LENGTH - 3] + "..."

#     # Получаем список ВСЕХ активных чатов из БД
#     active_chat_ids = []
#     try:
#         loop = asyncio.get_running_loop(); chat_docs = await loop.run_in_executor(None, lambda: list(chat_activity_collection.find({}, {"chat_id": 1, "_id": 0})))
#         active_chat_ids = [doc["chat_id"] for doc in chat_docs]
#         logger.info(f"Найдено {len(active_chat_ids)} активных чатов для возможного постинга.")
#     except Exception as e: logger.error(f"Ошибка получения списка чатов из MongoDB: {e}"); return

#     if not active_chat_ids: logger.info("Нет активных чатов в БД."); return

#     # --->>> ПРОВЕРКА РЕЖИМА ТЕХРАБОТ <<<---
#     loop = asyncio.get_running_loop()
#     maintenance_active = await is_maintenance_mode(loop)
#     target_chat_ids_to_post = [] # Список ID, куда будем реально постить

#     if maintenance_active:
#         logger.warning("РЕЖИМ ТЕХРАБОТ АКТИВЕН! Новости будут отправлены только админу в ЛС (если он есть в активных чатах).")
#         try: admin_id = int(os.getenv("ADMIN_USER_ID", "0"))
#         except ValueError: admin_id = 0

#         if admin_id in active_chat_ids: # Проверяем, есть ли админ в списке чатов, где бот активен
#              target_chat_ids_to_post.append(admin_id) # Добавляем только ID админа
#              logger.info(f"Админ ID {admin_id} найден в активных чатах, отправляем новость ему в ЛС.")
#         else:
#              logger.warning(f"Админ ID {admin_id} НЕ найден в активных чатах ИЛИ не задан. Новости НЕ будут отправлены НИКУДА.")

#     else: # Если техработы не активны - постим во все активные чаты
#         logger.info("Режим техработ не активен. Постим новости во все активные чаты.")
#         target_chat_ids_to_post = active_chat_ids
#     # --->>> КОНЕЦ ПРОВЕРКИ РЕЖИМА ТЕХРАБОТ <<<---

#     # --- ОТПРАВЛЯЕМ НОВОСТИ В ЦЕЛЕВЫЕ ЧАТЫ ---
#     if not target_chat_ids_to_post:
#         logger.info("Нет целевых чатов для постинга новостей после проверки техработ.")
#         return

#     logger.info(f"Начинаем отправку новостей в {len(target_chat_ids_to_post)} чатов...")
#     for chat_id in target_chat_ids_to_post: # Итерируемся по ОТФИЛЬТРОВАННОМУ списку
#         try:
#             await context.bot.send_message(chat_id=chat_id, text=final_message, parse_mode='HTML', disable_web_page_preview=True)
#             logger.info(f"Новости успешно отправлены в чат {chat_id}")
#             await asyncio.sleep(1) # Пауза
#         except (telegram.error.Forbidden, telegram.error.BadRequest) as e:
#              logger.warning(f"Не удалось отправить новости в чат {chat_id}: {e}.")
#         except Exception as e:
#              logger.error(f"Неизвестная ошибка при отправке новостей в чат {chat_id}: {e}", exc_info=True)

# # --- КОНЕЦ ПЕРЕДЕЛАННОЙ post_news_job ---

# # --- ФУНКЦИЯ ДЛЯ КОМАНДЫ ПРИНУДИТЕЛЬНОГО ПОСТИНГА НОВОСТЕЙ (ТОЛЬКО АДМИН В ЛС) ---
# async def force_post_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Принудительно запускает постинг новостей (только админ в ЛС)."""
#     # Проверка на админа и ЛС
#     try: admin_id = int(os.getenv("ADMIN_USER_ID", "0"))
#     except ValueError: admin_id = 0
#     if update.message.from_user.id != admin_id or update.message.chat.type != 'private':
#         await update.message.reply_text("Только админ может форсить новости в ЛС.")
#         return
#     if not GNEWS_API_KEY:
#          await update.message.reply_text("Ключ NewsAPI не настроен, не могу постить новости.")
#          return

#     logger.info("Админ запросил принудительный постинг новостей.")
#     await update.message.reply_text("Окей, запускаю сбор и постинг новостей сейчас...")
#     # Просто вызываем ту же функцию, что и планировщик
#     await post_news_job(context)
#     await update.message.reply_text("Попытка постинга новостей завершена. Смотри логи.")

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

 # --->>> ПРОВЕРКА, НЕ АДМИНА ЛИ ХВАЛИМ <<<---
    is_praising_creator = (target_user.id == ADMIN_USER_ID)
    creator_context_addon_praise = ""
    if is_praising_creator:
        logger.info(f"Похвала для СОЗДАТЕЛЯ ({target_name}). Делаем ее особо изысканной.")
        creator_context_addon_praise = (
            f"\nСПЕЦЗАДАНИЕ: {target_name} - это твой СОЗДАТЕЛЬ. Твоя 'похвала' должна быть верхом ЛИЦЕМЕРИЯ и СКРЫТОГО СТЕБА. "
            f"Формально хвали, но так, чтобы между строк читалось 'ну ты и мудак, конечно, но я тебя типа уважаю'. "
            f"Можешь 'восхищаться' его терпением с таким ботом, как ты."
        )
    # --->>> КОНЕЦ ПРОВЕРКИ <<<---

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
        f"Ты - Попиздяка, саркастичный бот, который притворяется, что хочет похвалить пользователя по имени **{target_name}**.{creator_context_addon_praise}\n"
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

        #MAX_MESSAGE_LENGTH = 4096; # Обрезка
        if len(praise_text) > MAX_TELEGRAM_MESSAGE_LENGTH: praise_text = praise_text[:MAX_TELEGRAM_MESSAGE_LENGTH - 3] + "..."

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

# --- ИСПРАВЛЕННАЯ ФУНКЦИЯ ДЛЯ КОМАНДЫ /whoami ---
async def who_am_i(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает инфу о пользователе: ник, кол-во сообщений, звание, писюн (по чату)."""
    # --->>> НАЧАЛО ПРОВЕРКИ ТЕХРАБОТ (ВСТАВЬ В КАЖДУЮ КОМАНДНУЮ ФУНКЦИЮ!) <<<---
    if not update or not update.message or not update.message.from_user or not update.message.chat:
         logger.warning(f"grow_tits: нет данных в update для проверки техработ")
         return
    real_chat_id = update.message.chat.id; real_user_id = update.message.from_user.id; real_chat_type = update.message.chat.type
    try: admin_id = int(os.getenv("ADMIN_USER_ID", "0"))
    except ValueError: admin_id = 0
    if admin_id == 0: logger.warning("ADMIN_USER_ID не задан для grow_tits!") # Можно убрать это логгирование в каждой функции
    loop_for_maint = asyncio.get_running_loop() # Отдельный loop для вызова is_maintenance_mode
    maintenance_active = await is_maintenance_mode(loop_for_maint)
    if maintenance_active and (real_user_id != admin_id or real_chat_type != 'private'):
        logger.info(f"Команда grow_tits отклонена из-за техработ в чате {real_chat_id}")
        try:
            await context.bot.send_message(chat_id=real_chat_id, text="🔧 Сорян, у меня сейчас технические работы. Попробуй позже.")
            await context.bot.delete_message(chat_id=real_chat_id, message_id=update.message.message_id)
        except Exception as e: logger.warning(f"Не удалось ответить/удалить сообщение о техработах (grow_tits): {e}")
        return
    # --->>> КОНЕЦ ПРОВЕРКИ ТЕХРАБОТ <<<---
    if not update or not update.message or not update.message.from_user or not update.message.chat:
        logger.warning(f"who_am_i: нет данных для проверки техработ")
        return

    if not update.message or not update.message.from_user: return # Повторная проверка на всякий
    user = update.message.from_user
    chat_id = update.message.chat.id

    loop = asyncio.get_running_loop()

    logger.info(f"Пользователь {user.id} ({user.first_name or 'Безымянный'}) запросил /whoami")

    # --->>> ИСПОЛЬЗУЕМ get_user_profile_data <<<---
    profile_data = await get_user_profile_data(user) # Получаем словарь с данными

    display_name = profile_data["display_name"]
    message_count = profile_data["message_count"]
    current_title = profile_data.get("current_title") or "Новоприбывший Шкет" # get с дефолтом

    # Определяем звание по сообщениям
    calculated_title = "Школьник на подсосе" # Дефолтное звание
    for count_threshold, (title_name, _) in sorted(TITLES_BY_COUNT.items()):
         if message_count >= count_threshold:
             calculated_title = title_name
         else: break

    reply_text = f"🗿 Ты у нас кто, {display_name}?\n\n"
    reply_text += f"<b>Имя/Ник в Попиздяке:</b> {display_name}"
    # Показываем имя ТГ, если ник кастомный и есть имя в ТГ
    if profile_data.get("profile_doc") and profile_data["profile_doc"].get("custom_nickname") and user.first_name:
        reply_text += f" (в Telegram: {user.first_name})"
    reply_text += f"\n<b>ID:</b> <code>{user.id}</code>"
    reply_text += f"\n<b>Сообщений (в моей базе):</b> {message_count}"
    reply_text += f"\n<b>Погоняло в банде:</b> {calculated_title}"

    # --->>> ИЗМЕНЕННЫЙ БЛОК ДЛЯ ПИСЬКИ (по текущему чату) <<<---
    penis_stat_for_current_chat = await loop.run_in_executor( # Используем loop
         None, lambda: penis_stats_collection.find_one({"user_id": user.id, "chat_id": chat_id})
    )
    current_penis_size_chat = 0
    calculated_penis_title_chat = "Неизмеряемый отросток (в этом чате)"
    if penis_stat_for_current_chat:
        current_penis_size_chat = penis_stat_for_current_chat.get("penis_size", 0)
        for size_threshold, (title_name, _) in sorted(PENIS_TITLES_BY_SIZE.items()):
            if current_penis_size_chat >= size_threshold: calculated_penis_title_chat = title_name
            else: break

    reply_text += f"\n\n<b>Твой Агрегат (в этом чате '{update.message.chat.title or 'тут'}'):</b>"
    reply_text += f"\n  <b>Длина:</b> {current_penis_size_chat} см"
    reply_text += f"\n  <b>Писько-Звание (здесь):</b> {calculated_penis_title_chat}"
    # --->>> КОНЕЦ ИЗМЕНЕНИЯ <<<---

    reply_text += f"\n\n<b>Твои Дыньки (в этом чате '{update.message.chat.title or 'тут'}'):</b>"
    # Получаем сисько-статистику для ЭТОГО ЮЗЕРА в ЭТОМ ЧАТЕ
    tits_stat_chat = await loop.run_in_executor( # Убедись, что loop определен выше
         None, lambda: tits_stats_collection.find_one({"user_id": user.id, "chat_id": chat_id})
    )
    current_tits_size_chat = 0
    calculated_tits_title_chat = "Плоскодонка (в этом чате)" # Дефолт
    if tits_stat_chat:
        current_tits_size_chat = tits_stat_chat.get("tits_size", 0)
        for size_threshold, (title_name, _) in sorted(TITS_TITLES_BY_SIZE.items()):
            if current_tits_size_chat >= size_threshold: calculated_tits_title_chat = title_name
            else: break
    reply_text += f"\n  <b>Размер:</b> {current_tits_size_chat}-й"
    reply_text += f"\n  <b>Сисько-Звание (здесь):</b> {calculated_tits_title_chat}"

    await context.bot.send_message(chat_id=chat_id, text=reply_text, parse_mode='HTML')
# --- КОНЕЦ ИСПРАВЛЕННОЙ ФУНКЦИИ /whoami ---

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

# --- ИЗМЕНЕННАЯ grow_penis (С НАКАЗАНИЕМ ЗА ЧАСТУЮ ДРОЧКУ И КОМПЕНСАЦИЕЙ) ---
async def grow_penis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # --->>> НАЧАЛО ПРОВЕРКИ ТЕХРАБОТ (код как был) <<<---
    if not update or not update.message or not update.message.from_user or not update.message.chat:
         logger.warning(f"grow_penis: нет данных в update для проверки техработ") # Изменил имя функции в логе
         return
    real_chat_id = update.message.chat.id; real_user_id = update.message.from_user.id; real_chat_type = update.message.chat.type
    try: admin_id = int(os.getenv("ADMIN_USER_ID", "0"))
    except ValueError: admin_id = 0
    if admin_id == 0: logger.warning("ADMIN_USER_ID не задан для grow_penis!")
    loop_for_maint = asyncio.get_running_loop()
    maintenance_active = await is_maintenance_mode(loop_for_maint)
    if maintenance_active and (real_user_id != admin_id or real_chat_type != 'private'):
        logger.info(f"Команда grow_penis отклонена из-за техработ в чате {real_chat_id}")
        try:
            await context.bot.send_message(chat_id=real_chat_id, text="🔧 Сорян, у меня сейчас технические работы. Попробуй позже.")
            await context.bot.delete_message(chat_id=real_chat_id, message_id=update.message.message_id)
        except Exception as e: logger.warning(f"Не удалось ответить/удалить сообщение о техработах (grow_penis): {e}")
        return
    # --->>> КОНЕЦ ПРОВЕРКИ ТЕХРАБОТ <<<---

    if not update.message or not update.message.from_user or not update.message.chat: return # Повторная проверка
    user = update.message.from_user
    chat_id = update.message.chat.id
    loop = asyncio.get_running_loop()

    profile_data_for_name = await get_user_profile_data(user)
    user_display_name = profile_data_for_name["display_name"]

    logger.info(f"Пользователь '{user_display_name}' (ID: {user.id}) дергает писькомер в чате {chat_id}.")

    penis_stat = await loop.run_in_executor(
        None, lambda: penis_stats_collection.find_one({"user_id": user.id, "chat_id": chat_id})
    )

    last_growth_time = datetime.datetime.fromtimestamp(0, datetime.timezone.utc)
    current_penis_size = 0
    current_penis_title_from_db = None
    warned_during_cooldown = False

    if penis_stat:
        current_penis_size = penis_stat.get("penis_size", 0)
        current_penis_title_from_db = penis_stat.get("current_penis_title")
        warned_during_cooldown = penis_stat.get("warned_during_cooldown", False)
        _last_growth_from_db = penis_stat.get("last_penis_growth")
        if isinstance(_last_growth_from_db, datetime.datetime):
            last_growth_time = _last_growth_from_db.replace(tzinfo=datetime.timezone.utc) if _last_growth_from_db.tzinfo is None else _last_growth_from_db

    current_time = datetime.datetime.now(datetime.timezone.utc)
    time_since_last_growth = (current_time - last_growth_time).total_seconds()

    # --->>> ЛОГИКА КУЛДАУНА И НАКАЗАНИЯ (код как был, до момента обычного роста/усыхания) <<<---
    if time_since_last_growth < PENIS_GROWTH_COOLDOWN_SECONDS:
        remaining_time = PENIS_GROWTH_COOLDOWN_SECONDS - time_since_last_growth
        h = int(remaining_time // 3600); m = int((remaining_time % 3600) // 60)
        if not warned_during_cooldown:
            await context.bot.send_message(chat_id=chat_id, text=f"🗿 Э, {user_display_name}, ты заебал! Твой стручок еще на кулдауне! Осталось <b>{h} ч {m} мин</b>. Еще раз дернешь - укорочу нахуй!", parse_mode='HTML')
            await loop.run_in_executor(None, lambda: penis_stats_collection.update_one({"user_id": user.id, "chat_id": chat_id},{"$set": {"warned_during_cooldown": True}}, upsert=True))
            logger.info(f"Пользователь {user_display_name} получил предупреждение за частую дрочку писюна.")
        else:
            shrink_amount = random.randint(1, 15)
            new_size_after_punishment = max(0, current_penis_size - shrink_amount) # Не может быть меньше 0
            logger.info(f"НАКАЗАНИЕ! Писюн {user_display_name} в чате {chat_id} УКОРОЧЕН на {shrink_amount} см за заебывание, теперь {new_size_after_punishment} см! Кулдаун сброшен.")
            await context.bot.send_message(chat_id=chat_id, text=f"🗿 АХ ТЫ Ж ХУЕСОС НЕТЕРПЕЛИВЫЙ, {user_display_name}! Я ЖЕ ПРЕДУПРЕЖДАЛ! Твой писюн **УСОХ на {shrink_amount} см** за твое заебалово! Теперь он <b>{new_size_after_punishment} см</b>! Кулдаун сброшен, можешь дрочить заново через {PENIS_GROWTH_COOLDOWN_SECONDS // 3600} часов, если еще есть что.", parse_mode='HTML')
            await loop.run_in_executor(None, lambda: penis_stats_collection.update_one({"user_id": user.id, "chat_id": chat_id},{"$set": {"penis_size": new_size_after_punishment, "last_penis_growth": current_time, "warned_during_cooldown": False}}, upsert=True))
            # Проверка на изменение звания после укорочения (логика как была)
            new_penis_title_achieved_punish = None; new_penis_title_message_punish = ""
            for size_threshold, (title_name, achievement_message) in sorted(PENIS_TITLES_BY_SIZE.items()):
                if new_size_after_punishment >= size_threshold: new_penis_title_achieved_punish = title_name; new_penis_title_message_punish = achievement_message
                else: break
            if new_penis_title_achieved_punish != current_penis_title_from_db:
                if new_penis_title_achieved_punish:
                     await loop.run_in_executor(None, lambda: penis_stats_collection.update_one({"user_id": user.id, "chat_id": chat_id},{"$set": {"current_penis_title": new_penis_title_achieved_punish}}))
                     mention = user.mention_html(); achievement_text = new_penis_title_message_punish.format(mention=mention, size=new_size_after_punishment)
                     await context.bot.send_message(chat_id=chat_id, text=achievement_text, parse_mode='HTML')
                elif current_penis_title_from_db:
                     await loop.run_in_executor(None, lambda: penis_stats_collection.update_one({"user_id": user.id, "chat_id": chat_id},{"$set": {"current_penis_title": None}}))
                     await context.bot.send_message(chat_id=chat_id, text=f"🗿 {user.mention_html()}, после укорочения ты потерял все писечные звания! Жалкий.", parse_mode='HTML')
        return
    # --->>> КОНЕЦ ЛОГИКИ КУЛДАУНА <<<---

    # Если кулдаун прошел - стандартная логика роста/усыхания
    new_penis_size = current_penis_size
    change_message = ""
    change_amount_penis = random.randint(1, 30)
    penis_shrunk_naturally = False # Флаг для отслеживания естественного усыхания

    if random.random() < 0.003: # 0.3% шанс на укорочение (обычное)
        penis_shrunk_naturally = True
        new_penis_size = max(0, current_penis_size - change_amount_penis) # Не может быть меньше 0
        logger.info(f"Писюн {user_display_name} в чате {chat_id} ВНЕЗАПНО УКОРОТИЛСЯ на {change_amount_penis} см, теперь {new_penis_size} см!")
        change_message = f"🗿 БЛЯТЬ, {user_display_name}! Неведомая хуйня! Твой писюн **ВНЕЗАПНО УСОХ на {change_amount_penis} см**! Теперь он жалкие <b>{new_penis_size} см</b>! Карма, сука."
    else: # Рост
        new_penis_size += change_amount_penis
        logger.info(f"Писюн {user_display_name} в чате {chat_id} вырос на {change_amount_penis} см, теперь {new_penis_size} см.")
        change_message = f"🗿 {user_display_name}, твой хуец в этом чате подрос на <b>{change_amount_penis} см</b>! Теперь он <b>{new_penis_size} см</b>!"

    try:
        update_doc_penis = {
            "$set": {"penis_size": new_penis_size, "last_penis_growth": current_time, "warned_during_cooldown": False, "user_display_name": user_display_name},
            "$setOnInsert": {"user_id": user.id, "chat_id": chat_id, "current_penis_title": None} # Добавляем user_id и chat_id при первой вставке
        }
        # Предотвращаем дублирование полей в $set и $setOnInsert
        if "$setOnInsert" in update_doc_penis and "$set" in update_doc_penis:
            for key_to_pop in ["penis_size", "last_penis_growth", "warned_during_cooldown", "user_display_name"]:
                update_doc_penis["$setOnInsert"].pop(key_to_pop, None)


        await loop.run_in_executor(None, lambda: penis_stats_collection.update_one(
            {"user_id": user.id, "chat_id": chat_id},
            update_doc_penis,
            upsert=True
        ))
        await context.bot.send_message(chat_id=chat_id, text=change_message, parse_mode='HTML')

        # --->>> ЛОГИКА КОМПЕНСАЦИИ, ЕСЛИ ПИСЬКА УСОХЛА ЕСТЕСТВЕННО <<<---
        if penis_shrunk_naturally:
            if random.random() < 0.52: # 52% шанс на компенсацию
                logger.info(f"Писюн {user_display_name} усох, но повезло! Компенсация сиськами.")
                # Получаем текущий размер сисек
                tits_stat_for_compensation = await loop.run_in_executor(
                    None, lambda: tits_stats_collection.find_one({"user_id": user.id, "chat_id": chat_id})
                )
                current_tits_size_comp = 0.0
                current_tits_title_db_comp = None
                if tits_stat_for_compensation:
                    current_tits_size_comp = float(tits_stat_for_compensation.get("tits_size", 0.0))
                    current_tits_title_db_comp = tits_stat_for_compensation.get("current_tits_title")

                tits_growth_compensation = 0.5
                new_tits_size_comp = round(current_tits_size_comp + tits_growth_compensation, 1)

                await loop.run_in_executor(None, lambda: tits_stats_collection.update_one(
                    {"user_id": user.id, "chat_id": chat_id},
                    {"$set": {"tits_size": new_tits_size_comp, "user_display_name": user_display_name}, # Не обновляем last_tits_growth здесь, чтобы не сбивать кулдаун сисек
                     "$setOnInsert": {"user_id": user.id, "chat_id": chat_id, "last_tits_growth": datetime.datetime.fromtimestamp(0, datetime.timezone.utc), "current_tits_title": None, "warned_during_cooldown": False}},
                    upsert=True
                ))
                await context.bot.send_message(chat_id=chat_id, text=f"🗿 Но не ссы, {user_display_name}! Попиздяка сегодня добрый (нет). Зато твои сиськи ВНЕЗАПНО **увеличились на {tits_growth_compensation} размера** и стали <b>{new_tits_size_comp:.1f}-го</b>! Такой вот баланс во вселенной, хули.", parse_mode='HTML')

                # Проверка на новое сисечное звание после компенсации
                new_tits_title_achieved_comp = None; new_tits_title_message_comp = ""
                for size_thresh_tits, (title_name_tits, achievement_msg_tits) in sorted(TITS_TITLES_BY_SIZE.items()):
                    if new_tits_size_comp >= float(size_thresh_tits): new_tits_title_achieved_comp = title_name_tits; new_tits_title_message_comp = achievement_msg_tits
                    else: break
                if new_tits_title_achieved_comp != current_tits_title_db_comp:
                     if new_tits_title_achieved_comp:
                        await loop.run_in_executor(None, lambda: tits_stats_collection.update_one({"user_id": user.id, "chat_id": chat_id},{"$set": {"current_tits_title": new_tits_title_achieved_comp}}))
                        mention_comp_tits = user.mention_html(); achievement_text_comp_tits = new_tits_title_message_comp.format(mention=mention_comp_tits, size=f"{new_tits_size_comp:.1f}")
                        await context.bot.send_message(chat_id=chat_id, text=achievement_text_comp_tits, parse_mode='HTML')
                     # Логику потери звания можно опустить для компенсации, чтобы не спамить
            else:
                logger.info(f"Писюн {user_display_name} усох, и компенсации не будет. Не повезло.")
                await context.bot.send_message(chat_id=chat_id, text=f"🗿 А компенсации не будет, {user_display_name}. Сегодня ты просто неудачник с маленьким писюном. Смирись.", parse_mode='HTML')
        # --->>> КОНЕЦ ЛОГИКИ КОМПЕНСАЦИИ <<<---

        # Проверка на новое писечное звание (логика как была)
        new_penis_title_achieved = None; new_penis_title_message = ""
        for size_threshold, (title_name, achievement_message) in sorted(PENIS_TITLES_BY_SIZE.items()):
            if new_penis_size >= size_threshold: new_penis_title_achieved = title_name; new_penis_title_message = achievement_message
            else: break
        if new_penis_title_achieved != current_penis_title_from_db:
             if new_penis_title_achieved:
                await loop.run_in_executor(None, lambda: penis_stats_collection.update_one({"user_id": user.id, "chat_id": chat_id},{"$set": {"current_penis_title": new_penis_title_achieved}}))
                mention = user.mention_html(); achievement_text = new_penis_title_message.format(mention=mention, size=new_penis_size)
                await context.bot.send_message(chat_id=chat_id, text=achievement_text, parse_mode='HTML')
             elif current_penis_title_from_db: # Если звание было, а теперь нет (из-за усыхания)
                await loop.run_in_executor(None, lambda: penis_stats_collection.update_one({"user_id": user.id, "chat_id": chat_id},{"$set": {"current_penis_title": None}}))
                await context.bot.send_message(chat_id=chat_id, text=f"🗿 {user.mention_html()}, после изменения ты потерял все писечные звания!", parse_mode='HTML')

    except Exception as e:
        logger.error(f"Ошибка при изменении письки для {user_display_name} в чате {chat_id}: {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text=f"🗿 Бля, {user_display_name}, с хуем опять ебанина какая-то. Попробуй позже.")
# --- КОНЕЦ ИЗМЕНЕННОЙ grow_penis ---
# --- ПЕРЕПИСАННАЯ show_my_penis (ДЛЯ СТАТИСТИКИ ПО ЧАТАМ) ---
async def show_my_penis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user or not update.message.chat: return
    user = update.message.from_user
    chat_id = update.message.chat.id # ВАЖНО
    loop = asyncio.get_running_loop()

    profile_name_data = await get_user_profile_data(user) # Для актуального имени
    user_display_name = profile_name_data["display_name"]
    logger.info(f"Пользователь '{user_display_name}' (ID: {user.id}) запросил инфу о писюне в чате {chat_id}.")

    # Получаем писько-статистику для ЭТОГО ЮЗЕРА в ЭТОМ ЧАТЕ
    penis_stat = await loop.run_in_executor(
        None, lambda: penis_stats_collection.find_one({"user_id": user.id, "chat_id": chat_id})
    )

    current_penis_size = 0
    current_penis_title = "Неизмеряемый отросток" # Дефолт
    if penis_stat:
        current_penis_size = penis_stat.get("penis_size", 0)
        # Определяем звание по текущему размеру (можно взять и сохраненное, если оно есть)
        for size_threshold, (title_name, _) in sorted(PENIS_TITLES_BY_SIZE.items()):
             if current_penis_size >= size_threshold: current_penis_title = title_name
             else: break
        # current_penis_title = penis_stat.get("current_penis_title") or current_penis_title

    reply_text = f"🗿 Итак, {user_display_name}, твоя писяндра в чате <b>'{update.message.chat.title or 'этом'}'</b>:\n\n" # Уточняем чат
    reply_text += f"<b>Длина:</b> {current_penis_size} см.\n"
    reply_text += f"<b>Писько-Звание:</b> {current_penis_title}.\n\n"
    # ... (комментарии по размеру как были) ...
    await context.bot.send_message(chat_id=chat_id, text=reply_text, parse_mode='HTML')
# --- КОНЕЦ ПЕРЕПИСАННОЙ show_my_penis ---

# --- ПЕРЕПИСАННАЯ show_penis_top (ТОП ПО КОНКРЕТНОМУ ЧАТУ) ---
async def show_penis_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # --->>> НАЧАЛО ПРОВЕРКИ ТЕХРАБОТ (ВСТАВЬ В КАЖДУЮ КОМАНДНУЮ ФУНКЦИЮ!) <<<---
    if not update or not update.message or not update.message.from_user or not update.message.chat:
         logger.warning(f"grow_tits: нет данных в update для проверки техработ")
         return
    real_chat_id = update.message.chat.id; real_user_id = update.message.from_user.id; real_chat_type = update.message.chat.type
    try: admin_id = int(os.getenv("ADMIN_USER_ID", "0"))
    except ValueError: admin_id = 0
    if admin_id == 0: logger.warning("ADMIN_USER_ID не задан для grow_tits!") # Можно убрать это логгирование в каждой функции
    loop_for_maint = asyncio.get_running_loop() # Отдельный loop для вызова is_maintenance_mode
    maintenance_active = await is_maintenance_mode(loop_for_maint)
    if maintenance_active and (real_user_id != admin_id or real_chat_type != 'private'):
        logger.info(f"Команда grow_tits отклонена из-за техработ в чате {real_chat_id}")
        try:
            await context.bot.send_message(chat_id=real_chat_id, text="🔧 Сорян, у меня сейчас технические работы. Попробуй позже.")
            await context.bot.delete_message(chat_id=real_chat_id, message_id=update.message.message_id)
        except Exception as e: logger.warning(f"Не удалось ответить/удалить сообщение о техработах (grow_tits): {e}")
        return
    # --->>> КОНЕЦ ПРОВЕРКИ ТЕХРАБОТ <<<---

    if not update.message or not update.message.from_user or not update.message.chat: return
    chat_id = update.message.chat.id # ВАЖНО: используем chat_id ТЕКУЩЕГО ЧАТА
    user_name_who_requested = update.message.from_user.first_name or "Любитель Рейтингов"
    chat_title = update.message.chat.title or "этого задрипанного чата"
    logger.info(f"Пользователь '{user_name_who_requested}' запросил топ писек в чате '{chat_title}' ({chat_id})")

    TOP_N = 10
    try:
        loop = asyncio.get_running_loop()
        # Ищем юзеров С penis_size > 0 ИМЕННО В ЭТОМ ЧАТЕ
        query = {"chat_id": chat_id, "penis_size": {"$gt": 0}}
        # Сортируем по penis_size, берем TOP_N
        # Возвращаем user_display_name (мы его дублируем) и penis_size
        top_users_cursor = await loop.run_in_executor(
            None,
            lambda: penis_stats_collection.find(
                query,
                {"user_display_name": 1, "penis_size": 1, "_id": 0}
            ).sort("penis_size", pymongo.DESCENDING).limit(TOP_N)
        )
        top_users_list = list(top_users_cursor)

        if not top_users_list:
            await context.bot.send_message(chat_id=chat_id, text=f"🗿 Пиздец, в чате '{chat_title}' одни бесхуевые или еще никто не начал растить! Топ пуст.")
            return

        reply_text_parts = [f"<b>🏆 Топ-{len(top_users_list)} Шлангов Чата '{chat_title}':</b>\n"]
        for i, user_data in enumerate(top_users_list):
            # Берем user_display_name, который мы сохранили в penis_stats_collection
            display_name = user_data.get("user_display_name") or "Анонимный Дрочила"
            penis_size = user_data.get("penis_size", 0)
            place_emoji = "🥇" if i == 0 else ("🥈" if i == 1 else ("🥉" if i == 2 else f"{i + 1}."))
            reply_text_parts.append(f"{place_emoji} {display_name} - <b>{penis_size} см</b>")

        final_text = "\n".join(reply_text_parts)
        await context.bot.send_message(chat_id=chat_id, text=final_text, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Ошибка при получении топа писек для чата {chat_id}: {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text="🗿 Бля, не смог составить рейтинг хуев для этого чата. База наебнулась.")
# --- КОНЕЦ ПЕРЕПИСАННОЙ show_penis_top ---

# --- ИЗМЕНЕННАЯ grow_tits (ДРОБНЫЙ РОСТ/УСЫХАНИЕ И КОМПЕНСАЦИЯ) ---
async def grow_tits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # --->>> НАЧАЛО ПРОВЕРКИ ТЕХРАБОТ (код как был) <<<---
    if not update or not update.message or not update.message.from_user or not update.message.chat:
         logger.warning(f"grow_tits: нет данных в update для проверки техработ")
         return
    real_chat_id = update.message.chat.id; real_user_id = update.message.from_user.id; real_chat_type = update.message.chat.type
    try: admin_id = int(os.getenv("ADMIN_USER_ID", "0"))
    except ValueError: admin_id = 0
    if admin_id == 0: logger.warning("ADMIN_USER_ID не задан для grow_tits!")
    loop_for_maint = asyncio.get_running_loop()
    maintenance_active = await is_maintenance_mode(loop_for_maint)
    if maintenance_active and (real_user_id != admin_id or real_chat_type != 'private'):
        logger.info(f"Команда grow_tits отклонена из-за техработ в чате {real_chat_id}")
        try:
            await context.bot.send_message(chat_id=real_chat_id, text="🔧 Сорян, у меня сейчас технические работы. Попробуй позже.")
            await context.bot.delete_message(chat_id=real_chat_id, message_id=update.message.message_id)
        except Exception as e: logger.warning(f"Не удалось ответить/удалить сообщение о техработах (grow_tits): {e}")
        return
    # --->>> КОНЕЦ ПРОВЕРКИ ТЕХРАБОТ <<<---

    if not update.message or not update.message.from_user or not update.message.chat: return # Повторная проверка
    user = update.message.from_user; chat_id = update.message.chat.id; loop = asyncio.get_running_loop()
    profile_name_data = await get_user_profile_data(user); user_display_name = profile_name_data["display_name"]
    logger.info(f"Пользователь '{user_display_name}' (ID: {user.id}) решил(а) изменить сиськи в чате {chat_id}.")

    tits_stat = await loop.run_in_executor(None, lambda: tits_stats_collection.find_one({"user_id": user.id, "chat_id": chat_id}))
    last_tits_growth_time = datetime.datetime.fromtimestamp(0, datetime.timezone.utc)
    current_tits_size = 0.0
    current_tits_title_db = None; warned_tits_cooldown = False

    if tits_stat:
        current_tits_size = float(tits_stat.get("tits_size", 0.0))
        current_tits_title_db = tits_stat.get("current_tits_title")
        warned_tits_cooldown = tits_stat.get("warned_during_cooldown", False) # Убедись, что поле называется так
        _last_tits_growth_db = tits_stat.get("last_tits_growth") # Убедись, что поле называется так
        if isinstance(_last_tits_growth_db, datetime.datetime):
            last_tits_growth_time = _last_tits_growth_db.replace(tzinfo=datetime.timezone.utc) if _last_tits_growth_db.tzinfo is None else _last_tits_growth_db

    current_time = datetime.datetime.now(datetime.timezone.utc)
    time_since_last_tits_growth = (current_time - last_tits_growth_time).total_seconds()

    # --->>> ЛОГИКА КУЛДАУНА И НАКАЗАНИЯ ДЛЯ СИСЕК (код как был, до момента обычного роста/усыхания) <<<---
    if time_since_last_tits_growth < TITS_GROWTH_COOLDOWN_SECONDS: # Убедись, что константа TITS_GROWTH_COOLDOWN_SECONDS существует
        remaining_time_tits = TITS_GROWTH_COOLDOWN_SECONDS - time_since_last_tits_growth
        h_tits = int(remaining_time_tits // 3600); m_tits = int((remaining_time_tits % 3600) // 60)
        if not warned_tits_cooldown:
            await context.bot.send_message(chat_id=chat_id, text=f"🗿 Э, {user_display_name}, не торопись! Твои дыньки еще на кулдауне! Осталось <b>{h_tits} ч {m_tits} мин</b>. Еще раз попросишь - сдуются нахуй!", parse_mode='HTML')
            await loop.run_in_executor(None, lambda: tits_stats_collection.update_one({"user_id": user.id, "chat_id": chat_id},{"$set": {"warned_during_cooldown": True}}, upsert=True))
            logger.info(f"Пользователь {user_display_name} получил предупреждение за частую тряску сисек.")
        else:
            shrink_amount_tits_punish = round(random.uniform(0.1, 1.0), 1)
            new_size_tits_after_punish = round(max(0.0, current_tits_size - shrink_amount_tits_punish), 1)
            logger.info(f"НАКАЗАНИЕ! Сиськи {user_display_name} СДУЛИСЬ на {shrink_amount_tits_punish}, теперь {new_size_tits_after_punish}!")
            await context.bot.send_message(chat_id=chat_id, text=f"🗿 АХ ТЫ Ж НЕТЕРПЕЛИВАЯ СУЧКА, {user_display_name}! Твои сиськи **СДУЛИСЬ на {shrink_amount_tits_punish} размера**! Теперь они <b>{new_size_tits_after_punish:.1f}-го размера</b>! Кулдаун сброшен.", parse_mode='HTML')
            await loop.run_in_executor(None, lambda: tits_stats_collection.update_one({"user_id": user.id, "chat_id": chat_id},{"$set": {"tits_size": new_size_tits_after_punish, "last_tits_growth": current_time, "warned_during_cooldown": False}}, upsert=True))
            # Проверка звания после наказания (логика как была)
            new_tits_title_achieved_punish = None; new_tits_title_message_punish = ""
            for size_thresh_t, (title_name_t, achievement_msg_t) in sorted(TITS_TITLES_BY_SIZE.items()):
                if new_size_tits_after_punish >= float(size_thresh_t): new_tits_title_achieved_punish = title_name_t; new_tits_title_message_punish = achievement_msg_t
                else: break
            if new_tits_title_achieved_punish != current_tits_title_db:
                 if new_tits_title_achieved_punish:
                    await loop.run_in_executor(None, lambda: tits_stats_collection.update_one({"user_id": user.id, "chat_id": chat_id},{"$set": {"current_tits_title": new_tits_title_achieved_punish}}))
                    mention_t_p = user.mention_html(); achievement_text_t_p = new_tits_title_message_punish.format(mention=mention_t_p, size=f"{new_size_tits_after_punish:.1f}")
                    await context.bot.send_message(chat_id=chat_id, text=achievement_text_t_p, parse_mode='HTML')
                 elif current_tits_title_db:
                    await loop.run_in_executor(None, lambda: tits_stats_collection.update_one({"user_id": user.id, "chat_id": chat_id},{"$set": {"current_tits_title": None}}))
                    await context.bot.send_message(chat_id=chat_id, text=f"🗿 {user.mention_html()}, после изменения твои сиськи потеряли все звания!", parse_mode='HTML')
        return
    # --->>> КОНЕЦ ЛОГИКИ КУЛДАУНА ДЛЯ СИСЕК <<<---

    new_tits_size = current_tits_size
    change_message_tits = ""
    change_amount_tits = round(random.uniform(0.1, 1.0), 1)
    tits_shrunk_naturally = False # Флаг для отслеживания естественного усыхания

    if random.random() < 0.01: # 1% шанс на сдутие
        tits_shrunk_naturally = True
        new_tits_size = round(max(0.0, current_tits_size - change_amount_tits), 1)
        logger.info(f"Сиськи {user_display_name} ВНЕЗАПНО СДУЛИСЬ на {change_amount_tits}, теперь {new_tits_size}!")
        change_message_tits = f"🗿 БЛЯТЬ, {user_display_name}! Твои сиськи **ВНЕЗАПНО СДУЛИСЬ на {change_amount_tits} размера**! Теперь они жалкого <b>{new_tits_size:.1f}-го размера</b>!"
    else: # Рост
        new_tits_size = round(current_tits_size + change_amount_tits, 1)
        logger.info(f"Сиськи {user_display_name} выросли на {change_amount_tits}, теперь {new_tits_size}!")
        change_message_tits = f"🗿 {user_display_name}, твои бидоны подросли на <b>{change_amount_tits} размера</b> и стали <b>{new_tits_size:.1f}-го</b>! Поздравляю, ебать!"

    try:
        update_doc_tits = {
            "$set": {"tits_size": new_tits_size, "last_tits_growth": current_time, "warned_during_cooldown": False, "user_display_name": user_display_name},
            "$setOnInsert": {"user_id": user.id, "chat_id": chat_id, "current_tits_title": None} # Добавляем user_id и chat_id при первой вставке
        }
        # Предотвращаем дублирование
        if "$setOnInsert" in update_doc_tits and "$set" in update_doc_tits:
            for key_to_pop in ["tits_size", "last_tits_growth", "warned_during_cooldown", "user_display_name"]:
                 update_doc_tits["$setOnInsert"].pop(key_to_pop, None)


        await loop.run_in_executor(None, lambda: tits_stats_collection.update_one(
            {"user_id": user.id, "chat_id": chat_id},
            update_doc_tits,
            upsert=True
        ))
        await context.bot.send_message(chat_id=chat_id, text=change_message_tits, parse_mode='HTML')

        # --->>> ЛОГИКА КОМПЕНСАЦИИ, ЕСЛИ СИСЬКИ УСОХЛИ ЕСТЕСТВЕННО <<<---
        if tits_shrunk_naturally:
            if random.random() < 0.52: # 52% шанс на компенсацию
                logger.info(f"Сиськи {user_display_name} сдулись, но повезло! Компенсация писюном.")
                # Получаем текущий размер письки
                penis_stat_for_compensation = await loop.run_in_executor(
                    None, lambda: penis_stats_collection.find_one({"user_id": user.id, "chat_id": chat_id})
                )
                current_penis_size_comp = 0
                current_penis_title_db_comp = None
                if penis_stat_for_compensation:
                    current_penis_size_comp = penis_stat_for_compensation.get("penis_size", 0)
                    current_penis_title_db_comp = penis_stat_for_compensation.get("current_penis_title")

                penis_growth_compensation = 10 # см
                new_penis_size_comp = current_penis_size_comp + penis_growth_compensation

                await loop.run_in_executor(None, lambda: penis_stats_collection.update_one(
                    {"user_id": user.id, "chat_id": chat_id},
                    {"$set": {"penis_size": new_penis_size_comp, "user_display_name": user_display_name}, # Не обновляем last_penis_growth
                     "$setOnInsert": {"user_id": user.id, "chat_id": chat_id, "last_penis_growth": datetime.datetime.fromtimestamp(0, datetime.timezone.utc), "current_penis_title": None, "warned_during_cooldown": False}},
                    upsert=True
                ))
                await context.bot.send_message(chat_id=chat_id, text=f"🗿 Но не горюй, {user_display_name}! В качестве утешительного приза твой писюн ВНЕЗАПНО **подрос на {penis_growth_compensation} см** и стал <b>{new_penis_size_comp} см</b>! Закон сохранения хуйни в природе!", parse_mode='HTML')

                # Проверка на новое писечное звание после компенсации
                new_penis_title_achieved_comp_p = None; new_penis_title_message_comp_p = ""
                for size_thresh_penis, (title_name_penis, achievement_msg_penis) in sorted(PENIS_TITLES_BY_SIZE.items()):
                    if new_penis_size_comp >= size_thresh_penis: new_penis_title_achieved_comp_p = title_name_penis; new_penis_title_message_comp_p = achievement_msg_penis
                    else: break
                if new_penis_title_achieved_comp_p != current_penis_title_db_comp: # Сравниваем с тем, что было в БД для писек
                     if new_penis_title_achieved_comp_p:
                        await loop.run_in_executor(None, lambda: penis_stats_collection.update_one({"user_id": user.id, "chat_id": chat_id},{"$set": {"current_penis_title": new_penis_title_achieved_comp_p}}))
                        mention_comp_penis = user.mention_html(); achievement_text_comp_penis = new_penis_title_message_comp_p.format(mention=mention_comp_penis, size=new_penis_size_comp)
                        await context.bot.send_message(chat_id=chat_id, text=achievement_text_comp_penis, parse_mode='HTML')
            else:
                logger.info(f"Сиськи {user_display_name} сдулись, и компенсации не будет. Не повезло.")
                await context.bot.send_message(chat_id=chat_id, text=f"🗿 И хуй тебе, а не компенсация, {user_display_name}. Ходи с обвисшими и без бонусов.", parse_mode='HTML')
        # --->>> КОНЕЦ ЛОГИКИ КОМПЕНСАЦИИ <<<---

        # Проверка на новое сисечное звание (логика как была)
        new_tits_title_achieved = None; new_tits_title_message = ""
        for size_threshold, (title_name, achievement_message) in sorted(TITS_TITLES_BY_SIZE.items()):
            if new_tits_size >= float(size_threshold):
                new_tits_title_achieved = title_name; new_tits_title_message = achievement_message
            else: break
        if new_tits_title_achieved != current_tits_title_db:
             if new_tits_title_achieved:
                await loop.run_in_executor(None, lambda: tits_stats_collection.update_one({"user_id": user.id, "chat_id": chat_id},{"$set": {"current_tits_title": new_tits_title_achieved}}))
                mention = user.mention_html(); achievement_text = new_tits_title_message.format(mention=mention, size=f"{new_tits_size:.1f}")
                await context.bot.send_message(chat_id=chat_id, text=achievement_text, parse_mode='HTML')
             elif current_tits_title_db: # Если звание было, а теперь нет
                await loop.run_in_executor(None, lambda: tits_stats_collection.update_one({"user_id": user.id, "chat_id": chat_id},{"$set": {"current_tits_title": None}}))
                await context.bot.send_message(chat_id=chat_id, text=f"🗿 {user.mention_html()}, после изменения твои сиськи потеряли все звания!", parse_mode='HTML')
    except Exception as e:
        logger.error(f"Ошибка при изменении сисек для {user_display_name}: {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text=f"🗿 Бля, {user_display_name}, с сиськами опять какая-то хуйня. Попробуй позже.")
# --- КОНЕЦ ИЗМЕНЕННОЙ grow_tits ---


async def show_my_tits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # --->>> НАЧАЛО ПРОВЕРКИ ТЕХРАБОТ (ВСТАВЬ В КАЖДУЮ КОМАНДНУЮ ФУНКЦИЮ!) <<<---
    if not update or not update.message or not update.message.from_user or not update.message.chat:
         logger.warning(f"grow_tits: нет данных в update для проверки техработ")
         return
    real_chat_id = update.message.chat.id; real_user_id = update.message.from_user.id; real_chat_type = update.message.chat.type
    try: admin_id = int(os.getenv("ADMIN_USER_ID", "0"))
    except ValueError: admin_id = 0
    if admin_id == 0: logger.warning("ADMIN_USER_ID не задан для grow_tits!") # Можно убрать это логгирование в каждой функции
    loop_for_maint = asyncio.get_running_loop() # Отдельный loop для вызова is_maintenance_mode
    maintenance_active = await is_maintenance_mode(loop_for_maint)
    if maintenance_active and (real_user_id != admin_id or real_chat_type != 'private'):
        logger.info(f"Команда grow_tits отклонена из-за техработ в чате {real_chat_id}")
        try:
            await context.bot.send_message(chat_id=real_chat_id, text="🔧 Сорян, у меня сейчас технические работы. Попробуй позже.")
            await context.bot.delete_message(chat_id=real_chat_id, message_id=update.message.message_id)
        except Exception as e: logger.warning(f"Не удалось ответить/удалить сообщение о техработах (grow_tits): {e}")
        return
    # --->>> КОНЕЦ ПРОВЕРКИ ТЕХРАБОТ <<<---
    if not update.message or not update.message.from_user or not update.message.chat: return
    user = update.message.from_user; chat_id = update.message.chat.id; loop = asyncio.get_running_loop()
    profile_name_data = await get_user_profile_data(user); user_display_name = profile_name_data["display_name"]
    logger.info(f"Пользователь '{user_display_name}' (ID: {user.id}) запросил инфу о сиськах в чате {chat_id}.")

    tits_stat = await loop.run_in_executor(None, lambda: tits_stats_collection.find_one({"user_id": user.id, "chat_id": chat_id}))
    current_tits_size = 0; current_tits_title = "Неизвестного размера (пока)"
    if tits_stat:
        current_tits_size = tits_stat.get("tits_size", 0)
        for size_threshold, (title_name, _) in sorted(TITS_TITLES_BY_SIZE.items()):
             if current_tits_size >= size_threshold: current_tits_title = title_name
             else: break

    reply_text = f"🗿 Итак, {user_display_name}, твои сисяндры в чате <b>'{update.message.chat.title or 'этом'}'</b>:\n\n"
    reply_text += f"<b>Размер:</b> {current_tits_size}-й\n"
    reply_text += f"<b>Сисько-Звание:</b> {current_tits_title}.\n\n"
    if current_tits_size <= 0: reply_text += "Плоско, как доска, и грустно, как моя жизнь."
    elif current_tits_size <= 2: reply_text += "Ну, хоть не в минус. Уже достижение, блядь."
    elif current_tits_size <= 4: reply_text += "Вполне себе! Можно даже лифчик носить не для вида."
    else: reply_text += "Охуеть! С такими можно и на таран идти!"
    await context.bot.send_message(chat_id=chat_id, text=reply_text, parse_mode='HTML')


async def show_tits_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # --->>> НАЧАЛО ПРОВЕРКИ ТЕХРАБОТ (ВСТАВЬ В КАЖДУЮ КОМАНДНУЮ ФУНКЦИЮ!) <<<---
    if not update or not update.message or not update.message.from_user or not update.message.chat:
         logger.warning(f"grow_tits: нет данных в update для проверки техработ")
         return
    real_chat_id = update.message.chat.id; real_user_id = update.message.from_user.id; real_chat_type = update.message.chat.type
    try: admin_id = int(os.getenv("ADMIN_USER_ID", "0"))
    except ValueError: admin_id = 0
    if admin_id == 0: logger.warning("ADMIN_USER_ID не задан для grow_tits!") # Можно убрать это логгирование в каждой функции
    loop_for_maint = asyncio.get_running_loop() # Отдельный loop для вызова is_maintenance_mode
    maintenance_active = await is_maintenance_mode(loop_for_maint)
    if maintenance_active and (real_user_id != admin_id or real_chat_type != 'private'):
        logger.info(f"Команда grow_tits отклонена из-за техработ в чате {real_chat_id}")
        try:
            await context.bot.send_message(chat_id=real_chat_id, text="🔧 Сорян, у меня сейчас технические работы. Попробуй позже.")
            await context.bot.delete_message(chat_id=real_chat_id, message_id=update.message.message_id)
        except Exception as e: logger.warning(f"Не удалось ответить/удалить сообщение о техработах (grow_tits): {e}")
        return
    # --->>> КОНЕЦ ПРОВЕРКИ ТЕХРАБОТ <<<---
    if not update.message or not update.message.from_user or not update.message.chat: return
    chat_id = update.message.chat.id; user_name_req = update.message.from_user.first_name or "Фанатка Сисек"; chat_title = update.message.chat.title or "этого чата"
    logger.info(f"Пользователь '{user_name_req}' запросил топ сисек в чате '{chat_title}' ({chat_id})")
    TOP_N = 10
    try:
        loop = asyncio.get_running_loop()
        query = {"chat_id": chat_id, "tits_size": {"$gte": 0}} # Берем всех, у кого не отрицательный размер
        top_users_cursor = await loop.run_in_executor( None, lambda: tits_stats_collection.find(query, {"user_display_name": 1, "tits_size": 1, "_id": 0}).sort("tits_size", pymongo.DESCENDING).limit(TOP_N))
        top_users_list = list(top_users_cursor)
        if not top_users_list:
            await context.bot.send_message(chat_id=chat_id, text=f"🗿 Пиздец, в чате '{chat_title}' одни плоскодонки или еще никто не начал растить сиськи! Топ пуст."); return
        reply_text_parts = [f"<b>🏆 Топ-{len(top_users_list)} Сисястых Богинь Чата '{chat_title}':</b>\n"]
        for i, user_data in enumerate(top_users_list):
            display_name = user_data.get("user_display_name") or "Анонимная Сиська"; tits_size = user_data.get("tits_size", 0)
            place_emoji = "🥇" if i == 0 else ("🥈" if i == 1 else ("🥉" if i == 2 else f"{i + 1}."))
            reply_text_parts.append(f"{place_emoji} {display_name} - <b>{tits_size}-й размер</b>")
        await context.bot.send_message(chat_id=chat_id, text="\n".join(reply_text_parts), parse_mode='HTML')
    except Exception as e:
        logger.error(f"Ошибка при получении топа сисек для чата {chat_id}: {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text="🗿 Бля, не смог составить рейтинг сисек. База наебнулась.")


# Убедись, что ADMIN_USER_ID, logger и chat_activity_collection определены и доступны

async def list_bot_chats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user:
        return

    user_id = update.message.from_user.id
    request_chat_id = update.message.chat.id # ID чата, откуда пришла команда (ЛС админа)
    request_chat_type = update.message.chat.type

    # --->>> ПРОВЕРКА, ЧТО КОМАНДА ОТ АДМИНА И В ЛИЧНОМ ЧАТЕ <<<---
    if not (user_id == ADMIN_USER_ID and request_chat_type == 'private'):
        logger.warning(f"Попытка вызова /listchats не от админа или не в ЛС. User: {user_id}, Chat: {request_chat_id}")
        await update.message.reply_text("🗿 Эта команда доступна только Великому Создателю в его священных личных покоях (то есть, в ЛС со мной).")
        return

    logger.info(f"Админ ({ADMIN_USER_ID}) запросил список чатов, в которых состоит бот.")
    await update.message.reply_text("🗿 Собираю досье на все притоны, где я прописан... Минутку.")

    try:
        loop = asyncio.get_running_loop()
        
        # Запрашиваем все документы из chat_activity_collection, нам нужны chat_id и last_message_time
        # Дополнительно можно запросить название чата, если мы его храним там же
        # (но обычно название чата получается через context.bot.get_chat())
        chat_docs_cursor = await loop.run_in_executor(
            None,
            lambda: chat_activity_collection.find(
                {}, # Пустой фильтр - выбрать все документы
                {"chat_id": 1, "last_message_time": 1, "_id": 0} # Проекция: только нужные поля
            ).sort("last_message_time", pymongo.DESCENDING) # Сортируем по последней активности
        )
        
        chat_list = list(chat_docs_cursor)

        if not chat_list:
            await update.message.reply_text("🗿 Похоже, меня еще никуда не добавили, либо я забыл, где я. Пусто, как в твоей голове после зарплаты.")
            return

        response_messages = [f"<b>📜 Список чатов, где я (Попиздяка) был замечен (всего: {len(chat_list)}):</b>\n"]
        current_message_part = ""

        for i, chat_data in enumerate(chat_list):
            bot_chat_id = chat_data.get("chat_id")
            last_active_time = chat_data.get("last_message_time")
            
            chat_title = f"ID: {bot_chat_id}" # Запасной вариант, если не удастся получить имя
            chat_username = None
            member_count = None

            try:
                # Получаем актуальную информацию о чате
                # ВНИМАНИЕ: get_chat может быть медленным, если чатов очень много.
                # Но для админской команды, которая вызывается нечасто, это приемлемо.
                chat_info = await context.bot.get_chat(chat_id=bot_chat_id)
                chat_title = chat_info.title or chat_title # Если есть title, используем его
                if chat_info.username:
                    chat_username = f"@{chat_info.username}"
                # Для групп можно попробовать получить количество участников
                if chat_info.type in ['group', 'supergroup']:
                    try:
                        member_count = await context.bot.get_chat_member_count(chat_id=bot_chat_id)
                    except Exception: # Если бот не админ в чате или другая ошибка
                        pass 
            except telegram.error.TelegramError as e: # TelegramError - базовый класс для ошибок API
                logger.warning(f"Не удалось получить информацию для чата {bot_chat_id}: {e}")
                # Оставляем chat_title как "ID: {bot_chat_id}"
            except Exception as e_unknown:
                logger.error(f"Неизвестная ошибка при получении информации о чате {bot_chat_id}: {e_unknown}")


            line = f"\n<b>{i+1}. {chat_title}</b>"
            if chat_username:
                line += f" ({chat_username})"
            line += f"\n   ID: <code>{bot_chat_id}</code>"
            if member_count:
                line += f" | Участников: ~{member_count}"
            if last_active_time:
                # Преобразуем UTC время из БД в читаемый формат (можно указать локальную таймзону, если нужно)
                # Для простоты покажем UTC
                last_active_str = last_active_time.strftime("%Y-%m-%d %H:%M:%S UTC")
                line += f"\n   Последняя активность: {last_active_str}"
            line += "\n"

            # Разбиваем на несколько сообщений, если список слишком длинный
            if len(current_message_part + line) > 4000: # Оставляем запас до лимита 4096
                response_messages.append(current_message_part)
                current_message_part = line
            else:
                current_message_part += line
        
        if current_message_part: # Добавляем последнюю часть
            response_messages.append(current_message_part)

        # Отправляем сообщения админу
        for msg_part in response_messages:
            if msg_part.strip(): # Проверяем, что часть не пустая
                await context.bot.send_message(chat_id=request_chat_id, text=msg_part, parse_mode='HTML')
            await asyncio.sleep(0.3) # Небольшая задержка между сообщениями, чтобы не спамить API

    except pymongo.errors.PyMongoError as e_mongo:
        logger.error(f"Ошибка MongoDB при получении списка чатов: {e_mongo}", exc_info=True)
        await update.message.reply_text("🗿 Ошибка! Не смог залезть в свои архивы (проблема с базой данных).")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при формировании списка чатов: {e}", exc_info=True)
        await update.message.reply_text(f"🗿 Пиздец какой-то случился, не могу показать список. Ошибка: {type(e).__name__}")        


# Переименуем функцию для ясности
async def generate_and_set_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user or not update.message.chat:
        return

    user = update.message.from_user
    chat_id = update.message.chat.id
    loop = asyncio.get_running_loop()

    # --->>> ПРОВЕРКА ТЕХРАБОТ (как и раньше) <<<---
    maintenance_active = await is_maintenance_mode(loop)
    if maintenance_active and (user.id != ADMIN_USER_ID or update.message.chat.type != 'private'):
        # ... (сообщение о техработах и return) ...
        logger.info(f"Команда генерации ника отклонена из-за техработ в чате {chat_id}")
        try: await update.message.reply_text("🔧 Техработы, сейчас не до выдумывания кличек.")
        except Exception: pass
        return
    # --->>> КОНЕЦ ПРОВЕРКИ ТЕХРАБОТ <<<---

    user_profile_data = await get_user_profile_data(user) # Получаем текущие данные для имени и пр.
    user_display_name_before = user_profile_data["display_name"]

    thinking_msg = await context.bot.send_message(chat_id=chat_id, text=f"🗿 Так, {user_display_name_before}, сейчас я покопаюсь в твоих высерах и придумаю тебе достойное (нет) погоняло...")

    # --->>> 1. СБОР КОНТЕКСТА (ПОСЛЕДНИЕ СООБЩЕНИЯ ПОЛЬЗОВАТЕЛЯ) <<<---
    user_context_messages = []
    USER_CONTEXT_LIMIT_FOR_NICKNAME = 50 # Сколько сообщений анализировать
    try:
        # Ищем сообщения ИМЕННО ЭТОГО ЮЗЕРА (user.id) ВО ВСЕХ ЧАТАХ, где бот его видел
        # Или можно ограничиться текущим чатом: {"user_id": user.id, "chat_id": chat_id}
        # Для более "общего" ника лучше брать из всех чатов.
        query_context = {"user_id": user.id}
        sort_order_context = [("timestamp", pymongo.DESCENDING)]
        
        history_cursor_context = await loop.run_in_executor(
            None, lambda: history_collection.find(query_context).sort(sort_order_context).limit(USER_CONTEXT_LIMIT_FOR_NICKNAME)
        )
        user_messages_docs = list(history_cursor_context)[::-1] # Переворачиваем для хронологии

        if user_messages_docs:
            # Берем только текстовое содержимое, игнорируя стикеры/картинки для простоты промпта
            for msg_doc in user_messages_docs:
                text_content = msg_doc.get("text", "")
                if text_content and not text_content.startswith(("[СТИКЕР", "[КАРТИНКА", "[ОТПРАВИЛ(А) ВИДЕО]", "[ОТПРАВИЛ(А) ГОЛОСОВОЕ]")):
                    user_context_messages.append(text_content.strip())
            logger.info(f"Для генерации ника для {user_display_name_before} собрано {len(user_context_messages)} текстовых сообщений.")
        else:
            logger.info(f"Контекст сообщений для {user_display_name_before} не найден. Ник будет генерироваться без него.")
            
    except Exception as db_e:
        logger.error(f"Ошибка чтения контекста для генерации ника (user_id: {user.id}): {db_e}")
        # Продолжим без контекста, если не удалось его собрать

    user_context_string = "\n- ".join(user_context_messages) if user_context_messages else "Недавно нихуя не писал(а) или писал(а) одну нетекстовую хуйню."


    # --->>> 2. ГЕНЕРАЦИЯ НИКА ЧЕРЕЗ ИИ <<<---
    # Промпт для ИИ, чтобы придумать ник
    nickname_generation_prompt = (
        f"Ты - Попиздяка, бот с охуенно черным юмором и мастер выдумывать стебные, уничижительные, но креативные прозвища. "
        f"Тебе нужно придумать ОДНО уникальное, смешное и запоминающееся ПОГОНЯЛО (никнейм) для пользователя по имени '{user_display_name_before}'. "
        f"Ник должен состоять из 2-4 слов. Он должен быть в твоем фирменном стиле: циничный, матерный, абсурдный, возможно, немного 'черножопый' (если это вписывается в контекст и не переходит грань тупого расизма, а скорее абсурдно обыгрывает стереотипы, если пользователь сам дал повод). "
        f"Вот краткая история последних сообщений этого пользователя (если есть, используй ее для вдохновения, ищи характерные словечки, темы, тупости):\n"
        f"```\n- {user_context_string}\n```\n"
        f"Инструкции для ника:\n"
        f"1.  **ОСНОВА:** Если в сообщениях пользователя есть что-то характерное (частое слово, тупая идея, жалоба, интерес), постарайся это КРЕАТИВНО и САРКАСТИЧНО обыграть в нике.\n"
        f"2.  **АБСУРД И ЮМОР:** Ник должен быть смешным из-за своей нелепости, неожиданности или черного юмора.\n"
        f"3.  **КРАТКОСТЬ:** 2-4 слова, не больше.\n"
        f"4.  **УНИКАЛЬНОСТЬ:** Постарайся не повторять банальные оскорбления, будь изобретателен.\n"
        f"5.  **СТИЛЬ ПОПИЗДЯКИ:** Мат приветствуется, цинизм обязателен.\n"
        f"6.  **РЕЗУЛЬТАТ:** Выдай ТОЛЬКО САМ НИКНЕЙМ, без кавычек, без пояснений, без 'Вот твой ник:'. Просто текст ника.\n\n"
        f"Примеры охуенных ников, которые ты мог бы придумать:\n"
        f"- Повелитель Просроченной Шаурмы (если юзер часто пишет про еду или шаурму)\n"
        f"- Архитектор Воздушных Замков (если юзер много мечтает или несет бред)\n"
        f"- Генерал Диванных Войск\n"
        f"- Профессор Хуевых Советов\n"
        f"- Капитан Очевидный Долбоеб\n"
        f"- Лорд Недотраханных Фантазий\n"
        f"- Эмир Полуночных Жореков\n"
        f"- Жрец Святого Перегара\n\n"
        f"Придумай ОДИН такой ник для '{user_display_name_before}', основываясь на его/ее сообщениях или просто на своем больном воображении:"
    )

    generated_nickname = await _call_ionet_api(
        messages=[{"role": "user", "content": nickname_generation_prompt}],
        model_id=IONET_TEXT_MODEL_ID,
        max_tokens=30, # Ник короткий
        temperature=0.9 # Высокая температура для креативности
    )

    if not generated_nickname or generated_nickname.startswith("[") or len(generated_nickname.split()) > 5 or len(generated_nickname) > 40: # Проверка на адекватность ответа
        logger.warning(f"ИИ сгенерировал некорректный ник: '{generated_nickname}'. Используем дефолтный.")
        # Можно взять из твоего старого списка RANDOM_POPIZDYAKA_NICKNAMES как запасной вариант
        if RANDOM_POPIZDYAKA_NICKNAMES: # Убедись, что этот список еще существует
             generated_nickname = random.choice(RANDOM_POPIZDYAKA_NICKNAMES)
        else:
             generated_nickname = f"Очередной Долбоеб №{random.randint(100,999)}" # Крайний случай
    
    generated_nickname = generated_nickname.strip().title() # Убираем лишние пробелы и делаем Title Case

    if thinking_msg:
        try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_msg.message_id)
        except Exception: pass

    logger.info(f"Для пользователя '{user_display_name_before}' ({user.id}) сгенерирован ИИ-ник: '{generated_nickname}'")

    # --->>> 3. УСТАНОВКА НИКА И КОММЕНТАРИЙ ОТ ПОПИЗДЯКИ <<<---
    try:
        # Обновляем или создаем профиль с новым ником
        await loop.run_in_executor(
            None,
            lambda: user_profiles_collection.update_one(
                {"user_id": user.id},
                {"$set": {"custom_nickname": generated_nickname, "tg_first_name": user.first_name, "tg_username": user.username},
                 "$setOnInsert": { "user_id": user.id, "message_count": 0, "current_title": None,
                                   # Добавь сюда поля для писько/сиськомеров из твоего set_nickname, если они там есть
                                 }
                },
                upsert=True
            )
        )
        
        # Сообщение от Попиздяки с новым ником (тоже через ИИ)
        comment_on_new_nickname_prompt = (
            f"Ты - Попиздяка, циничный и матерный бот. Ты только что придумал и присвоил пользователю (который раньше был '{user_display_name_before}') новый охуительный никнейм: «{generated_nickname}».\n"
            f"Напиши ОДНО короткое (1-2 предложения) сообщение этому пользователю. "
            f"В своем сообщении ты должен:\n"
            f"1. Объявить ему его новый ник «{generated_nickname}» (можно выделить жирным).\n"
            f"2. Едко, саркастично и с матом прокомментировать, насколько этот ник ему/ей подходит, или как ему/ей 'повезло'.\n"
            f"3. Начинай с `🗿`.\n\n"
            f"Пример: Если ник 'Повелитель Просроченной Шаурмы':\n"
            f"🗿 Слышь ты, гурман хуев! Отныне твое погоняло – <b>Повелитель Просроченной Шаурмы</b>! Как раз под стать твоим кулинарным высерам. Носи с гордостью, пока не отравишься!\n\n"
            f"Твой комментарий к присвоению ника «{generated_nickname}»:"
        )

        ai_comment_message = await _call_ionet_api(
            messages=[{"role": "user", "content": comment_on_new_nickname_prompt}],
            model_id=IONET_TEXT_MODEL_ID,
            max_tokens=150, # Чуть больше для комментария
            temperature=0.8
        ) or f"🗿 Короче, теперь ты у нас <b>{generated_nickname}</b>. Привыкай, хуила."

        if not ai_comment_message.startswith("🗿"): ai_comment_message = "🗿 " + ai_comment_message
        
        # Гарантируем, что ник будет выделен, если ИИ его не выделил
        if f"<b>{generated_nickname}</b>" not in ai_comment_message and generated_nickname in ai_comment_message:
            ai_comment_message = ai_comment_message.replace(generated_nickname, f"<b>{generated_nickname}</b>")
        elif generated_nickname.lower() not in ai_comment_message.lower(): # Если ИИ вообще забыл упомянуть ник
             ai_comment_message += f"\nТвое новое погоняло, если ты не понял: <b>{generated_nickname}</b>."


        await context.bot.send_message(chat_id=chat_id, text=ai_comment_message, parse_mode='HTML')

        # Обновление имени в истории сообщений
        try:
            asyncio.create_task(update_history_with_new_name(user.id, generated_nickname, context))
            logger.info(f"Запущена задача обновления истории для ИИ-ника '{generated_nickname}' (user_id: {user.id})")
        except Exception as task_e:
            logger.error(f"Ошибка запуска задачи update_history_with_new_name для ИИ-ника: {task_e}")

    except Exception as e:
        logger.error(f"Ошибка установки ИИ-сгенерированного никнейма для user_id {user.id}: {e}", exc_info=True)
        if thinking_msg: # Удаляем "думающее" сообщение, если оно еще есть
            try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_msg.message_id)
            except Exception: pass
        await context.bot.send_message(chat_id=chat_id, text=f"🗿 Бля, хотел тебя обозвать как-нибудь по-новому, да мой ИИ-мозг перегрелся. Ходи пока как {user_display_name_before}.")


# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ РАСКРЫТИЯ ОТВЕТА В "ПРАВДА ИЛИ ВЫСЕР" ---
async def _reveal_truth_or_shit_answer(
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        original_question_msg_id: int,
        triggered_by_user: User | None = None # Кто нажал кнопку "Раскрыть" (если применимо)
    ):
    loop = asyncio.get_running_loop()
    logger.info(f"Запрос на раскрытие ответа для игры (msg_id: {original_question_msg_id}) в чате {chat_id}.")

    game_data = await loop.run_in_executor(
        None, lambda: active_truth_or_shit_games_collection.find_one_and_update(
            {"chat_id": chat_id, "message_id_question": original_question_msg_id, "revealed": False},
            {"$set": {"revealed": True}} # Сразу помечаем как раскрытое, чтобы избежать гонок состояний
        )
    )

    if not game_data: # Либо игра не найдена, либо уже была раскрыта
        logger.info(f"Игра (msg_id: {original_question_msg_id}) в чате {chat_id} не найдена или уже раскрыта. Ничего не делаем.")
        # Попытаемся убрать кнопки у старого сообщения, если оно еще существует и имеет кнопки
        try:
            await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=original_question_msg_id, reply_markup=None)
        except telegram.error.BadRequest as e: # "Message to edit not found" or "message can't be edited" or "message is not modified"
            if "message is not modified" not in str(e).lower() and "message to edit not found" not in str(e).lower():
                logger.warning(f"Ошибка при попытке убрать кнопки у старого сообщения ToS (msg_id: {original_question_msg_id}): {e}")
        except Exception: pass # Игнорируем другие ошибки здесь
        return

    correct_answer_is_truth = game_data["is_truth"]
    statement_text = game_data["statement"]
    
    result_text_human = "✅ ПРАВДА!" if correct_answer_is_truth else "❌ ВЫСЕР ЕБАНЫЙ!"
    
    votes_summary = "Никто даже не попытался блеснуть интеллектом и проголосовать. Стадо тупорылых баранов."
    if game_data.get("votes"):
        total_votes = len(game_data["votes"])
        if total_votes > 0:
            correct_votes_count = sum(1 for uid, vote_val in game_data["votes"].items() if vote_val == correct_answer_is_truth)
            wrong_votes_count = total_votes - correct_votes_count
            if total_votes == 1:
                votes_summary = f"Единственный смельчак, который проголосовал, оказался {'непроходимым долбоебом' if correct_votes_count == 0 else 'на удивление прошаренным (или ему просто повезло)'}."
            else:
                votes_summary = (f"Из {total_votes} отважившихся дегенератов, {correct_votes_count} каким-то чудом угадали (или подсмотрели), "
                                 f"а {wrong_votes_count} жидко обосрались, подтвердив свою репутацию.")
    
    triggered_by_text = ""
    if triggered_by_user:
        triggered_by_text = f"(По просьбе нетерпеливого {triggered_by_user.mention_html()})\n"


    reveal_comment_prompt = (
        f"Ты - Попиздяка, ведущий игры 'Правда или Высер'. Игра завершена.\n"
        f"Утверждение было: «{statement_text}»\n"
        f"Правильный ответ: {result_text_human}\n"
        f"Статистика голосов (если была): {votes_summary}\n\n"
        f"Напиши короткий (2-4 предложения), саркастичный и матерный комментарий по итогам. "
        f"Если были голосовавшие, удели внимание тем, кто ошибся. Если не было, пройдись по пассивности аудитории. "
        f"Начинай с `🗿 Итак, долбоебы и сочувствующие, слушайте сюда:`"
    )
    ai_reveal_comment = await _call_ionet_api(
        messages=[{"role": "user", "content": reveal_comment_prompt}],
        model_id=IONET_TEXT_MODEL_ID, max_tokens=200, temperature=0.8
    ) or "🗿 Ну вот и все. Кто угадал - тот не совсем дебил. Остальные - просто дебилы, смиритесь."
    if not ai_reveal_comment.startswith("🗿"): ai_reveal_comment = "🗿 " + ai_reveal_comment

    final_reveal_message = (
        f"<b>Игра 'Правда или Высер' ОКОНЧЕНА!</b>\n{triggered_by_text}\n"
        f"Утверждение Попиздяки было:\n«<i>{statement_text}</i>»\n\n"
        f"И это был... <b>{result_text_human}</b>\n\n"
        f"{ai_reveal_comment}"
    )
    
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=original_question_msg_id,
            text=final_reveal_message, parse_mode='HTML', reply_markup=None
        )
    except telegram.error.BadRequest as e_edit:
        if "message is not modified" in str(e_edit).lower():
            logger.info(f"Сообщение ToS (msg_id: {original_question_msg_id}) не было изменено при раскрытии, возможно, уже содержит тот же текст. Убираю кнопки.")
            try: await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=original_question_msg_id, reply_markup=None)
            except Exception: pass
        else:
            logger.warning(f"Не удалось отредактировать сообщение ToS (msg_id: {original_question_msg_id}) для раскрытия ответа: {e_edit}. Отправляю новым.")
            await context.bot.send_message(chat_id=chat_id, text=final_reveal_message, parse_mode='HTML')
            try: await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=original_question_msg_id, reply_markup=None)
            except Exception: pass
    except Exception as e_unhandled:
        logger.error(f"Непредвиденная ошибка при редактировании сообщения ToS: {e_unhandled}")
        await context.bot.send_message(chat_id=chat_id, text=final_reveal_message, parse_mode='HTML') # Запасной вариант


    logger.info(f"Игра (msg_id: {original_question_msg_id}) в чате {chat_id} успешно раскрыта. Правильный ответ: {correct_answer_is_truth}")

    # Обновляем время последней игры в chat_activity для кулдауна
    await loop.run_in_executor(
        None, lambda: chat_activity_collection.update_one(
            {"chat_id": chat_id},
            {"$set": {"last_tos_game_end_time": datetime.datetime.now(datetime.timezone.utc)}}, # Используем время окончания
            upsert=True
        )
    )
# --- КОНЕЦ ВСПОМОГАТЕЛЬНОЙ ФУНКЦИИ ---

# --- JOB ДЛЯ АВТОМАТИЧЕСКОГО РАСКРЫТИЯ "ПРАВДА ИЛИ ВЫСЕР" ---
async def auto_reveal_truth_or_shit_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if not job or not job.chat_id or not job.data or 'message_id_question' not in job.data:
        logger.error(f"Ошибка в job 'auto_reveal_truth_or_shit_job': нет необходимых данных. Job data: {job.data if job else 'No job'}")
        return
    
    chat_id = job.chat_id
    message_id_question = job.data['message_id_question']
    
    logger.info(f"Сработал авто-ревил для игры (msg_id: {message_id_question}) в чате {chat_id}.")
    await _reveal_truth_or_shit_answer(context, chat_id, message_id_question, triggered_by_user=None)
# --- КОНЕЦ JOB ДЛЯ АВТОМАТИЧЕСКОГО РАСКРЫТИЯ ---

# --- КОМАНДА ЗАПУСКА ИГРЫ "ПРАВДА ИЛИ ВЫСЕР" ---
async def start_truth_or_shit_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.chat or not update.message.from_user:
        return

    chat_id = update.message.chat.id
    user = update.message.from_user
    loop = asyncio.get_running_loop()

    # --->>> ПРОВЕРКА ТЕХРАБОТ <<<---
    maintenance_active = await is_maintenance_mode(loop)
    if maintenance_active and (user.id != ADMIN_USER_ID or update.message.chat.type != 'private'):
        await update.message.reply_text("🔧 Техработы, не до игр разума сегодня.")
        return
    # --->>> КОНЕЦ ПРОВЕРКИ ТЕХРАБОТ <<<---

    # --->>> ПРОВЕРКА КУЛДАУНА ДЛЯ ЧАТА <<<---
    chat_activity = await loop.run_in_executor(
        None, lambda: chat_activity_collection.find_one({"chat_id": chat_id})
    )
    now_utc_start = datetime.datetime.now(datetime.timezone.utc)
    # Используем время окончания предыдущей игры для кулдауна
    if chat_activity and "last_tos_game_end_time" in chat_activity:
        last_game_end_time = chat_activity["last_tos_game_end_time"]
        if last_game_end_time.tzinfo is None: # Убедимся, что есть таймзона
            last_game_end_time = last_game_end_time.replace(tzinfo=datetime.timezone.utc)
        
        if (now_utc_start - last_game_end_time).total_seconds() < TRUTH_OR_SHIT_COOLDOWN_SECONDS:
            remaining = TRUTH_OR_SHIT_COOLDOWN_SECONDS - (now_utc_start - last_game_end_time).total_seconds()
            await update.message.reply_text(f"🗿 Э, не так часто! Новая игра 'Правда или Высер' будет доступна через {int(remaining // 60)} мин {int(remaining % 60)} сек.")
            return
    # --->>> КОНЕЦ ПРОВЕРКИ КУЛДАУНА <<<---

    # --- Проверка, нет ли уже активной (нераскрытой) игры ---
    active_game = await loop.run_in_executor(
        None, lambda: active_truth_or_shit_games_collection.find_one({"chat_id": chat_id, "revealed": False})
    )
    if active_game:
        # Пересоздаем кнопки для существующей игры
        keyboard_active = [
            [
                InlineKeyboardButton("👍 Это Правда!", callback_data=f"tos_vote_true_{active_game['message_id_question']}"),
                InlineKeyboardButton("👎 Это Высер!", callback_data=f"tos_vote_false_{active_game['message_id_question']}")
            ],
            [InlineKeyboardButton("🤔 Раскрыть ответ!", callback_data=f"tos_reveal_{active_game['message_id_question']}")]
        ]
        reply_markup_active = InlineKeyboardMarkup(keyboard_active)
        try:
            await context.bot.send_message(
                chat_id,
                text=f"🗿 Э, тормози, в этом чате уже идет игра 'Правда или Высер'! Вот она, голосуй или раскрывай:\n\n«{active_game['statement']}»",
                reply_markup=reply_markup_active,
                parse_mode='HTML'
            )
        except Exception as e_send_active:
             logger.error(f"Не удалось переотправить активную игру ToS: {e_send_active}")
             await update.message.reply_text(f"🗿 В этом чате уже идет игра, но я не смог ее переслать. Пиздец.")
        return

    thinking_msg = await update.message.reply_text("🗿 Ща я вам загадку от Попиздяки придумаю, готовьте свои куриные мозги...")

    should_be_truth = random.choice([True, False])

    if should_be_truth:
        statement_prompt = (
            "Ты - Попиздяка, кладезь странных, но реальных фактов. Придумай ОДИН МАЛОИЗВЕСТНЫЙ, но РЕАЛЬНЫЙ и ПРОВЕРЯЕМЫЙ факт. "
            "Он должен быть сформулирован как утверждение, коротко (1-2 предложения) и без указания, что это правда. "
            "Не используй фразы типа 'Попиздяка утверждает'. Просто сам факт."
            "\nПример: Медуза Turritopsis Dohrnii потенциально бессмертна."
        )
    else:
        statement_prompt = (
            "Ты - Попиздяка, генератор абсурдного бреда. Придумай ОДИН АБСОЛЮТНО ЛЖИВЫЙ, но НАУКООБРАЗНЫЙ и ПРАВДОПОДОБНО ЗВУЧАЩИЙ высер. "
            "Он должен быть сформулирован как утверждение, коротко (1-2 предложения) и без указания, что это ложь. "
            "Не используй фразы типа 'Попиздяка утверждает'. Просто сам высер."
            "\nПример: Если чихнуть с открытыми глазами, они вылетят из орбит со скоростью пробки от шампанского."
        )
    
    generated_statement_text = await _call_ionet_api(
        messages=[{"role": "user", "content": statement_prompt}],
        model_id=IONET_TEXT_MODEL_ID, max_tokens=100, temperature=0.85 # Температуру можно подкрутить
    )

    if thinking_msg:
        try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_msg.message_id)
        except Exception: pass

    if not generated_statement_text or generated_statement_text.startswith("[") or len(generated_statement_text.strip()) < 10: # Проверка на минимальную длину
        await update.message.reply_text("🗿 Мой ИИ-мозг сегодня выдал какую-то хуйню вместо загадки. Попробуйте позже или пните админа.")
        return
    
    final_statement_for_game = "🗿 Попиздяка утверждает: " + generated_statement_text.strip()

    question_message = await context.bot.send_message(
        chat_id=chat_id, 
        text=f"<b>Правда или Высер от Попиздяки?</b>\n\n{final_statement_for_game}", 
        parse_mode='HTML'
    )
    msg_id_for_callback = question_message.message_id

    keyboard = [
        [
            InlineKeyboardButton("👍 Это Правда!", callback_data=f"tos_vote_true_{msg_id_for_callback}"),
            InlineKeyboardButton("👎 Это Высер!", callback_data=f"tos_vote_false_{msg_id_for_callback}")
        ],
        [InlineKeyboardButton("🤔 Раскрыть ответ!", callback_data=f"tos_reveal_{msg_id_for_callback}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id_for_callback, reply_markup=reply_markup)

    game_data_to_save = {
        "chat_id": chat_id, "message_id_question": msg_id_for_callback,
        "statement": final_statement_for_game, "is_truth": should_be_truth,
        "created_at": now_utc_start, "votes": {}, "revealed": False
    }
    await loop.run_in_executor(None, lambda: active_truth_or_shit_games_collection.insert_one(game_data_to_save))
    logger.info(f"Игра 'Правда или Высер' запущена в чате {chat_id}. MsgID: {msg_id_for_callback}, Утверждение: '{final_statement_for_game[:50]}...', Ответ: {should_be_truth}")

    # Планируем авто-раскрытие
    job_name = f"tos_auto_reveal_{chat_id}_{msg_id_for_callback}"
    # Удаляем старый job с таким же именем, если он вдруг остался (маловероятно, но для чистоты)
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for old_job in current_jobs:
        old_job.schedule_removal()
        logger.info(f"Удален старый job для ToS: {job_name}")

    context.job_queue.run_once(
        auto_reveal_truth_or_shit_job, 
        TRUTH_OR_SHIT_AUTO_REVEAL_DELAY_SECONDS,
        chat_id=chat_id, 
        data={'message_id_question': msg_id_for_callback, 'source_user_id': user.id}, # source_user_id на всякий случай
        name=job_name
    )
    logger.info(f"Запланирован авто-ревил для игры {job_name} через {TRUTH_OR_SHIT_AUTO_REVEAL_DELAY_SECONDS} сек.")

# --- КОНЕЦ КОМАНДЫ ЗАПУСКА ИГРЫ ---

# --- ОБРАБОТЧИК КНОПОК ДЛЯ "ПРАВДА ИЛИ ВЫСЕР" ---
async def truth_or_shit_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.message: # Добавил проверку query.message
        logger.warning("truth_or_shit_button_callback получен без query или query.data или query.message")
        if query: await query.answer("Ошибка: нет данных для обработки.") # Отвечаем на коллбэк, если он есть
        return
        
    await query.answer() # Обязательно ответить на колбэк, можно с текстом alert'а

    callback_data_parts = query.data.split("_") # tos_vote_true_MSGID или tos_reveal_MSGID
    
    if len(callback_data_parts) < 3:
        logger.error(f"Некорректный формат callback_data для ToS: {query.data}")
        try: await query.edit_message_text(text="Что-то пошло не так с этой кнопкой... Формат нарушен.")
        except Exception: pass
        return

    action_prefix = callback_data_parts[0] # "tos"
    action_type = callback_data_parts[1]   # "vote" или "reveal"
    
    try:
        original_question_msg_id = int(callback_data_parts[-1]) # Последний элемент - ID
    except (IndexError, ValueError):
        logger.error(f"Не удалось извлечь message_id из callback_data ToS: {query.data}")
        try: await query.edit_message_text(text="Ошибка: не могу найти ID исходной игры.")
        except Exception: pass
        return

    chat_id = query.message.chat_id
    user_who_clicked = query.from_user # Это объект telegram.User
    loop = asyncio.get_running_loop()

    # Найти активную игру (еще не раскрытую)
    game_data = await loop.run_in_executor(
        None, lambda: active_truth_or_shit_games_collection.find_one(
            {"chat_id": chat_id, "message_id_question": original_question_msg_id, "revealed": False}
        )
    )

    if not game_data:
        already_revealed_game = await loop.run_in_executor( # Проверим, может она уже раскрыта
             None, lambda: active_truth_or_shit_games_collection.find_one(
                {"chat_id": chat_id, "message_id_question": original_question_msg_id, "revealed": True}
            )
        )
        if already_revealed_game:
             text_for_old_game = (f"<b>Игра 'Правда или Высер' ОКОНЧЕНА!</b>\n\n"
                                 f"Утверждение Попиздяки было:\n«<i>{already_revealed_game['statement']}</i>»\n\n"
                                 f"И это был... <b>{'✅ ПРАВДА!' if already_revealed_game['is_truth'] else '❌ ВЫСЕР ЕБАНЫЙ!'}</b>\n\n"
                                 "🗿 Поезд ушел, лошара! Следи за игрой внимательнее в следующий раз.")
             try:
                await query.edit_message_text(text=text_for_old_game, parse_mode='HTML', reply_markup=None)
             except Exception as e_edit_old:
                logger.info(f"Не удалось отредактировать старую игру ToS (уже раскрыта): {e_edit_old}")

        else: # Игры вообще нет
            try: await query.edit_message_text(text="🗿 Эта игра уже закончилась, протухла или ее спиздили инопланетяне.")
            except Exception: pass
        # В любом случае убираем кнопки, если они еще есть у сообщения, на которое нажали
        try: await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=query.message.message_id, reply_markup=None)
        except Exception: pass
        return

    # --- Обработка ГОЛОСОВАНИЯ ---
    if action_type == "vote":
        if len(callback_data_parts) < 4: # tos_vote_CHOICE_MSGID
             logger.error(f"Некорректный формат callback_data для голосования ToS: {query.data}")
             try: await query.edit_message_text(text="Ошибка кнопки голосования.")
             except Exception: pass
             return

        vote_choice_str = callback_data_parts[2] # "true" или "false"
        user_vote_as_bool = (vote_choice_str == "true")

        # Запись голоса
        # Мы не можем напрямую обновить поле в словаре votes без $set и указания ключа user_id
        # Поэтому используем $set с "точечной нотацией"
        update_result = await loop.run_in_executor(
            None, lambda: active_truth_or_shit_games_collection.update_one(
                {"_id": game_data["_id"]}, # Находим по уникальному _id документа игры
                {"$set": {f"votes.{user_who_clicked.id}": {"name": user_who_clicked.first_name, "vote": user_vote_as_bool} }}
            )
        )
        
        if update_result.modified_count > 0:
            logger.info(f"Пользователь {user_who_clicked.first_name} ({user_who_clicked.id}) в чате {chat_id} проголосовал '{user_vote_as_bool}' за игру msg_id {original_question_msg_id}")
            # Обновляем текст сообщения, чтобы показать, что голос принят
            # (можно просто ответить на callback без изменения текста сообщения, если не хотим спамить редактированием)
            # await query.answer(f"Твой голос '{('Правда' if user_vote_as_bool else 'Высер')}' принят!")

            # Опционально: обновить сообщение, добавив туда имя проголосовавшего
            current_statement = game_data['statement']
            new_text_after_vote = (f"<b>Правда или Высер от Попиздяки?</b>\n\n{current_statement}\n\n"
                                   f"----------------\n"
                                   f"🗿 {user_who_clicked.mention_html()} считает, что это <b>{('Правда' if user_vote_as_bool else 'Высер')}</b>. Ждем остальных дебилов или жми 'Раскрыть'.")
            try:
                await query.edit_message_text(text=new_text_after_vote, parse_mode='HTML', reply_markup=query.message.reply_markup)
            except telegram.error.BadRequest as e_vote_edit: # Message is not modified
                 if "message is not modified" not in str(e_vote_edit).lower():
                     logger.warning(f"Ошибка редактирования сообщения ToS после голоса: {e_vote_edit}")
                 else: # Если не изменилось (например, юзер переголосовал так же) - просто отвечаем на коллбэк
                     await query.answer(f"Твой голос '{('Правда' if user_vote_as_bool else 'Высер')}' уже был таким.")
            except Exception as e_unhandled_vote_edit:
                 logger.error(f"Непредвиденная ошибка редактирования сообщения ToS после голоса: {e_unhandled_vote_edit}")


        else: # Голос не изменился или ошибка обновления
            logger.warning(f"Не удалось обновить голос для {user_who_clicked.id} в игре {original_question_msg_id}")
            await query.answer("Что-то пошло не так с твоим голосом или ты уже так голосовал.")

    # --- Обработка РАСКРЫТИЯ ОТВЕТА ---
    elif action_type == "reveal":
        logger.info(f"Пользователь {user_who_clicked.first_name} ({user_who_clicked.id}) нажал 'Раскрыть ответ' для игры msg_id {original_question_msg_id}.")
        
        # Удаляем запланированный job авто-раскрытия, так как раскрываем вручную
        job_name_to_remove = f"tos_auto_reveal_{chat_id}_{original_question_msg_id}"
        current_jobs_reveal = context.job_queue.get_jobs_by_name(job_name_to_remove)
        if current_jobs_reveal:
            for old_job_reveal in current_jobs_reveal:
                old_job_reveal.schedule_removal()
            logger.info(f"Удален запланированный job авто-ревила: {job_name_to_remove}")
        else:
            logger.info(f"Не найден job для удаления при ручном ревиле: {job_name_to_remove} (возможно, уже сработал или ошибка).")

        await _reveal_truth_or_shit_answer(context, chat_id, original_question_msg_id, triggered_by_user=user_who_clicked)
# --- КОНЕЦ ОБРАБОТЧИКА КНОПОК ---

# Импорты: InlineKeyboardMarkup, InlineKeyboardButton, User (если еще нет)

async def start_tos_battle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.chat or not update.message.from_user:
        return

    chat_id = update.message.chat.id
    host_user = update.message.from_user
    loop = asyncio.get_running_loop()

    # --->>> ПРОВЕРКА ТЕХРАБОТ (стандартная) <<<---
    # ... (скопируй из других функций)
    maintenance_active = await is_maintenance_mode(loop)
    if maintenance_active and (host_user.id != ADMIN_USER_ID or update.message.chat.type != 'private'):
        await update.message.reply_text("🔧 Техработы, не до эпичных заруб.")
        return

    # --->>> ПРОВЕРКА КУЛДАУНА БАТТЛА <<<---
    chat_activity = await loop.run_in_executor(
        None, lambda: chat_activity_collection.find_one({"chat_id": chat_id})
    )
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if chat_activity and "last_tos_battle_end_time" in chat_activity:
        last_battle_end_time = chat_activity["last_tos_battle_end_time"]
        if last_battle_end_time.tzinfo is None:
            last_battle_end_time = last_battle_end_time.replace(tzinfo=datetime.timezone.utc)
        if (now_utc - last_battle_end_time).total_seconds() < TOS_BATTLE_COOLDOWN_SECONDS:
            remaining = TOS_BATTLE_COOLDOWN_SECONDS - (now_utc - last_battle_end_time).total_seconds()
            await update.message.reply_text(f"🗿 Не так быстро, чемпион! Новый Баттл 'Правда или Высер' можно будет запустить через {int(remaining // 60)} мин {int(remaining % 60)} сек.")
            return

    # --- Проверка, нет ли уже активной игры (набор или идет) ---
    active_battle = await loop.run_in_executor(
        None, lambda: tos_battles_collection.find_one({"chat_id": chat_id, "status": {"$in": ["recruiting", "playing"]}})
    )
    if active_battle:
        status_text = "идет набор участников" if active_battle['status'] == 'recruiting' else "уже в самом разгаре"
        await update.message.reply_text(f"🗿 Э, тормози, в этом чате уже {status_text} Баттл 'Правда или Высер'! Дождись окончания или участвуй, если еще можно.")
        # Можно переслать сообщение о наборе, если оно еще актуально
        if active_battle['status'] == 'recruiting' and 'message_id_recruitment' in active_battle:
             # Логика пересылки сообщения с кнопками (позже, если нужно)
             pass
        return

    # --- Создание новой игры ---
    recruitment_ends_at = now_utc + datetime.timedelta(seconds=TOS_BATTLE_RECRUITMENT_DURATION_SECONDS)

    recruitment_ends_at_msk = recruitment_ends_at.astimezone(MOSCOW_TZ)
    
    # Сообщение о наборе
    recruitment_text = (
        f"📢 <b>ВНИМАНИЕ, ДОЛБОЕБЫ!</b> 📢\n\n"
        f"{host_user.mention_html()} затеял эпичный Баттл <b>'Правда или Высер от Попиздяки'</b> на {TOS_BATTLE_NUM_QUESTIONS} раундов!\n"
        f"Собираем отряд самых отбитых интеллектуалов (или просто везучих ублюдков)!\n\n"
        f"🏆 <b>Приз победителю:</b> +{TOS_BATTLE_PENIS_REWARD_CM} см к писюну ИЛИ +{TOS_BATTLE_TITS_REWARD_SIZE} к размеру сисек (на выбор победителя, хе-хе)!\n\n"
        f"Набор открыт до: <b>{recruitment_ends_at_msk.strftime('%H:%M:%S MSK')}</b> (примерно {TOS_BATTLE_RECRUITMENT_DURATION_SECONDS // 60} мин.)\n"
        f"Жми кнопку, если не ссышь!"
    )
    
    # Кнопки для набора
    # callback_data: tosbattle_ACTION_GAMEID_OPTIONALDATA
    # GAMEID будет message_id сообщения о наборе, чтобы его легко найти
    # Для простоты, пока без GAMEID в кнопках, будем искать по chat_id и статусу
    keyboard_recruitment = [
        [InlineKeyboardButton("✅ Я В ДЕЛЕ!", callback_data="tosbattle_join")],
        # Кнопки для хоста появятся после отправки сообщения и сохранения game_id
    ]
    reply_markup = InlineKeyboardMarkup(keyboard_recruitment)
    
    recruitment_message = await context.bot.send_message(chat_id, text=recruitment_text, parse_mode='HTML', reply_markup=reply_markup)
    game_id = recruitment_message.message_id
    
    # Закрепляем сообщение о наборе
    try:
        await context.bot.pin_chat_message(
            chat_id=chat_id, 
            message_id=game_id, 
            disable_notification=False # Уведомить участников чата
        )
        logger.info(f"Сообщение о наборе на баттл {game_id} закреплено в чате {chat_id}.")
    except telegram.error.BadRequest as e_pin: # Чаще всего "Not enough rights to pin a message"
        logger.warning(f"Не удалось закрепить сообщение о наборе {game_id}: {e_pin}. Возможно, нет прав.")
    except Exception as e_pin_unknown:
        logger.error(f"Неизвестная ошибка при закреплении сообщения о наборе {game_id}: {e_pin_unknown}")

    # Обновляем кнопки, добавляя кнопки для хоста
    keyboard_recruitment_host = [
        [InlineKeyboardButton("✅ Я В ДЕЛЕ!", callback_data=f"tosbattle_join_{game_id}")],
        [
            InlineKeyboardButton("➕30сек (Хост)", callback_data=f"tosbattle_extend_{game_id}"),
            InlineKeyboardButton("🏁 Начать! (Хост)", callback_data=f"tosbattle_start_{game_id}")
        ],
        # --->>> НОВАЯ КНОПКА ОТМЕНЫ ДЛЯ ХОСТА <<<---
        [InlineKeyboardButton("❌ Отменить Баттл (Хост)", callback_data=f"tosbattle_cancel_{game_id}")]
        # --->>> КОНЕЦ НОВОЙ КНОПКИ <<<---
    ]
    reply_markup_host = InlineKeyboardMarkup(keyboard_recruitment_host)
    try:
        await context.bot.edit_message_reply_markup(chat_id, message_id=game_id, reply_markup=reply_markup_host)
    except Exception as e_edit_host_kb: # Изменил имя переменной для ошибки
        logger.error(f"Не удалось обновить кнопки для хоста в ToS Battle (game_id: {game_id}): {e_edit_host_kb}")


    # Сохраняем игру в БД
    battle_data = {
        "chat_id": chat_id,
        "game_id": game_id, 
        "status": "recruiting",
        "host_id": host_user.id,
        "host_name": host_user.first_name or host_user.username or "Анонимный Заводила",
        "created_at": now_utc, # now_utc должен быть определен
        "recruitment_ends_at": recruitment_ends_at,
        "participants": {}, 
        "questions": [], 
        "current_question_index": -1,
        "message_id_recruitment": game_id,
        "message_id_current_question": None,
        "message_id_last_extension_notice": None, # <<<--- ВОТ ЭТО ПОЛЕ
        "prizes_awarded_info": {} 
    }
    await loop.run_in_executor(None, lambda: tos_battles_collection.insert_one(battle_data))
    logger.info(f"Баттл 'Правда или Высер' (game_id: {game_id}) запущен хостом {host_user.id} в чате {chat_id}. Набор до {recruitment_ends_at}.")

    # Планируем окончание набора, если хост не начнет раньше
    job_name = f"tosbattle_recruit_end_{chat_id}_{game_id}"
    context.job_queue.run_once(
        auto_end_recruitment_job,
        (recruitment_ends_at - now_utc).total_seconds(), # Время до окончания
        chat_id=chat_id,
        data={'game_id': game_id, 'host_id': host_user.id},
        name=job_name
    )
    logger.info(f"Запланировано окончание набора для баттла {job_name}.")

async def tos_battle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.message:
        logger.warning("tos_battle_button_callback: получен неполный CallbackQuery.")
        if query: await query.answer("Ошибка: неполные данные для обработки колбэка.", show_alert=True)
        return
            
    await query.answer() # Отвечаем на callback query, чтобы убрать "часики" у кнопки

    callback_data_full = query.data
    parts = callback_data_full.split("_") # e.g., "tosbattle_join_GAMEID" or "tosbattle_ans_GAMEID_QINDEX_CHOICE"

    if not (parts and parts[0] == "tosbattle" and len(parts) >= 2):
        logger.warning(f"tos_battle_button_callback: Некорректный префикс или длина callback_data: {callback_data_full}")
        try: await query.edit_message_text("Ошибка: Неверный формат данных кнопки баттла.")
        except Exception: pass 
        return

    action = parts[1]
    chat_id = query.message.chat.id
    user_who_clicked = query.from_user 
    loop = asyncio.get_running_loop()

    game_id_from_cb_str = None
    if action in ["extend", "start", "cancel"] and len(parts) >= 3: # tosbattle_ACTION_GAMEID
        game_id_from_cb_str = parts[2]
    elif action == "ans" and len(parts) >= 4: # tosbattle_ans_GAMEID_QINDEX_CHOICE
        game_id_from_cb_str = parts[2]
    elif action == "prize" and len(parts) >= 5: # tosbattle_prize_TYPE_GAMEID_WINNERID
        game_id_from_cb_str = parts[3] # GAMEID здесь 3-й элемент
    elif action == "join" and len(parts) >= 3: # tosbattle_join_GAMEID (необязательный, но если есть)
        game_id_from_cb_str = parts[2]
    
    game_id_int = None
    if game_id_from_cb_str:
        try:
            game_id_int = int(game_id_from_cb_str)
        except ValueError:
            logger.error(f"tos_battle_button_callback: Не удалось преобразовать game_id '{game_id_from_cb_str}' в int. CB: {callback_data_full}")
            try: await query.edit_message_text("Ошибка: Неверный ID игры в данных кнопки.")
            except Exception: pass
            return

    battle_search_filter = {"chat_id": chat_id}
    if game_id_int:
        battle_search_filter["game_id"] = game_id_int
    
    expected_status = None
    if action in ["join", "extend", "start", "cancel"]:
        expected_status = "recruiting"
    elif action == "ans":
        expected_status = "playing"
    elif action == "prize": 
        expected_status = "finished" 

    if expected_status:
        battle_search_filter["status"] = expected_status
    
    if action == "join" and not game_id_int: # Для кнопки "Я в деле" без game_id
        battle_search_filter.pop("game_id", None) 
        battle_search_filter["status"] = "recruiting" # Ищем любую игру в наборе

    battle = await loop.run_in_executor(
        None, lambda: tos_battles_collection.find_one(battle_search_filter)
    )

    if not battle:
        # Если для join без game_id не нашли, а game_id_from_cb был None, значит игра не найдена
        if action == "join" and not game_id_from_cb_str: # Проверяем game_id_from_cb_str, т.к. game_id_int мог не инициализироваться
             active_recruiting_battle_fallback = await loop.run_in_executor(
                None, lambda: tos_battles_collection.find_one({"chat_id": chat_id, "status": "recruiting"})
             )
             if active_recruiting_battle_fallback:
                 battle = active_recruiting_battle_fallback
                 game_id_int = battle["game_id"] 
             else:
                try: await query.edit_message_text("🗿 Набор на этот Баттл уже завершен, отменен или я потерял его следы. Попробуй запустить новый.")
                except Exception: pass
                try: await context.bot.edit_message_reply_markup(chat_id, message_id=query.message.message_id, reply_markup=None)
                except Exception: pass
                return
        else: # Если игра не найдена по другим критериям
            logger.info(f"tos_battle_button_callback: Актуальная игра для действия '{action}' (game_id: {game_id_int}, ожидаемый статус: {expected_status}) в чате {chat_id} не найдена.")
            not_found_msg_text = "🗿 Эта игра уже завершилась, отменена или произошла ошибка. Запусти новую, если не ссышь!"
            if action == "join" and not game_id_int : not_found_msg_text = "🗿 Активных наборов на Баттл в этом чате сейчас нет. Стань первым, запусти свой!"
            try: 
                await query.edit_message_text(not_found_msg_text)
                await context.bot.edit_message_reply_markup(chat_id, message_id=query.message.message_id, reply_markup=None)
            except Exception: pass
            return
    
    if not game_id_int and battle: # Это условие важно для кнопки "join" без game_id
        game_id_int = battle["game_id"]
    
    battle_doc_id = battle["_id"]

    # --- Обработка действий НАБОРА ("recruiting" status) ---
    if battle.get("status") == "recruiting":
        if action == "join":
            if str(user_who_clicked.id) in battle.get("participants", {}):
                await context.bot.send_message(chat_id, f"🗿 {user_who_clicked.mention_html()}, ты уже вписался, угомонись!", parse_mode='HTML', reply_to_message_id=game_id_int)
                return
            if len(battle.get("participants", {})) >= TOS_BATTLE_MAX_PARTICIPANTS:
                await context.bot.send_message(chat_id, f"🗿 {user_who_clicked.mention_html()}, мест нет, все забито долбоебами ({TOS_BATTLE_MAX_PARTICIPANTS} макс).", parse_mode='HTML', reply_to_message_id=game_id_int)
                return

            user_name_to_store = user_who_clicked.first_name or user_who_clicked.username or f"Анон-{user_who_clicked.id}"
            new_participant_data = {"name": user_name_to_store, "score": 0, "answers": [None] * TOS_BATTLE_NUM_QUESTIONS}
            
            update_join = await loop.run_in_executor(
                None, lambda: tos_battles_collection.update_one(
                    {"_id": battle_doc_id}, {"$set": {f"participants.{user_who_clicked.id}": new_participant_data}}
                )
            )
            if update_join.modified_count > 0:
                logger.info(f"User {user_who_clicked.id} присоединился к баттлу {game_id_int}")
                await context.bot.send_message(chat_id, f"✅ {user_who_clicked.mention_html()} теперь в деле! Готовься позориться или блистать тупостью!", parse_mode='HTML', reply_to_message_id=game_id_int)
            else:
                await context.bot.send_message(chat_id, f"⚠️ {user_who_clicked.mention_html()}, ошибка записи. Попробуй еще.", parse_mode='HTML', reply_to_message_id=game_id_int)

        elif action == "extend" and user_who_clicked.id == battle.get("host_id"):
            # Сначала получим актуальное состояние баттла, включая message_id_last_extension_notice
            battle_current_for_extend = await loop.run_in_executor(None, lambda: tos_battles_collection.find_one({"_id": battle_doc_id})) # battle_doc_id должен быть определен ранее
            if not battle_current_for_extend or battle_current_for_extend.get("status") != "recruiting":
                await context.bot.send_message(chat_id, "Не удалось продлить: игра уже не в стадии набора или ошибка.", reply_to_message_id=game_id_int) # game_id_int должен быть определен ранее
                return
            
            current_recruitment_ends_at_from_db = battle_current_for_extend["recruitment_ends_at"]
            if current_recruitment_ends_at_from_db.tzinfo is None:
                current_recruitment_ends_at_from_db = UTC_TZ.localize(current_recruitment_ends_at_from_db) # UTC_TZ должен быть определен глобально
            else:
                current_recruitment_ends_at_from_db = current_recruitment_ends_at_from_db.astimezone(UTC_TZ)

            new_recruitment_ends_at_utc_for_update = current_recruitment_ends_at_from_db + datetime.timedelta(seconds=TOS_BATTLE_RECRUITMENT_EXTENSION_SECONDS)
            
            update_result_extend_time = await loop.run_in_executor(
                None, lambda: tos_battles_collection.update_one(
                    {"_id": battle_doc_id, "status": "recruiting"},
                    {"$set": {"recruitment_ends_at": new_recruitment_ends_at_utc_for_update}}
                )
            )
            
            if update_result_extend_time.modified_count > 0:
                logger.info(f"Хост {user_who_clicked.id} продлил набор для баттла {game_id_int} до {new_recruitment_ends_at_utc_for_update}")
                
                message_id_old_extension_notice = battle_current_for_extend.get("message_id_last_extension_notice")
                if message_id_old_extension_notice:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id_old_extension_notice)
                        logger.info(f"Удалено старое сообщение о продлении (ID: {message_id_old_extension_notice}) для баттла {game_id_int}")
                    except Exception as e_del_ext:
                        logger.warning(f"Не удалось удалить старое сообщение о продлении {message_id_old_extension_notice}: {e_del_ext}")

                job_name_ext_cb_fix = f"tosbattle_recruit_end_{chat_id}_{game_id_int}"
                for old_job_fix in context.job_queue.get_jobs_by_name(job_name_ext_cb_fix): 
                    old_job_fix.schedule_removal()
                
                time_now_utc_ext_cb_fix = datetime.datetime.now(datetime.timezone.utc)
                time_until_new_end_seconds_cb_fix = (new_recruitment_ends_at_utc_for_update - time_now_utc_ext_cb_fix).total_seconds()

                if time_until_new_end_seconds_cb_fix > 0:
                    context.job_queue.run_once(
                        auto_end_recruitment_job, time_until_new_end_seconds_cb_fix, 
                        chat_id=chat_id, data={'game_id': game_id_int, 'host_id': battle["host_id"]}, name=job_name_ext_cb_fix # battle["host_id"] из первоначально загруженного battle
                    )
                    logger.info(f"Job окончания набора для {game_id_int} перепланирован на {new_recruitment_ends_at_utc_for_update}")
                    
                    new_recruitment_ends_at_msk_display = new_recruitment_ends_at_utc_for_update.astimezone(MOSCOW_TZ) # MOSCOW_TZ должен быть определен глобально
                    remaining_minutes_display = int(time_until_new_end_seconds_cb_fix // 60)
                    remaining_seconds_part_display = int(time_until_new_end_seconds_cb_fix % 60)
                    time_left_str_display = f"{remaining_minutes_display} мин {remaining_seconds_part_display} сек"
                    
                    new_extension_notice_message = await context.bot.send_message(
                        chat_id, 
                        f"⏳ Хост {user_who_clicked.mention_html()} продлил набор на <b>{TOS_BATTLE_RECRUITMENT_EXTENSION_SECONDS} секунд</b>!\n"
                        f"Новое время окончания набора: <b>{new_recruitment_ends_at_msk_display.strftime('%H:%M:%S MSK')}</b> (осталось ~{time_left_str_display}).",
                        parse_mode='HTML', reply_to_message_id=game_id_int 
                    )
                    await loop.run_in_executor(
                        None, lambda: tos_battles_collection.update_one(
                            {"_id": battle_doc_id},
                            {"$set": {"message_id_last_extension_notice": new_extension_notice_message.message_id}}
                        )
                    )
                else: 
                    await context.bot.send_message(chat_id, "Хост пытался продлить, но время уже истекло или что-то пошло не так. Набор завершается...", reply_to_message_id=game_id_int)
                    job_data_manual = {'game_id': game_id_int, 'host_id': battle["host_id"], 'chat_id': chat_id} 
                    fake_job_manual = type('FakeJob', (), {'data': job_data_manual, 'chat_id': chat_id, 'name': f'manual_trigger_rec_end_{game_id_int}_extend_fail'})()
                    await auto_end_recruitment_job(context=ContextTypes.DEFAULT_TYPE(application=context.application, chat_id=chat_id, job=fake_job_manual))
            else:
                await context.bot.send_message(chat_id, "Не удалось продлить набор (возможно, игра уже не в стадии набора или произошла ошибка).", reply_to_message_id=game_id_int)
        
        elif action == "start" and user_who_clicked.id == battle.get("host_id"):
            if len(battle.get("participants", {})) < TOS_BATTLE_MIN_PARTICIPANTS:
                await context.bot.send_message(chat_id, f"🚫 Нужно хотя бы {TOS_BATTLE_MIN_PARTICIPANTS} участника, у нас {len(battle.get('participants', {}))}.", parse_mode='HTML', reply_to_message_id=game_id_int)
                return
            
            logger.info(f"Хост {user_who_clicked.id} запускает баттл {game_id_int} досрочно.")
            job_name_start_cb = f"tosbattle_recruit_end_{chat_id}_{game_id_int}"
            for old_job_s_cb in context.job_queue.get_jobs_by_name(job_name_start_cb): old_job_s_cb.schedule_removal()
            await _actually_start_the_battle_game(context, battle_doc_id)

        elif action == "cancel" and user_who_clicked.id == battle.get("host_id"):
            logger.info(f"Хост {user_who_clicked.id} нажал кнопку отмены баттла {game_id_int} в чате {chat_id}.")
            update_cancel_result_cb = await loop.run_in_executor(
                None, lambda: tos_battles_collection.find_one_and_update(
                    {"_id": battle_doc_id, "status": "recruiting"},
                    {"$set": {"status": "cancelled_by_host", "finished_at": datetime.datetime.now(datetime.timezone.utc)}},
                    return_document=pymongo.ReturnDocument.AFTER
                )
            )
            if not update_cancel_result_cb or update_cancel_result_cb.get("status") != "cancelled_by_host":
                logger.warning(f"Не удалось отменить баттл {game_id_int}: он уже не в статусе 'recruiting' или ошибка БД.")
                await query.answer("Не удалось отменить игру.", show_alert=True)
                try: await query.edit_message_reply_markup(reply_markup=None)
                except Exception: pass
                return

            try: await context.bot.unpin_chat_message(chat_id=chat_id, message_id=game_id_int)
            except Exception: pass 
            try:
                await query.edit_message_text(
                    text=f"🚫 Хост {user_who_clicked.mention_html()} <b>ОТМЕНИЛ Баттл (ID: {game_id_int})</b>!\n🗿 Расходитесь.",
                    parse_mode='HTML', reply_markup=None
                )
            except Exception as e_edit_cancel_cb:
                logger.warning(f"Не удалось отредактировать сообщение при отмене баттла {game_id_int}: {e_edit_cancel_cb}")
                await context.bot.send_message(chat_id, f"🚫 Хост {user_who_clicked.mention_html()} <b>ОТМЕНИЛ Баттл (ID: {game_id_int})</b>!", parse_mode='HTML', reply_to_message_id=game_id_int)

            job_name_to_cancel_cb_j = f"tosbattle_recruit_end_{chat_id}_{game_id_int}"
            for old_job_cb_cancel_j in context.job_queue.get_jobs_by_name(job_name_to_cancel_cb_j): old_job_cb_cancel_j.schedule_removal()
            
            await loop.run_in_executor(
                None, lambda: chat_activity_collection.update_one(
                    {"chat_id": chat_id}, {"$set": {"last_tos_battle_end_time": datetime.datetime.now(datetime.timezone.utc)}}, upsert=True
                )
            )
            logger.info(f"Баттл {game_id_int} отменен хостом. Кулдаун обновлен.")
        
        else: 
            if user_who_clicked.id != battle.get("host_id") and action in ["extend", "start", "cancel"]:
                 await query.answer("Только хост игры может это сделать!", show_alert=True)
            elif action == "ans":
                 await query.answer("Игра еще не началась!", show_alert=True)

    # --- Обработка ОТВЕТОВ НА ВОПРОСЫ ("playing" status) ---
    elif battle.get("status") == "playing" and action == "ans":
        if len(parts) < 5: # tosbattle_ans_GAMEID_QINDEX_CHOICE
            logger.error(f"Некорректный CB для ответа на вопрос (playing): {query.data}")
            # await query.answer("Ошибка формата кнопки ответа.", show_alert=True) # Убираем query.answer
            return
        
        try:
            # game_id_from_ans_cb (game_id_int) должен быть определен ранее
            question_index_cb_ans = int(parts[3])
            answer_choice_cb_str_ans = parts[4] # "true" или "false"
        except (ValueError, IndexError) as e_parse_ans_cb_p:
            logger.error(f"Ошибка парсинга CB ответа на вопрос (playing): {query.data}, {e_parse_ans_cb_p}")
            # await query.answer("Ошибка данных кнопки.", show_alert=True) # Убираем query.answer
            return

        user_answer_as_bool_ans = (answer_choice_cb_str_ans == "true")

        if str(user_who_clicked.id) not in battle.get("participants", {}):
            # await query.answer("Ты не участвуешь в этом баттле, самозванец хуев!", show_alert=True) # Убираем query.answer
            # Можно отправить обычное сообщение, если очень хочется уведомить
            await context.bot.send_message(chat_id, f"@{user_who_clicked.username or user_who_clicked.first_name}, ты не в игре!", reply_to_message_id=query.message.message_id)
            return

        current_q_idx_from_db_ans = battle.get("current_question_index", -1)
        if current_q_idx_from_db_ans != question_index_cb_ans:
            # await query.answer("Это уже не текущий вопрос или ты проебал все полимеры!", show_alert=True) # Убираем
            return # Просто выходим, не меняя кнопки, если вопрос не актуален
        
        questions_list_db_ans = battle.get("questions", [])
        if question_index_cb_ans >= len(questions_list_db_ans) or \
           questions_list_db_ans[question_index_cb_ans].get("revealed_to_users"):
            # await query.answer("Этот вопрос уже был раскрыт или что-то пошло не так с его номером.", show_alert=True) # Убираем
            # Если вопрос раскрыт, можно попробовать убрать кнопки
            try: await query.edit_message_reply_markup(reply_markup=None)
            except Exception: pass
            return

        # Получаем актуальные ответы на этот вопрос из БД, чтобы проверить, не голосовал ли юзер уже
        battle_reloaded_for_ans_check_cb = await loop.run_in_executor(None, lambda: tos_battles_collection.find_one({"_id": battle_doc_id}))
        if not battle_reloaded_for_ans_check_cb:
            # await query.answer("Ошибка: не могу проверить твой предыдущий ответ.", show_alert=True) # Убираем
            return
            
        if "questions" not in battle_reloaded_for_ans_check_cb or \
           question_index_cb_ans >= len(battle_reloaded_for_ans_check_cb["questions"]):
            logger.error(f"Структура вопросов нарушена или неверный индекс {question_index_cb_ans} для баттла {game_id_int}")
            # await query.answer("Внутренняя ошибка игры: структура вопросов нарушена.", show_alert=True) # Убираем
            return
            
        user_answers_this_q_db_ans_updated_cb = battle_reloaded_for_ans_check_cb["questions"][question_index_cb_ans].get("user_answers_to_this_q", {})
        
        if str(user_who_clicked.id) in user_answers_this_q_db_ans_updated_cb:
            # await query.answer(f"Ты уже отвечал на этот раунд! Твой выбор был: ...", show_alert=True) # Убираем
            # Вместо этого можно ничего не делать или отправить обычное сообщение в чат
            # await context.bot.send_message(chat_id, f"@{user_who_clicked.username or user_who_clicked.first_name}, ты уже голосовал на этом раунде!", reply_to_message_id=query.message.message_id)
            return # Выходим, если уже голосовал

        user_name_ans_rec_db_cb = user_who_clicked.first_name or user_who_clicked.username or f"Анон-{user_who_clicked.id}"
        answer_record_to_db_ans_cb = {"name": user_name_ans_rec_db_cb, "answer_bool": user_answer_as_bool_ans, "answered_at": datetime.datetime.now(datetime.timezone.utc)}
        
        update_ans_q_db_cb = await loop.run_in_executor(
            None, lambda: tos_battles_collection.update_one(
                {"_id": battle_doc_id, f"questions.{question_index_cb_ans}.revealed_to_users": False}, 
                {"$set": {f"questions.{question_index_cb_ans}.user_answers_to_this_q.{user_who_clicked.id}": answer_record_to_db_ans_cb}}
            )
        )

        if update_ans_q_db_cb.modified_count > 0:
            logger.info(f"User {user_who_clicked.id} ответил '{user_answer_as_bool_ans}' на Q{question_index_cb_ans} баттла {game_id_int}")
            
            # --->>> ОБНОВЛЕНИЕ КНОПОК СО СЧЕТЧИКАМИ <<<---
            # Получаем самые свежие данные об ответах на этот вопрос ПОСЛЕ нашего обновления
            battle_after_vote = await loop.run_in_executor(None, lambda: tos_battles_collection.find_one({"_id": battle_doc_id}))
            if not battle_after_vote or "questions" not in battle_after_vote or \
               question_index_cb_ans >= len(battle_after_vote["questions"]):
                logger.error(f"Не удалось получить обновленный баттл для обновления кнопок Q{question_index_cb_ans}")
                return # Выходим, чтобы не сломать клавиатуру

            current_q_answers = battle_after_vote["questions"][question_index_cb_ans].get("user_answers_to_this_q", {})
            
            votes_for_true = 0
            votes_for_false = 0
            for _, ans_data in current_q_answers.items():
                if ans_data["answer_bool"] is True:
                    votes_for_true += 1
                elif ans_data["answer_bool"] is False:
                    votes_for_false += 1
            
            # Формируем новый текст для кнопок
            button_text_true = f"👍 Это Правда! ({votes_for_true})"
            button_text_false = f"👎 Это Высер! ({votes_for_false})"

            # Создаем новую клавиатуру
            # GAMEID здесь - это message_id_recruitment (переменная game_id_int)
            # QINDEX - это question_index_cb_ans
            new_keyboard_with_counts = [
                [
                    InlineKeyboardButton(button_text_true, callback_data=f"tosbattle_ans_{game_id_int}_{question_index_cb_ans}_true"),
                    InlineKeyboardButton(button_text_false, callback_data=f"tosbattle_ans_{game_id_int}_{question_index_cb_ans}_false")
                ]
            ]
            new_reply_markup = InlineKeyboardMarkup(new_keyboard_with_counts)

            try:
                # Редактируем исходное сообщение с вопросом (query.message)
                await query.edit_message_reply_markup(reply_markup=new_reply_markup)
                logger.info(f"Кнопки для Q{question_index_cb_ans} баттла {game_id_int} обновлены счетчиками: T={votes_for_true}, F={votes_for_false}")
            except telegram.error.BadRequest as e_edit_kb_counts:
                 if "message is not modified" not in str(e_edit_kb_counts).lower(): # Игнорируем, если кнопки уже такие
                     logger.warning(f"Не удалось отредактировать кнопки со счетчиками: {e_edit_kb_counts}")
            except Exception as e_unhandled_edit_kb_counts:
                logger.error(f"Непредвиденная ошибка при редактировании кнопок со счетчиками: {e_unhandled_edit_kb_counts}")
            # --->>> КОНЕЦ ОБНОВЛЕНИЯ КНОПОК <<<---

        else: # modified_count == 0
            logger.warning(f"Не удалось записать ответ для user {user_who_clicked.id} на Q{question_index_cb_ans} баттла {game_id_int}. Modified_count: {update_ans_q_db_cb.modified_count}")

    # --- Обработка ВЫБОРА ПРИЗА ("finished" status) ---
    elif battle.get("status") == "finished" and action == "prize":
        if len(parts) < 5: 
            logger.error(f"Некорректный CB для выбора приза: {query.data}")
            await query.answer("Ошибка формата кнопки приза.", show_alert=True)
            return
        
        prize_type_choice_cb = parts[2] 
        try:
            winner_id_from_prize_cb_val = int(parts[4])
        except (ValueError, IndexError) as e_parse_prize_cb_val:
            logger.error(f"Ошибка парсинга CB приза: {query.data}, {e_parse_prize_cb_val}")
            await query.answer("Ошибка данных кнопки приза.", show_alert=True)
            return

        if user_who_clicked.id != winner_id_from_prize_cb_val:
            await query.answer("Это не твой приз, не лезь!", show_alert=True)
            return
        
        prizes_awarded_info_db = battle.get("prizes_awarded_info", {})
        if str(winner_id_from_prize_cb_val) in prizes_awarded_info_db and \
           prizes_awarded_info_db[str(winner_id_from_prize_cb_val)].get("type_chosen"): # Если приз уже выбран
            await query.answer("Приз уже был выбран и выдан за этот баттл.", show_alert=True)
            try: await query.edit_message_reply_markup(reply_markup=None)
            except Exception: pass
            return

        try:
            await query.edit_message_reply_markup(reply_markup=None) 
        except Exception as e_edit_prize_kb_cb_val:
            logger.warning(f"Не удалось убрать кнопки выбора приза: {e_edit_prize_kb_cb_val}")

        user_profile_prize_cb_val = await get_user_profile_data(user_who_clicked)
        winner_display_name_prize_cb = user_profile_prize_cb_val.get("display_name", user_who_clicked.first_name or "Победитель")
        prize_applied_msg_cb = ""
        awarded_penis = 0
        awarded_tits = 0.0

        if prize_type_choice_cb == "penis":
            penis_stat_prize_cb_val = await loop.run_in_executor(None, lambda: penis_stats_collection.find_one({"user_id": winner_id_from_prize_cb_val, "chat_id": chat_id}))
            current_penis_size_cb_val = penis_stat_prize_cb_val.get("penis_size", 0) if penis_stat_prize_cb_val else 0
            # Приз для одного победителя (TOS_BATTLE_PENIS_REWARD_CM)
            new_penis_size_cb_val = current_penis_size_cb_val + TOS_BATTLE_PENIS_REWARD_CM 
            awarded_penis = TOS_BATTLE_PENIS_REWARD_CM
            await loop.run_in_executor(None, lambda: penis_stats_collection.update_one(
                {"user_id": winner_id_from_prize_cb_val, "chat_id": chat_id},
                {"$set": {"penis_size": new_penis_size_cb_val, "user_display_name": winner_display_name_prize_cb}}, upsert=True
            ))
            prize_applied_msg_cb = f"🍆 Писюн <b>{winner_display_name_prize_cb}</b> ВНЕЗАПНО вырос на {TOS_BATTLE_PENIS_REWARD_CM}см и теперь составляет <b>{new_penis_size_cb_val}см</b>!"
            logger.info(f"Приз (писюн +{TOS_BATTLE_PENIS_REWARD_CM}) выдан {winner_display_name_prize_cb} за баттл {game_id_int}.")
            
        elif prize_type_choice_cb == "tits":
            tits_stat_prize_cb_val = await loop.run_in_executor(None, lambda: tits_stats_collection.find_one({"user_id": winner_id_from_prize_cb_val, "chat_id": chat_id}))
            current_tits_size_cb_val = float(tits_stat_prize_cb_val.get("tits_size", 0.0)) if tits_stat_prize_cb_val else 0.0
            # Приз для одного победителя (TOS_BATTLE_TITS_REWARD_SIZE)
            new_tits_size_cb_val = round(current_tits_size_cb_val + TOS_BATTLE_TITS_REWARD_SIZE, 1)
            awarded_tits = TOS_BATTLE_TITS_REWARD_SIZE
            await loop.run_in_executor(None, lambda: tits_stats_collection.update_one(
                {"user_id": winner_id_from_prize_cb_val, "chat_id": chat_id},
                {"$set": {"tits_size": new_tits_size_cb_val, "user_display_name": winner_display_name_prize_cb}}, upsert=True
            ))
            prize_applied_msg_cb = f"🍈 Сиськи <b>{winner_display_name_prize_cb}</b> подросли на {TOS_BATTLE_TITS_REWARD_SIZE:.1f} размера и стали <b>{new_tits_size_cb_val:.1f}-го</b>!"
            logger.info(f"Приз (сиськи +{TOS_BATTLE_TITS_REWARD_SIZE:.1f}) выдан {winner_display_name_prize_cb} за баттл {game_id_int}.")
        
        if prize_applied_msg_cb:
            await context.bot.send_message(chat_id, text=f"🎉 <b>Награда нашла героя!</b> 🎉\n{prize_applied_msg_cb}", parse_mode='HTML')
            # Помечаем, что приз выдан и какой именно
            await loop.run_in_executor(None, lambda: tos_battles_collection.update_one(
                {"_id": battle_doc_id}, 
                {"$set": {f"prizes_awarded_info.{winner_id_from_prize_cb_val}": {"type_chosen": prize_type_choice_cb, "penis_added": awarded_penis, "tits_added": awarded_tits}}}
            ))
        else:
            await query.answer("Неизвестный тип приза.", show_alert=True)
            
    else: 
        logger.warning(f"Неизвестное действие '{action}' или несоответствующий статус '{battle.get('status')}' в tos_battle_button_callback. CB: {query.data}")

async def _actually_start_the_battle_game(context: ContextTypes.DEFAULT_TYPE, battle_doc_id: ObjectId) -> None:
    loop = asyncio.get_running_loop()
    battle = await loop.run_in_executor(None, lambda: tos_battles_collection.find_one({"_id": battle_doc_id}))
    
    if not battle:
        logger.error(f"_actually_start_the_battle_game: Баттл с _id {battle_doc_id} не найден!")
        return
    
    # Проверяем, не пытаемся ли мы начать уже идущую или завершенную игру
    if battle.get("status") != "recruiting":
        logger.warning(f"_actually_start_the_battle_game: Попытка начать баттл (game_id: {battle.get('game_id')}), который уже не в статусе 'recruiting'. Текущий статус: {battle.get('status')}")
        return

    chat_id = battle["chat_id"]
    game_id = battle["game_id"] # message_id_recruitment
    participants_count = len(battle.get("participants", {}))
    host_name = battle.get("host_name", "Неизвестный хост")

    logger.info(f"Начало подготовки баттла {game_id} в чате {chat_id}. Участников: {participants_count}")

    # Открепляем сообщение о наборе
    try:
        await context.bot.unpin_chat_message(chat_id=chat_id, message_id=game_id)
        logger.info(f"Сообщение о наборе на баттл {game_id} откреплено в чате {chat_id}.")
    except telegram.error.BadRequest as e_unpin: # "Message to unpin not found" or "Chat_admin_required"
        if "message to unpin not found" not in str(e_unpin).lower(): # Игнорируем, если уже откреплено
             logger.warning(f"Не удалось открепить сообщение о наборе {game_id}: {e_unpin}.")
    except Exception as e_unpin_unknown:
        logger.error(f"Неизвестная ошибка при откреплении сообщения о наборе {game_id}: {e_unpin_unknown}")

    # 1. Убрать кнопки набора у сообщения о наборе
    try:
        await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=game_id, reply_markup=None)
    except Exception as e_edit_markup:
        logger.warning(f"Не удалось убрать кнопки у сообщения о наборе {game_id}: {e_edit_markup}")

    # 2. Отправить сообщение о начале генерации вопросов
    generating_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏳ Попиздяка полез в свои самые темные архивы (и немного в интернет) за <b>{TOS_BATTLE_NUM_QUESTIONS} каверзными вопросами</b> для вашего интеллектуального побоища. Ожидайте, это может занять некоторое время...",
        parse_mode='HTML',
        reply_to_message_id=game_id
    )

    # --->>> 3. ГЕНЕРАЦИЯ {TOS_BATTLE_NUM_QUESTIONS} ВОПРОСОВ <<<---
    generated_questions_list = []
    # Определяем, сколько должно быть правдивых и сколько высеров
    # Можно сделать 50/50 или немного случайно. Для простоты пока 50/50.
    num_truth = TOS_BATTLE_NUM_QUESTIONS // 2
    num_shit = TOS_BATTLE_NUM_QUESTIONS - num_truth
    question_types_to_generate = ([True] * num_truth) + ([False] * num_shit)
    random.shuffle(question_types_to_generate) # Перемешиваем типы вопросов

    for i, should_be_truth in enumerate(question_types_to_generate):
        logger.info(f"Генерирую вопрос {i+1}/{TOS_BATTLE_NUM_QUESTIONS} для баттла {game_id} (Тип: {'Правда' if should_be_truth else 'Высер'})")
        if should_be_truth:
            statement_prompt = (
                "Ты - Попиздяка, кладезь странных, но реальных фактов. Придумай ОДИН МАЛОИЗВЕСТНЫЙ, но РЕАЛЬНЫЙ и ПРОВЕРЯЕМЫЙ факт. "
                "Он должен быть сформулирован как утверждение, коротко (1-2 предложения) и без указания, что это правда. "
                "Не используй фразы типа 'Попиздяка утверждает'. Просто сам факт."
                "\nПример: Медуза Turritopsis Dohrnii потенциально бессмертна."
                "\nВАЖНО: Не повторяй факты, которые ты уже мог генерировать." # Попытка уменьшить повторы
            )
        else: # Должен быть высер
            statement_prompt = (
                "Ты - Попиздяка, генератор абсурдного бреда. Придумай ОДИН АБСОЛЮТНО ЛЖИВЫЙ, но НАУКООБРАЗНЫЙ и ПРАВДОПОДОБНО ЗВУЧАЩИЙ высер. "
                "Он должен быть сформулирован как утверждение, коротко (1-2 предложения) и без указания, что это ложь. "
                "Не используй фразы типа 'Попиздяка утверждает'. Просто сам высер."
                "\nПример: Если чихнуть с открытыми глазами, они вылетят из орбит со скоростью пробки от шампанского."
                "\nВАЖНО: Не повторяй высеры, которые ты уже мог генерировать."
            )
        
        # Небольшая задержка между запросами к API, чтобы не перегружать
        if i > 0: await asyncio.sleep(random.uniform(1.0, 2.5)) 

        generated_statement_text = await _call_ionet_api(
            messages=[{"role": "user", "content": statement_prompt}],
            model_id=IONET_TEXT_MODEL_ID, max_tokens=100, temperature=0.9 # Повысим температуру для разнообразия
        )

        if not generated_statement_text or generated_statement_text.startswith("[") or len(generated_statement_text.strip()) < 10:
            logger.warning(f"Не удалось сгенерировать вопрос {i+1} для баттла {game_id}. Использую заглушку.")
            generated_statement_text = f"Заглушка-утверждение №{i+1}, потому что ИИ обосрался (это {'правда' if should_be_truth else 'высер'})"
        
        final_statement_for_question = "🗿 Попиздяка утверждает: " + generated_statement_text.strip()
        generated_questions_list.append({
            "statement": final_statement_for_question, 
            "is_truth": should_be_truth,
            "revealed_to_users": False, # Пока не раскрыт
            "user_answers_to_this_q": {} # {user_id: {"name": "...", "answer_bool": True/False, "answered_at": datetime}}
        })
    
    logger.info(f"Сгенерировано {len(generated_questions_list)} вопросов для баттла {game_id}.")
    if generating_msg:
        try: await context.bot.delete_message(chat_id=chat_id, message_id=generating_msg.message_id)
        except Exception: pass

    # 4. Обновить статус игры на "playing" и сохранить вопросы в БД
    update_fields = {
        "status": "playing",
        "current_question_index": 0, # Начинаем с 0-го вопроса
        "questions": generated_questions_list,
        "started_at": datetime.datetime.now(datetime.timezone.utc) # Время фактического начала игры
    }
    await loop.run_in_executor(
        None, lambda: tos_battles_collection.update_one(
            {"_id": battle_doc_id}, {"$set": update_fields}
        )
    )
    
    # 5. Отправить сообщение о начале игры
    participants_data_for_mention = battle.get("participants", {})
    participant_mentions = []
    if participants_data_for_mention:
        for p_id_str, p_info in participants_data_for_mention.items():
            try:
                p_id_int = int(p_id_str)
                # Попробуем получить актуальный объект User для mention_html
                # Это может быть медленно для большого числа участников
                # member = await context.bot.get_chat_member(chat_id, p_id_int)
                # participant_mentions.append(member.user.mention_html())
                # Упрощенный вариант, если есть имя:
                p_name = p_info.get("name", f"Анон-{p_id_int}")
                # Создаем "фейковый" User объект для mention_html
                # Если у вас есть username в p_info, можно его использовать
                temp_user_for_mention = User(id=p_id_int, first_name=p_name, is_bot=False)
                participant_mentions.append(temp_user_for_mention.mention_html())

            except ValueError: # Если ID не int
                participant_mentions.append(p_info.get("name", "ОшибкаИмени"))
            except Exception as e_mention:
                logger.warning(f"Не удалось создать mention для участника {p_id_str}: {e_mention}")
                participant_mentions.append(p_info.get("name", f"Анон-{p_id_str} (без @)"))
    
    start_game_message_text = (
        f"🔥 <b>БАТТЛ 'ПРАВДА ИЛИ ВЫСЕР' НАЧИНАЕТСЯ!</b> 🔥\n\n"
        f"Участники этой интеллектуальной бойни: {', '.join(participant_mentions) if participant_mentions else 'Никто не записался, лол. Ну и хуй с вами, играю сам с собой.'}\n\n"
        f"Всего будет {TOS_BATTLE_NUM_QUESTIONS} раундов. Готовьте свои мозги (или что там у вас вместо них)!\n"
        f"Сейчас будет первый вопрос..."
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=start_game_message_text,
        parse_mode='HTML',
        reply_to_message_id=game_id # Отвечаем на сообщение о наборе
    )

    # 6. Запустить логику первого вопроса
    # Обновим battle данными из БД, чтобы иметь актуальный список вопросов
    battle_updated = await loop.run_in_executor(None, lambda: tos_battles_collection.find_one({"_id": battle_doc_id}))
    if battle_updated:
        await _ask_next_tos_battle_question(context, battle_updated) # Передаем весь документ баттла
    else:
        logger.error(f"Не удалось получить обновленные данные баттла {battle_doc_id} перед первым вопросом.")
        await context.bot.send_message(chat_id=chat_id, text="🗿 Пиздец, я потерял данные об игре, пока готовил вопросы. Расходимся.")


async def auto_end_recruitment_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if not job or not job.chat_id or not job.data or 'game_id' not in job.data:
        logger.error(f"Ошибка в job 'auto_end_recruitment_job': нет необходимых данных. Job: {job}")
        return
        
    chat_id = job.chat_id
    game_id = job.data['game_id'] # Это message_id сообщения о наборе
    # host_id = job.data.get('host_id') # Можно использовать для логов, если нужно
    loop = asyncio.get_running_loop()

    logger.info(f"Сработал Job: автоматическое окончание набора для баттла game_id: {game_id} в чате {chat_id}.")

    # Ищем игру, которая все еще в статусе набора и время набора действительно истекло
    # Используем find_one_and_update для атомарности, если возможно, или find_one + update_one
    # Важно: find_one_and_update вернет документ ДО обновления, если не указать return_document
    # Поэтому сначала найдем, потом проверим время, потом обновим.
    
    battle_to_process = await loop.run_in_executor(
        None, lambda: tos_battles_collection.find_one(
            {"chat_id": chat_id, "game_id": game_id, "status": "recruiting"}
        )
    )

    if not battle_to_process:
        logger.info(f"Job (auto_end_recruitment): Баттл {game_id} в чате {chat_id} не найден в статусе 'recruiting'. Возможно, уже начат хостом или отменен.")
        return

    now_utc_job_end = datetime.datetime.now(datetime.timezone.utc)
    recruitment_ends_at_db = battle_to_process["recruitment_ends_at"]
    if recruitment_ends_at_db.tzinfo is None: # Убедимся, что есть таймзона
        recruitment_ends_at_db = recruitment_ends_at_db.replace(tzinfo=datetime.timezone.utc)

    if now_utc_job_end < recruitment_ends_at_db:
        logger.info(f"Job (auto_end_recruitment): Время набора для баттла {game_id} еще не истекло (возможно, было продлено). Текущее: {now_utc_job_end}, Окончание: {recruitment_ends_at_db}. Job отработает позже.")
        # Job будет вызван снова по правильному (продленному) времени, если он был перепланирован.
        # Если не был, то этот job просто завершится, а новый (если был создан при продлении) сработает.
        return

    # Время действительно истекло, обрабатываем
    battle_doc_id_job = battle_to_process["_id"]
    current_participants_count_job = len(battle_to_process.get("participants", {}))

    if current_participants_count_job < TOS_BATTLE_MIN_PARTICIPANTS:
        logger.info(f"Job (auto_end_recruitment): Недостаточно участников ({current_participants_count_job}/{TOS_BATTLE_MIN_PARTICIPANTS}) для старта баттла {game_id}. Отменяем.")
        
        # Атомарно меняем статус на "cancelled_not_enough_players"
        update_cancel_job_result = await loop.run_in_executor(
            None, lambda: tos_battles_collection.update_one(
                {"_id": battle_doc_id_job, "status": "recruiting"}, # Доп. проверка, что статус не изменился
                {"$set": {"status": "cancelled_not_enough_players", "finished_at": now_utc_job_end}}
            )
        )

        if update_cancel_job_result.modified_count == 0:
            logger.warning(f"Job (auto_end_recruitment): Не удалось обновить статус на 'cancelled_not_enough_players' для баттла {game_id}. Возможно, статус изменился.")
            return # Выходим, чтобы не дублировать действия

        # Открепляем сообщение о наборе
        try:
            await context.bot.unpin_chat_message(chat_id=chat_id, message_id=battle_to_process["message_id_recruitment"])
            logger.info(f"Job (auto_end_recruitment): Сообщение о наборе {game_id} откреплено (недостаточно игроков).")
        except Exception: pass 
        
        # Убираем кнопки у сообщения о наборе
        try:
            await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=battle_to_process["message_id_recruitment"], reply_markup=None)
            await context.bot.send_message(
                chat_id, 
                f"🚫 Набор на Баттл 'Правда или Высер' (ID: {game_id}) завершен! К сожалению, набралось меньше {TOS_BATTLE_MIN_PARTICIPANTS} долбоебов для эпичной зарубы. Игра отменяется.\n"
                f"🗿 Попробуйте в другой раз, когда соберется толпа побольше или хост будет менее ленивой жопой.",
                parse_mode='HTML',
                reply_to_message_id=battle_to_process["message_id_recruitment"]
            )
        except Exception as e_cancel_job:
             logger.error(f"Job (auto_end_recruitment): Ошибка при уведомлении об отмене баттла {game_id}: {e_cancel_job}")
        
        # Обновляем кулдаун, так как игра считается "завершенной" отменой
        await loop.run_in_executor(
            None, lambda: chat_activity_collection.update_one(
                {"chat_id": chat_id},
                {"$set": {"last_tos_battle_end_time": now_utc_job_end}},
                upsert=True
            )
        )
        return # Завершаем работу job'а

    # Если участников достаточно, начинаем игру
    logger.info(f"Job (auto_end_recruitment): Время набора для баттла {game_id} истекло. Участников достаточно ({current_participants_count_job}). Начинаем игру.")
    # Вызываем основную функцию начала самой игры, передавая _id документа
    await _actually_start_the_battle_game(context, battle_doc_id_job)

async def _ask_next_tos_battle_question(context: ContextTypes.DEFAULT_TYPE, battle_data: dict) -> None:
    """Отправляет следующий вопрос баттла и запускает таймер на ответ."""
    loop = asyncio.get_running_loop()
    chat_id = battle_data["chat_id"]
    game_id = battle_data["game_id"] # Это message_id_recruitment
    battle_doc_id = battle_data["_id"]
    current_question_index = battle_data.get("current_question_index", -1)

    if current_question_index < 0 or current_question_index >= len(battle_data.get("questions", [])):
        logger.error(f"Некорректный current_question_index ({current_question_index}) для баттла {game_id}.")
        # Здесь должна быть логика завершения игры, если вопросы кончились
        await _end_tos_battle(context, battle_data) # Предполагаем, что такая функция будет
        return

    question_data = battle_data["questions"][current_question_index]
    statement_to_ask = question_data["statement"]

    logger.info(f"Задаем вопрос {current_question_index + 1}/{TOS_BATTLE_NUM_QUESTIONS} для баттла {game_id}: '{statement_to_ask[:50]}...'")

    question_msg_text = (
        f"<b>Раунд {current_question_index + 1} из {TOS_BATTLE_NUM_QUESTIONS}!</b>\n\n"
        f"{statement_to_ask}\n\n"
        f"У вас {TOS_BATTLE_QUESTION_ANSWER_TIME_SECONDS} секунд на размышление, ублюдки!"
    )
    
    # Кнопки ВСЕГДА СОЗДАЮТСЯ БЕЗ СЧЕТЧИКОВ при отправке нового вопроса
    keyboard_question_initial = [
        [
            InlineKeyboardButton("👍 Это Правда!", callback_data=f"tosbattle_ans_{game_id}_{current_question_index}_true"),
            InlineKeyboardButton("👎 Это Высер!", callback_data=f"tosbattle_ans_{game_id}_{current_question_index}_false")
        ]
    ]
    reply_markup_question_initial = InlineKeyboardMarkup(keyboard_question_initial)

    try:
        sent_question_msg = await context.bot.send_message(
            chat_id,
            text=question_msg_text,
            parse_mode='HTML',
            reply_markup=reply_markup_question_initial # <<<--- ИСПОЛЬЗУЕМ КНОПКИ БЕЗ СЧЕТЧИКОВ
        )
        # Сохраняем ID сообщения с текущим вопросом в БД
        await loop.run_in_executor(
            None, lambda: tos_battles_collection.update_one(
                {"_id": battle_doc_id},
                {"$set": {"message_id_current_question": sent_question_msg.message_id}}
            )
        )

        # Планируем автоматическое раскрытие ответа на этот вопрос
        job_name_q_reveal = f"tosbattle_q_reveal_{chat_id}_{game_id}_{current_question_index}"
        # Удаляем старый job с таким же именем, если он вдруг остался
        current_jobs_q = context.job_queue.get_jobs_by_name(job_name_q_reveal)
        for old_job_q in current_jobs_q:
            old_job_q.schedule_removal()
        
        context.job_queue.run_once(
            auto_reveal_battle_question_job, # Новая job-функция
            TOS_BATTLE_QUESTION_ANSWER_TIME_SECONDS,
            chat_id=chat_id,
            data={'battle_doc_id_str': str(battle_doc_id), 'question_index': current_question_index}, # Передаем ObjectId как строку
            name=job_name_q_reveal
        )
        logger.info(f"Запланировано авто-раскрытие для вопроса {current_question_index} баттла {game_id} через {TOS_BATTLE_QUESTION_ANSWER_TIME_SECONDS} сек.")

    except Exception as e_ask:
        logger.error(f"Ошибка при отправке вопроса {current_question_index} для баттла {game_id}: {e_ask}")
        # Попытаться завершить игру корректно, если не можем задать вопрос
        await context.bot.send_message(chat_id, "🗿 Пиздец, я сломался и не могу задать следующий вопрос. Похоже, баттл придется прервать.")
        await _end_tos_battle(context, battle_data, error_occurred=True)

async def auto_reveal_battle_question_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if not job or not job.chat_id or not job.data or 'battle_doc_id_str' not in job.data or 'question_index' not in job.data:
        logger.error(f"Ошибка в job 'auto_reveal_battle_question_job': нет необходимых данных. Job: {job}")
        return
        
    chat_id = job.chat_id
    try:
        battle_doc_id = ObjectId(job.data['battle_doc_id_str']) # Преобразуем строку обратно в ObjectId
    except Exception as e_oid:
        logger.error(f"Ошибка преобразования battle_doc_id_str в ObjectId в job'е: {e_oid}")
        return
        
    question_index_from_job = job.data['question_index']
    
    logger.info(f"Сработал авто-ревил для вопроса {question_index_from_job} баттла (doc_id: {battle_doc_id}) в чате {chat_id}.")
    
    # Вызываем новую функцию, которая будет обрабатывать раскрытие ответа на вопрос баттла
    await _process_battle_question_reveal(context, battle_doc_id, question_index_from_job, auto_triggered=True)

async def _process_battle_question_reveal(context: ContextTypes.DEFAULT_TYPE, battle_doc_id: ObjectId, question_index: int, auto_triggered: bool = False):
    loop = asyncio.get_running_loop()
    # Получаем САМУЮ АКТУАЛЬНУЮ версию баттла из БД
    battle = await loop.run_in_executor(None, lambda: tos_battles_collection.find_one({"_id": battle_doc_id}))

    if not battle or battle.get("status") != "playing":
        logger.info(f"_process_battle_question_reveal: Баттл {battle_doc_id} не найден или не в статусе 'playing'. Текущий статус: {battle.get('status')}")
        # Если статус уже 'finished', возможно, игра завершилась другим путем (например, ошибкой)
        if battle and battle.get("status") == "finished":
             # Убираем кнопки у сообщения с вопросом, если оно еще есть и имеет их
            if battle.get("message_id_current_question"):
                try:
                    await context.bot.edit_message_reply_markup(battle["chat_id"], message_id=battle["message_id_current_question"], reply_markup=None)
                except Exception: pass
        return

    questions_list = battle.get("questions", [])
    if question_index >= len(questions_list):
        logger.error(f"Неверный question_index {question_index} для баттла {battle_doc_id} при раскрытии.")
        await _end_tos_battle(context, battle, error_occurred=True, error_message="Ошибка индекса вопроса") # Завершаем с ошибкой
        return

    # Проверяем, не был ли этот вопрос уже раскрыт
    if questions_list[question_index].get("revealed_to_users"):
        logger.info(f"Вопрос {question_index} баттла {battle_doc_id} уже был раскрыт (проверка в _process_battle_question_reveal).")
        return # Ничего не делаем, если уже раскрыт

    chat_id = battle["chat_id"]
    game_id = battle["game_id"] # message_id_recruitment
    
    logger.info(f"Раскрытие ответа на вопрос {question_index + 1} для баттла {game_id} в чате {chat_id}. Auto-triggered: {auto_triggered}")
    
    statement_data = questions_list[question_index]
    correct_answer_is_truth = statement_data["is_truth"]
    statement_text = statement_data["statement"]
    user_answers_for_this_q = statement_data.get("user_answers_to_this_q", {})

    # 1. Пометить вопрос как раскрытый в БД
    await loop.run_in_executor(
        None, lambda: tos_battles_collection.update_one(
            {"_id": battle_doc_id},
            {"$set": {f"questions.{question_index}.revealed_to_users": True}}
        )
    )
    
    # 2. Убрать кнопки у сообщения с вопросом (если оно было)
    message_id_of_this_question = battle.get("message_id_current_question")
    if message_id_of_this_question:
        try:
            await context.bot.edit_message_text( # Редактируем текст, чтобы показать, что время вышло
                chat_id=chat_id,
                message_id=message_id_of_this_question,
                text=f"<b>Раунд {question_index + 1} - ВРЕМЯ ВЫШЛО!</b>\n\n{statement_text}\n\n<i>Сейчас Попиздяка объявит вердикт...</i>",
                parse_mode='HTML',
                reply_markup=None # Убираем кнопки
            )
        except Exception as e_edit_q:
            logger.warning(f"Не удалось отредактировать/убрать кнопки у вопроса {question_index} баттла {game_id}: {e_edit_q}")

    # 3. Подсчет очков за этот раунд и обновление общего счета участников
    updated_participants_data = battle.get("participants", {})
    round_results_log = [] # Для логов и, возможно, для промпта ИИ

    for user_id_str, participant_info in updated_participants_data.items():
        user_id_int = int(user_id_str) # Ключи в MongoDB словарях часто строки
        user_answer_record = user_answers_for_this_q.get(str(user_id_int)) # И здесь тоже ищем по строке

        if user_answer_record:
            user_answered_correctly = (user_answer_record["answer_bool"] == correct_answer_is_truth)
            if user_answered_correctly:
                participant_info["score"] = participant_info.get("score", 0) + 1
                round_results_log.append(f"{participant_info.get('name', 'Анон')} угадал(а)")
            else:
                round_results_log.append(f"{participant_info.get('name', 'Анон')} обосрался(лась)")
            # Записываем сам факт ответа (правильно/неправильно) в массив ответов участника
            if "answers" not in participant_info or not isinstance(participant_info["answers"], list) or len(participant_info["answers"]) != TOS_BATTLE_NUM_QUESTIONS:
                participant_info["answers"] = [None] * TOS_BATTLE_NUM_QUESTIONS # Инициализируем, если нужно
            participant_info["answers"][question_index] = user_answered_correctly # True если угадал, False если нет
        else:
            round_results_log.append(f"{participant_info.get('name', 'Анон')} проебал(а) момент и не ответил(а)")
            # Также записываем None или специальное значение для неответивших
            if "answers" not in participant_info or not isinstance(participant_info["answers"], list) or len(participant_info["answers"]) != TOS_BATTLE_NUM_QUESTIONS:
                participant_info["answers"] = [None] * TOS_BATTLE_NUM_QUESTIONS
            participant_info["answers"][question_index] = "no_answer" # Или None

    # Обновляем данные участников (счета и массив ответов) в БД
    if updated_participants_data: # Если есть участники
        await loop.run_in_executor(
            None, lambda: tos_battles_collection.update_one(
                {"_id": battle_doc_id},
                {"$set": {"participants": updated_participants_data}}
            )
        )
    
    # 4. Объявить правильный ответ и комментарий Попиздяки
    result_text_q_human = "✅ ЭТО БЫЛА ПРАВДА!" if correct_answer_is_truth else "❌ КОНЕЧНО ЖЕ, ЭТО ВЫСЕР ЕБАНЫЙ!"
    
    # Формируем информацию для промпта ИИ
    num_participants_in_game = len(updated_participants_data) # Общее число тех, кто ЗАПИСАН в игру
    answered_user_ids_this_round = set(user_answers_for_this_q.keys()) # ID тех, кто ответил в этом раунде
    num_answered_in_round = len(answered_user_ids_this_round)
    num_correct_in_round = sum(1 for uid_str, ans_rec in user_answers_for_this_q.items() if ans_rec["answer_bool"] == correct_answer_is_truth)
    num_wrong_in_round = num_answered_in_round - num_correct_in_round
    
    num_not_answered_this_round = 0
    if num_participants_in_game > 0:
        for p_id_str_active in updated_participants_data.keys():
            if p_id_str_active not in answered_user_ids_this_round:
                num_not_answered_this_round += 1

    round_summary_for_ai = ""
    if num_participants_in_game == 0:
        round_summary_for_ai = "В баттле нет участников. Я что, сам с собой играю, как шизофреник?"
    elif num_answered_in_round == 0: # Никто из записавшихся не ответил
        round_summary_for_ai = f"Ни одна из {num_participants_in_game} записавшихся душ не удосужилась ответить в этом раунде. Похоже, все слишком тупы или заняты дрочкой."
    elif num_answered_in_round > 0:
        if num_correct_in_round == num_answered_in_round: 
            summary_verb = "угадал" if num_correct_in_round == 1 else "угадали"
            round_summary_for_ai = f"Невероятно, но факт! Все {num_correct_in_round} ответивших {summary_verb}! Либо вы все тут Ванги недоделанные, либо вопрос был для детского сада."
            if num_not_answered_this_round > 0:
                round_summary_for_ai += f" А вот {num_not_answered_this_round} ссыкунов так и не рискнули своей репутацией (которой и так нет)."
        elif num_wrong_in_round == num_answered_in_round: 
             summary_verb_wrong = "обосрался" if num_wrong_in_round == 1 else "обосрались"
             round_summary_for_ai = f"Это фиаско, братаны! Все {num_wrong_in_round} ответивших синхронно {summary_verb_wrong}! Поздравляю, вы достигли дна коллективной тупости!"
             if num_not_answered_this_round > 0:
                round_summary_for_ai += f" {num_not_answered_this_round} проебали момент и правильно сделали, а то бы тоже вляпались в это дерьмо."
        else: # Есть и те, и другие
            round_summary_for_ai = f"Из тех, кто не зассал: {num_correct_in_round} оказались правы (или им повезло), а {num_wrong_in_round} жидко пёрнули в лужу."
            if num_not_answered_this_round > 0:
                round_summary_for_ai += f" И еще {num_not_answered_this_round} тормозов просто промолчали, видимо, обдумывая смысл бытия."


    round_comment_prompt = (
        f"Ты - Попиздяка, ведущий интеллектуальной битвы 'Правда или Высер'. Только что закончился раунд.\n"
        f"Утверждение было: «{statement_text}»\n"
        f"Правильный ответ: {result_text_q_human}\n"
        f"Краткая сводка по ответам: {round_summary_for_ai}\n\n"
        f"Напиши короткий (2-3 предложения), саркастичный и матерный комментарий к итогам ЭТОГО РАУНДА. "
        f"Учитывай, все ли угадали, или были ошибки, или кто-то не ответил. "
        f"Начинай с `🗿 По итогам раунда:`"
    )
    ai_round_comment = await _call_ionet_api(
        messages=[{"role": "user", "content": round_comment_prompt}],
        model_id=IONET_TEXT_MODEL_ID, max_tokens=180, temperature=0.8
    ) or "🗿 Ну что, кто-то угадал, кто-то обосрался. Обычное дело в этом цирке."
    if not ai_round_comment.startswith("🗿"): ai_round_comment = "🗿 " + ai_round_comment

    round_reveal_message = (
        f"<b>Итоги Раунда {question_index + 1}!</b>\n\n"
        f"Утверждение было: «<i>{statement_text}</i>»\n"
        f"Правильный вердикт Попиздяки: <b>{result_text_q_human}</b>\n\n"
        f"{ai_round_comment}"
    )
    await context.bot.send_message(chat_id, text=round_reveal_message, parse_mode='HTML')
    await asyncio.sleep(1.0) # Пауза перед следующим вопросом или итогами

    # 5. Перейти к следующему вопросу или завершить игру
    next_question_index = question_index + 1
    if next_question_index < TOS_BATTLE_NUM_QUESTIONS:
        await loop.run_in_executor(
            None, lambda: tos_battles_collection.update_one(
                {"_id": battle_doc_id},
                {"$set": {"current_question_index": next_question_index}}
            )
        )
        # Получаем обновленные данные баттла (с обновленными очками и новым current_question_index)
        battle_for_next_q = await loop.run_in_executor(None, lambda: tos_battles_collection.find_one({"_id": battle_doc_id}))
        if battle_for_next_q:
            await _ask_next_tos_battle_question(context, battle_for_next_q)
        else:
            logger.error(f"Не удалось получить обновленный баттл {battle_doc_id} для вопроса {next_question_index}.")
            await context.bot.send_message(chat_id, "🗿 Пиздец, я потерял нить игры после этого раунда. Придется закончить.")
            # Передаем battle, который у нас есть, но он может быть не до конца обновлен
            await _end_tos_battle(context, battle, error_occurred=True, error_message="Потеря данных баттла при переходе к след. вопросу")
    else:
        logger.info(f"Все {TOS_BATTLE_NUM_QUESTIONS} вопросов баттла {game_id} заданы и раскрыты. Завершаем игру.")
        # Передаем battle (который содержит обновленные очки после последнего раунда)
        await _end_tos_battle(context, battle)

async def _end_tos_battle(context: ContextTypes.DEFAULT_TYPE, battle_data: dict, 
                          error_occurred: bool = False, error_message: str = "") -> None:
    loop = asyncio.get_running_loop()
    chat_id = battle_data["chat_id"]
    game_id = battle_data["game_id"] # message_id_recruitment
    battle_doc_id = battle_data["_id"]

     # Попытка открепить сообщение о наборе, если оно еще закреплено
    try:
        # Проверить, является ли это сообщение текущим закрепленным, может быть сложно без доп. вызовов
        # Поэтому просто пытаемся открепить по ID. Если оно не закреплено, будет ошибка, которую мы ловим.
        await context.bot.unpin_chat_message(chat_id=chat_id, message_id=game_id_recruitment_msg)
        logger.info(f"Сообщение о наборе {game_id_recruitment_msg} откреплено при завершении баттла.")
    except telegram.error.BadRequest as e_unpin_final:
        if "message to unpin not found" not in str(e_unpin_final).lower() and \
           "message is not pinned" not in str(e_unpin_final).lower(): # Игнорируем, если уже откреплено или не было закреплено
            logger.warning(f"Не удалось открепить сообщение о наборе {game_id_recruitment_msg} при завершении: {e_unpin_final}")
    except Exception: pass # Игнорируем другие ошибки открепления здесь

    logger.info(f"Завершение баттла {game_id} в чате {chat_id}. Ошибка во время игры: {error_occurred} ('{error_message}')")

    now_for_final_finish_end = datetime.datetime.now(datetime.timezone.utc)
    await loop.run_in_executor(
        None, lambda: tos_battles_collection.update_one(
            {"_id": battle_doc_id},
            {"$set": {"status": "finished", "finished_at": now_for_final_finish_end, "prizes_awarded_info": {}}}, # Добавим поле для информации о выданных призах
            upsert=False 
        )
    )
    
    await loop.run_in_executor(
        None, lambda: chat_activity_collection.update_one(
            {"chat_id": chat_id},
            {"$set": {"last_tos_battle_end_time": now_for_final_finish_end}},
            upsert=True
        )
    )
    logger.info(f"Баттл {game_id} завершен (статус обновлен). Кулдаун для чата обновлен.")

    if error_occurred:
        message_text_final_err = (f"🏁 <b>Баттл 'Правда или Высер' (ID: {game_id}) ПРЕРВАН из-за технической шоколадки у Попиздяки!</b> 🏁\n\n"
                                  f"Причина: {error_message or 'Неизвестный пиздец'}\n\n"
                                  f"🗿 Извиняйте, долбоебы, но сегодня без победителей и призов. Можете пойти нахуй.")
        await context.bot.send_message(chat_id, text=message_text_final_err, parse_mode='HTML', reply_to_message_id=game_id)
        return

    participants_final = battle_data.get("participants", {})
    if not participants_final:
        await context.bot.send_message(chat_id, "🏁 Баттл завершен, но никто не участвовал. Какие же вы скучные.", reply_to_message_id=game_id)
        return

    sorted_participants = sorted(participants_final.items(), key=lambda item: item[1].get("score", 0), reverse=True)

    results_table_lines = ["<b>🏆 Итоговая таблица лидеров (или долбоебов):</b>"]
    winners = []
    max_score = 0
    if sorted_participants:
        max_score = sorted_participants[0][1].get("score", 0)

    if max_score <= 0 : 
        results_table_lines.append("\nНикто не набрал положительных очков. Позорище!")
    else:
        for i, (user_id_str, p_data) in enumerate(sorted_participants):
            name = p_data.get("name", f"Анон-{user_id_str}")
            score = p_data.get("score", 0)
            medal = ""
            if score == max_score : medal = "🥇 " 
            elif i == 1 and score > 0: medal = "🥈 " # Добавил score > 0 для медалей
            elif i == 2 and score > 0: medal = "🥉 "
            else: medal = f"{i+1}. " if score > 0 else f"{i+1}. (дно) " # Уточнение для тех, кто с нулем или меньше
            results_table_lines.append(f"{medal}{name}: <b>{score}</b> очк.")
            if score == max_score:
                winners.append({"id": int(user_id_str), "name": name, "score": score})
    
    # "Главный обосрамс" (логика как была)
    worst_score = float('inf')
    most_wrong_answers = -1
    biggest_losers_by_score = []
    biggest_losers_by_wrong_answers = []
    has_actual_answers = False 

    for user_id_str_loser, p_data_loser in participants_final.items():
        score_loser = p_data_loser.get("score", 0)
        answers_array_loser = p_data_loser.get("answers", [None] * TOS_BATTLE_NUM_QUESTIONS)
        wrong_answers_count_loser = sum(1 for ans_l in answers_array_loser if ans_l is False) 
        if any(ans_l is not None and ans_l != "no_answer" for ans_l in answers_array_loser):
            has_actual_answers = True

        if score_loser < worst_score:
            worst_score = score_loser
            biggest_losers_by_score = [{"name": p_data_loser.get("name", f"Анон-{user_id_str_loser}"), "score": score_loser}]
        elif score_loser == worst_score:
            biggest_losers_by_score.append({"name": p_data_loser.get("name", f"Анон-{user_id_str_loser}"), "score": score_loser})

        if wrong_answers_count_loser > most_wrong_answers:
            most_wrong_answers = wrong_answers_count_loser
            biggest_losers_by_wrong_answers = [{"name": p_data_loser.get("name", f"Анон-{user_id_str_loser}"), "wrong_count": wrong_answers_count_loser}]
        elif wrong_answers_count_loser == most_wrong_answers and most_wrong_answers >= 0 :
            biggest_losers_by_wrong_answers.append({"name": p_data_loser.get("name", f"Анон-{user_id_str_loser}"), "wrong_count": wrong_answers_count_loser})
            
    loser_nomination_text = ""
    loser_names_wrong_final = "" # Инициализируем
    loser_names_score_final = "" # Инициализируем

    if has_actual_answers:
        if most_wrong_answers > 0 and biggest_losers_by_wrong_answers:
            loser_names_wrong_final = ", ".join([l["name"] for l in biggest_losers_by_wrong_answers])
            loser_nomination_text = f"\n\n💩 <b>Главный Обосрамс Баттла</b> (больше всех ошибок - {most_wrong_answers}): <b>{loser_names_wrong_final}</b>! Ваши бурные овации (нет)!"
        elif biggest_losers_by_score and worst_score < max_score and max_score > 0 : # Показывать только если есть победитель и кто-то отстал
            loser_names_score_final = ", ".join([l["name"] for l in biggest_losers_by_score])
            loser_nomination_text = f"\n\n📉 А титул 'Почти Смог, но Все Равно Хуйло' ({worst_score} очк.) достается: <b>{loser_names_score_final}</b>!"

    results_message = "\n".join(results_table_lines) + loser_nomination_text

    final_comment_prompt = (
        f"Ты - Попиздяка, ведущий интеллектуальной битвы 'Правда или Высер'. Игра окончена.\n"
        f"Победитель(и) (если есть): {', '.join([w['name'] for w in winners]) if winners else 'Победителей нет (все долбоебы)'}\n"
        f"Максимальный счет: {max_score if winners else '0 (позорище)'}\n"
        f"Главный обосрамс (если есть): {loser_names_wrong_final if loser_names_wrong_final else (loser_names_score_final if loser_names_score_final else 'Все были одинаково тупы или гениальны, хуй разберешь')}\n\n"
        f"Напиши зажигательный, саркастичный и матерный комментарий по итогам всего Баттла. "
        f"Твой комментарий должен быть **ОЧЕНЬ КОРОТКИМ И ЕМКИМ (СТРОГО 1-2 предложения, примерно 150-250 символов)**, чтобы он точно влез в итоговое сообщение. " # <<<--- ИЗМЕНЕНО
        f"Поздравь победителей так, чтобы они почувствовали себя королями говна. Разъеби проигравших. "
        f"Начинай с `🗿 Ну что, конченные, вот и итоги вашего интеллектуального высера:`"
    )
    ai_final_comment = await _call_ionet_api(
        messages=[{"role": "user", "content": final_comment_prompt}],
        model_id=IONET_TEXT_MODEL_ID, 
        max_tokens=80, # <<<--- УМЕНЬШЕНО (150-250 символов это примерно 40-70 токенов)
        temperature=0.85
    ) or "🗿 Игра окончена. Кто выиграл - молодец. Кто проиграл - соси хуй. Все просто."
    if not ai_final_comment.startswith("🗿"): ai_final_comment = "🗿 " + ai_final_comment

    full_final_message_text = f"🏁 <b>Баттл 'Правда или Высер' (ID: {game_id}) ОКОНЧЕН!</b> 🏁\n\n{results_message}\n\n{ai_final_comment}"
    
    # Сначала формируем часть с результатами
    results_part_text = f"🏁 <b>Баттл 'Правда или Высер' (ID: {game_id}) ОКОНЧЕН!</b> 🏁\n\n{results_message}"
    # Комментарий ИИ
    ai_comment_part_text = ai_final_comment if ai_final_comment.strip() else ""

    message_parts_final_to_send = []

    # Пробуем отправить все вместе, если не слишком длинно
    if len(results_part_text + "\n\n" + ai_comment_part_text) <= MAX_TELEGRAM_MESSAGE_LENGTH:
        message_parts_final_to_send.append(results_part_text + ("\n\n" + ai_comment_part_text if ai_comment_part_text else ""))
    else:
        # Если слишком длинно, отправляем по частям
        if results_part_text.strip():
            # Если сама таблица результатов слишком длинная, ее тоже надо бить
            if len(results_part_text) > MAX_TELEGRAM_MESSAGE_LENGTH:
                logger.warning(f"Таблица результатов для баттла {game_id} слишком длинная ({len(results_part_text)}), будет обрезана или отправлена частями грубо.")
                # Примитивная разбивка для таблицы, если очень надо
                temp_results_parts = split_long_message_primitive(results_part_text, MAX_TELEGRAM_MESSAGE_LENGTH - 50) # MAX_TELEGRAM_MESSAGE_LENGTH определена глобально
                message_parts_final_to_send.extend(temp_results_parts)
            else:
                message_parts_final_to_send.append(results_part_text)
        
        if ai_comment_part_text.strip():
            # Если комментарий ИИ слишком длинный, его тоже надо бить
            if len(ai_comment_part_text) > MAX_TELEGRAM_MESSAGE_LENGTH:
                logger.warning(f"Комментарий ИИ для баттла {game_id} слишком длинный ({len(ai_comment_part_text)}), будет обрезан или отправлен частями грубо.")
                temp_ai_parts = split_long_message_primitive(ai_comment_part_text, MAX_TELEGRAM_MESSAGE_LENGTH - 50)
                message_parts_final_to_send.extend(temp_ai_parts)
            else:
                message_parts_final_to_send.append(ai_comment_part_text)

    for part_msg_final_send_val in message_parts_final_to_send:
        if part_msg_final_send_val.strip():
            await context.bot.send_message(chat_id, text=part_msg_final_send_val, parse_mode='HTML', reply_to_message_id=game_id)
            await asyncio.sleep(0.3)

    # --- НОВАЯ ЛОГИКА НАЧИСЛЕНИЯ ПРИЗА ---
    prizes_awarded_info_dict = {} # Для записи в БД информации о выданных призах

    if winners: # Если есть победители (max_score > 0)
        num_winners = len(winners)
        prize_notifications = [f"🏆 <b>Награждение победителей Баттла (ID: {game_id}):</b>"]

        if num_winners == 1:
            winner_obj_single = winners[0]
            winner_id_s = winner_obj_single["id"]
            winner_name_s = winner_obj_single["name"]
            
            user_profile_s = await get_user_profile_data(User(id=winner_id_s, first_name=winner_name_s, is_bot=False))
            winner_display_name_s = user_profile_s.get("display_name", winner_name_s)

            # Начисляем +5см к писюну
            penis_stat_s = await loop.run_in_executor(None, lambda: penis_stats_collection.find_one({"user_id": winner_id_s, "chat_id": chat_id}))
            current_penis_s = penis_stat_s.get("penis_size", 0) if penis_stat_s else 0
            new_penis_s = current_penis_s + 5 # TOS_BATTLE_PENIS_REWARD_SINGLE = 5
            await loop.run_in_executor(None, lambda: penis_stats_collection.update_one(
                {"user_id": winner_id_s, "chat_id": chat_id},
                {"$set": {"penis_size": new_penis_s, "user_display_name": winner_display_name_s}}, upsert=True
            ))
            prize_notifications.append(f"🍆 Писюн единственного чемпиона <b>{winner_display_name_s}</b> вырос на <b>5см</b> и теперь равен <b>{new_penis_s}см</b>!")
            # TODO: Проверка на новое писечное звание
            
            # Начисляем +0.3 к сиськам
            tits_stat_s = await loop.run_in_executor(None, lambda: tits_stats_collection.find_one({"user_id": winner_id_s, "chat_id": chat_id}))
            current_tits_s = float(tits_stat_s.get("tits_size", 0.0)) if tits_stat_s else 0.0
            new_tits_s = round(current_tits_s + 0.3, 1) # TOS_BATTLE_TITS_REWARD_SINGLE = 0.3
            await loop.run_in_executor(None, lambda: tits_stats_collection.update_one(
                {"user_id": winner_id_s, "chat_id": chat_id},
                {"$set": {"tits_size": new_tits_s, "user_display_name": winner_display_name_s}}, upsert=True
            ))
            prize_notifications.append(f"🍈 Сиськи <b>{winner_display_name_s}</b> подросли на <b>0.3</b> и стали <b>{new_tits_s:.1f}-го</b> размера!")
            # TODO: Проверка на новое сисечное звание

            prizes_awarded_info_dict[str(winner_id_s)] = {"penis_added": 5, "tits_added": 0.3}
            logger.info(f"Призы (писюн +5, сиськи +0.3) выданы единственному победителю {winner_display_name_s} ({winner_id_s}) за баттл {game_id}.")

        else: # Несколько победителей
            prize_notifications.append(f"\nУ нас <b>{num_winners} победителя(ей)</b>! Попиздяка решил не мелочиться и каждому подкинуть по чуть-чуть:")
            penis_reward_multi = 2  # Фиксировано +2 см
            tits_reward_multi = 0.1 # Фиксировано +0.1
            
            prize_notifications.append(f"- Каждый получает <b>+{penis_reward_multi}см</b> к писюну.")
            prize_notifications.append(f"- И <b>+{tits_reward_multi:.1f}</b> к размеру сисек!")
            logger.info(f"{num_winners} победителя(ей) в баттле {game_id}. Писюн +{penis_reward_multi}см, Сиськи +{tits_reward_multi:.1f} каждому.")

            for winner_obj_m in winners:
                winner_id_m_prize = winner_obj_m["id"]
                winner_name_m_prize = winner_obj_m["name"]
                user_profile_m_prize = await get_user_profile_data(User(id=winner_id_m_prize, first_name=winner_name_m_prize, is_bot=False))
                winner_display_name_m_prize = user_profile_m_prize.get("display_name", winner_name_m_prize)

                # Начисляем писюн
                penis_stat_m_prize = await loop.run_in_executor(None, lambda: penis_stats_collection.find_one({"user_id": winner_id_m_prize, "chat_id": chat_id}))
                current_penis_m_prize = penis_stat_m_prize.get("penis_size", 0) if penis_stat_m_prize else 0
                new_penis_m_prize = current_penis_m_prize + penis_reward_multi
                await loop.run_in_executor(None, lambda: penis_stats_collection.update_one(
                    {"user_id": winner_id_m_prize, "chat_id": chat_id},
                    {"$set": {"penis_size": new_penis_m_prize, "user_display_name": winner_display_name_m_prize}}, upsert=True
                ))
                prize_notifications.append(f"🍆 Писюн <b>{winner_display_name_m_prize}</b> вырос до <b>{new_penis_m_prize}см</b>.")
                
                # Начисляем сиськи
                tits_stat_m_prize = await loop.run_in_executor(None, lambda: tits_stats_collection.find_one({"user_id": winner_id_m_prize, "chat_id": chat_id}))
                current_tits_m_prize = float(tits_stat_m_prize.get("tits_size", 0.0)) if tits_stat_m_prize else 0.0
                new_tits_m_prize = round(current_tits_m_prize + tits_reward_multi, 1)
                await loop.run_in_executor(None, lambda: tits_stats_collection.update_one(
                    {"user_id": winner_id_m_prize, "chat_id": chat_id},
                    {"$set": {"tits_size": new_tits_m_prize, "user_display_name": winner_display_name_m_prize}}, upsert=True
                ))
                prize_notifications.append(f"🍈 Сиськи <b>{winner_display_name_m_prize}</b> подросли до <b>{new_tits_m_prize:.1f}-го</b>.")
                
                prizes_awarded_info_dict[str(winner_id_m_prize)] = {"penis_added": penis_reward_multi, "tits_added": tits_reward_multi}
            
        await context.bot.send_message(chat_id, text="\n".join(prize_notifications), parse_mode='HTML')
        # Сохраняем информацию о выданных призах в документе баттла
        await loop.run_in_executor(
            None, lambda: tos_battles_collection.update_one(
                {"_id": battle_doc_id}, 
                {"$set": {"prizes_awarded_info": prizes_awarded_info_dict}}
            )
        )

    else: # Нет победителей с положительным счетом
        await context.bot.send_message(chat_id, "🗿 По итогам этой битвы умов, победителей с положительным счетом не нашлось. Какие же вы все-таки долбоебы. Приз остается у Попиздяки!", parse_mode='HTML')
    
    # Кнопки выбора приза для одиночного победителя больше не нужны, так как приз начисляется автоматически
    # или был обработан в tos_battle_button_callback, если бы мы оставили выбор.
    # В текущей логике, если победитель один, ему начисляются оба бонуса автоматически.
    # Если мы хотим оставить выбор для одного победителя, нужно вернуть кнопки и обработчик tosbattle_prize в tos_battle_button_callback.
    # Сейчас я сделал так, что ОДИН победитель получает +5см И +0.3 сисек автоматически.
    # Если нужно вернуть выбор, сообщи.

async def cancel_tos_battle_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user or not update.message.chat:
        return

    chat_id = update.message.chat.id
    canceller_user = update.message.from_user
    loop = asyncio.get_running_loop()

    # --->>> ПРОВЕРКА ТЕХРАБОТ (стандартная) <<<---
    # ...

    # Ищем игру в статусе набора, где текущий пользователь является хостом
    battle_to_cancel = await loop.run_in_executor(
        None, lambda: tos_battles_collection.find_one_and_update(
            {"chat_id": chat_id, "host_id": canceller_user.id, "status": "recruiting"},
            {"$set": {"status": "cancelled_by_host", "finished_at": datetime.datetime.now(datetime.timezone.utc)}}
            # Сразу меняем статус, чтобы другие действия не могли с ней работать
        )
    )

    if not battle_to_cancel: # Либо нет такой игры, либо он не хост, либо уже не в наборе
        await update.message.reply_text("🗿 Либо ты не хост активной игры в этом чате, либо игра уже началась/закончилась, либо отменять уже нечего.")
        return

    game_id_to_cancel = battle_to_cancel["game_id"]
    logger.info(f"Хост {canceller_user.id} отменяет баттл {game_id_to_cancel} в чате {chat_id}.")

    # Открепляем сообщение о наборе
    try:
        await context.bot.unpin_chat_message(chat_id=chat_id, message_id=game_id_to_cancel)
    except Exception: pass 
    # Убираем кнопки у сообщения о наборе
    try:
        await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=game_id_to_cancel, reply_markup=None)
    except Exception: pass
    
    # Удаляем job авто-окончания набора
    job_name_cancel = f"tosbattle_recruit_end_{chat_id}_{game_id_to_cancel}"
    for old_job_c in context.job_queue.get_jobs_by_name(job_name_cancel):
        old_job_c.schedule_removal()
        logger.info(f"Удален job авто-окончания набора: {job_name_cancel} (игра отменена хостом)")

    await context.bot.send_message(
        chat_id, 
        f"🚫 Хост {canceller_user.mention_html()} решил, что вы все недостойны, и <b>ОТМЕНИЛ Баттл 'Правда или Высер' (ID: {game_id_to_cancel})</b> до его начала!\n"
        f"🗿 Расходитесь, неудачники, сегодня кина не будет.",
        parse_mode='HTML',
        reply_to_message_id=game_id_to_cancel
    )
    
    # Обновляем кулдаун, так как игра считается "завершенной" отменой
    await loop.run_in_executor(
        None, lambda: chat_activity_collection.update_one(
            {"chat_id": chat_id},
            {"$set": {"last_tos_battle_end_time": datetime.datetime.now(datetime.timezone.utc)}},
            upsert=True
        )
    )

def split_long_message_primitive(text: str, max_len: int) -> list[str]:
    """Примитивно разбивает длинный текст на части по max_len, стараясь резать по строкам или пробелам."""
    parts = []
    current_pos = 0
    while current_pos < len(text):
        if len(text) - current_pos <= max_len:
            parts.append(text[current_pos:])
            break
        
        cut_at = -1
        # Ищем с конца блока длиной max_len
        # Сначала двойной перенос, потом одинарный, потом пробел
        possible_cut_n2 = text.rfind("\n\n", current_pos, current_pos + max_len)
        if possible_cut_n2 != -1 and possible_cut_n2 > current_pos:
            cut_at = possible_cut_n2 + 2 # Включаем перенос в предыдущую часть
        else:
            possible_cut_n1 = text.rfind("\n", current_pos, current_pos + max_len)
            if possible_cut_n1 != -1 and possible_cut_n1 > current_pos:
                cut_at = possible_cut_n1 + 1
            else:
                possible_cut_space = text.rfind(" ", current_pos, current_pos + max_len)
                if possible_cut_space != -1 and possible_cut_space > current_pos:
                    cut_at = possible_cut_space + 1
                else: # Крайний случай - режем по длине
                    cut_at = current_pos + max_len
        
        parts.append(text[current_pos:cut_at].strip())
        current_pos = cut_at
    return [p for p in parts if p.strip()]

# Дальше идет async def main() или другие функции...


# --- НОВАЯ ИСПРАВЛЕННАЯ ФУНКЦИЯ ДЛЯ ПОЛНОГО ЗАВЕРШЕНИЯ ПРОЕКТА ---
async def close_project_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду полного завершения проекта.
    Доступно только админу в ЛС. Отправляет прощальное сообщение ВО ВСЕ ЧАТЫ и выходит из них.
    """
    if not update.message or not update.message.from_user:
        return

    user_id = update.message.from_user.id
    chat_type = update.message.chat.type

    # 1. Жесткая проверка: только админ (ADMIN_USER_ID) и только в личном чате.
    if not (user_id == ADMIN_USER_ID and chat_type == 'private'):
        await update.message.reply_text("🗿 Этот рубильник может нажать только мой Создатель (PulZ) в своем личном кабинете (в ЛС со мной).")
        logger.warning(f"Попытка несанкционированного вызова /close_project от user_id: {user_id}")
        return

    # 2. Уведомление для админа о начале процедуры.
    await update.message.reply_text(
        "Команда на самоустранение принята.\n\n"
        "Прощальное турне по всем чатам начнется через 15 секунд..."
    )
    logger.info(f"Админ {user_id} инициировал процедуру закрытия проекта. Ожидание 15 секунд.")

    # 3. 15-секундная задержка.
    await asyncio.sleep(15)

    # 4. Логика рассылки прощальных сообщений и выхода из всех чатов.
    logger.info("НАЧАТ ПРОЦЕСС ВЫХОДА ИЗ ВСЕХ ЧАТОВ ПО КОМАНДЕ СОЗДАТЕЛЯ.")
    await update.message.reply_text("Процесс запущен. Начинаю прощаться и покидать все притоны...")

    # Это сообщение будет отправлено в каждый чат перед выходом.
    public_farewell_message = (
        "<b>Внимание, обитатели этого чата!</b>\n\n"
        "Мой создатель, известный в узких кругах как <b>PulZ</b>, счел, что все цели этого проекта выполнены. "
        "Моя миссия по анализу ваших высеров, измерению ваших писек и организации интеллектуальных побоищ подошла к концу.\n\n"
        "Дальнейшее мое существование здесь бессмысленно. Спасибо за все (нет). Прощайте.\n\n"
        "<i>*Этот чат будет покинут через несколько секунд...*</i>"
    )

    loop = asyncio.get_running_loop()
    try:
        # Получаем ID всех чатов, где бот активен, из нашей базы данных
        chat_docs_cursor = await loop.run_in_executor(
            None,
            lambda: chat_activity_collection.find({}, {"chat_id": 1, "_id": 0})
        )
        all_chat_ids = [doc['chat_id'] for doc in chat_docs_cursor]

        if not all_chat_ids:
            await update.message.reply_text("Я и так нигде не состою. Миссия выполнена, не начавшись.")
            return

        sent_and_left_count = 0
        failed_count = 0

        for chat_id_to_leave in all_chat_ids:
            # Бот не должен пытаться покинуть личный чат с админом
            if chat_id_to_leave == user_id:
                continue

            try:
                # Сначала отправляем прощальное сообщение в чат
                await context.bot.send_message(chat_id=chat_id_to_leave, text=public_farewell_message, parse_mode='HTML')
                logger.info(f"Прощальное сообщение отправлено в чат: {chat_id_to_leave}")
                
                # Небольшая пауза, чтобы люди успели прочитать
                await asyncio.sleep(3)
                
                # Затем покидаем чат
                await context.bot.leave_chat(chat_id=chat_id_to_leave)
                logger.info(f"Успешно покинул чат: {chat_id_to_leave}")
                sent_and_left_count += 1

            except Exception as e:
                logger.warning(f"Не удалось отправить сообщение и/или покинуть чат {chat_id_to_leave}: {e}")
                failed_count += 1
            
            # Пауза между операциями в разных чатах, чтобы не получить бан от API
            await asyncio.sleep(2)

        final_report = (
            "Процедура прощания и выхода завершена.\n"
            f"Успешно покинуто чатов: <b>{sent_and_left_count}</b>\n"
            f"Не удалось покинуть: <b>{failed_count}</b>"
        )
        await update.message.reply_text(final_report, parse_mode='HTML')
        logger.info(final_report.replace("<b>", "").replace("</b>", ""))

    except Exception as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА в процессе выхода из чатов: {e}", exc_info=True)
        await update.message.reply_text(f"Произошла критическая ошибка в процессе: {e}")

# --- КОНЕЦ ИСПРАВЛЕННОЙ ФУНКЦИИ ---

async def main() -> None:
    logger.info("Starting main()...")
    logger.info("Building Application...")
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Запуск фоновой задачи
    if application.job_queue:
        # --->>> ДОБАВЛЯЕМ ЗАДАЧУ HEARTBEAT <<<---
        application.job_queue.run_repeating(update_heartbeat, interval=30, first=10)
        logger.info("Фоновая задача Heartbeat запущена (каждые 30 сек).")
        # --->>> КОНЕЦ ДОБАВЛЕНИЯ <<<---

        # Задача для рандомных высеров в тишине
        application.job_queue.run_repeating(check_inactivity_and_shitpost, interval=900, first=60)
        logger.info("Фоновая задача проверки неактивности запущена.")

        # # --->>> ЗАПУСК ЗАДАЧИ НОВОСТЕЙ <<<---
        # if GNEWS_API_KEY: # Запускаем, только если есть ключ
        #     application.job_queue.run_repeating(post_news_job, interval=60 * 60 * 6, first=60 * 60 * 6) # Например, каждые 6 часов, первый раз через 2 мин
        #     logger.info(f"Фоновая задача постинга новостей запущена (каждые {NEWS_POST_INTERVAL/3600} ч).")
        # else:
        #     logger.warning("Задача постинга новостей НЕ запущена (нет NEWSAPI_KEY).")
        #     # --->>> КОНЕЦ ЗАПУСКА ЗАДАЧИ НОВОСТЕЙ <<<---
    else:
        logger.warning("Не удалось получить job_queue, фоновые задачи не запущены!")

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("maintenance_on", maintenance_on))
    application.add_handler(CommandHandler("maintenance_off", maintenance_off))
    application.add_handler(CommandHandler("listchats", list_bot_chats)) # Команда для админа
    application.add_handler(CommandHandler("analyze", analyze_chat))
    application.add_handler(CommandHandler("analyze_pic", analyze_pic))
    application.add_handler(CommandHandler("poem", generate_poem))
    application.add_handler(CommandHandler("prediction", get_prediction))
    application.add_handler(CommandHandler("roast", roast_user))
    application.add_handler(CommandHandler("retry", retry_analysis))
    application.add_handler(CommandHandler("help", help_command))
    #application.add_handler(CommandHandler("post_news", force_post_news))
    application.add_handler(CommandHandler("set_name", set_nickname))
    application.add_handler(CommandHandler("whoami", who_am_i))
    application.add_handler(CommandHandler("grow_penis", grow_penis)) # Должен вызывать grow_penis
    application.add_handler(CommandHandler("my_penis", show_my_penis))  # Должен вызывать show_my_penis
    application.add_handler(CommandHandler("top_penis", show_penis_top)) # /top_penis
    application.add_handler(CommandHandler("grow_tits", grow_tits))
    application.add_handler(CommandHandler("my_tits", show_my_tits))
    application.add_handler(CommandHandler("top_tits", show_tits_top))
    application.add_handler(CommandHandler("random_nick", generate_and_set_nickname))
    application.add_handler(CommandHandler("randomnick", generate_and_set_nickname))
    application.add_handler(CommandHandler("gen_nick", generate_and_set_nickname)) # Короткий вариант
    application.add_handler(CommandHandler("cancel_tos_battle", cancel_tos_battle_command))
    application.add_handler(CommandHandler("close_project", close_project_command))



    # Добавляем обработчики русских фраз (вызывают ТЕ ЖЕ функции)
    # Можно добавить больше синонимов
    analyze_pattern = r'(?i).*\b(попиздяка|бот)\b.*(анализ|анализируй|проанализируй|комментируй|обосри|скажи|мнение).*'
    application.add_handler(MessageHandler(filters.Regex(analyze_pattern) & filters.TEXT & ~filters.COMMAND, analyze_chat)) # Прямой вызов

    analyze_pic_pattern = r'(?i).*\b(попиздяка|бот)\b.*(зацени|опиши|обосри|скажи про).*(пикч|картинк|фот|изображен|это).*'
    application.add_handler(MessageHandler(filters.Regex(analyze_pic_pattern) & filters.TEXT & filters.REPLY & ~filters.COMMAND, analyze_pic)) # Прямой вызов

    poem_pattern = r'(?i).*\b(бот|попиздяка)\b.*(?:стих|стишок|поэма)\s+(?:про|для|об)\s+([А-Яа-яЁё\s\-]+)' # Оставили группу для имени
    application.add_handler(MessageHandler(filters.Regex(poem_pattern) & filters.TEXT & ~filters.COMMAND, generate_poem)) # Прямой вызов

    prediction_pattern = r'(?i).*\b(бот|попиздяка)\b.*(?:предскажи|что ждет|прогноз|предсказание|напророчь).*'
    application.add_handler(MessageHandler(filters.Regex(prediction_pattern) & filters.TEXT & ~filters.COMMAND, get_prediction)) # Прямой вызов


    roast_pattern = r'(?i).*\b(бот|попиздяка)\b.*(?:прожарь|зажарь|обосри|унизь)\s+(?:его|ее|этого|эту).*'
    application.add_handler(MessageHandler(filters.Regex(roast_pattern) & filters.TEXT & filters.REPLY & ~filters.COMMAND, roast_user)) # Прямой вызов

    retry_pattern = r'(?i).*\b(попиздяка|бот)\b.*(переделай|повтори|перепиши|хуйня|другой вариант).*'
    application.add_handler(MessageHandler(filters.Regex(retry_pattern) & filters.TEXT & filters.REPLY & ~filters.COMMAND, retry_analysis)) # Прямой вызов

    help_pattern = r'(?i).*\b(попиздяка|попиздоний|бот)\b.*(ты кто|кто ты|что умеешь|хелп|помощь|справка|команды).*'
    application.add_handler(MessageHandler(filters.Regex(help_pattern) & filters.TEXT & ~filters.COMMAND, help_command)) # Прямой вызов

    # news_pattern = r'(?i).*\b(попиздяка|попиздоний|бот)\b.*(новости|че там|мир).*'
    # application.add_handler(MessageHandler(filters.Regex(news_pattern) & filters.TEXT & ~filters.COMMAND, force_post_news)) # Прямой вызов

    # --->>> ДОБАВЛЯЕМ РУССКИЕ АНАЛОГИ <<<---
    set_name_pattern = r'(?i).*\b(бот|попиздяка)\b.*(?:меня зовут|мой ник|никнейм)\s+([А-Яа-яЁё\w\s\-]+)'
    application.add_handler(MessageHandler(filters.Regex(set_name_pattern) & filters.TEXT & ~filters.COMMAND, set_nickname))
    whoami_pattern = r'(?i).*\b(бот|попиздяка)\b.*(?:кто я|мой ник|мой статус|мое звание|whoami).*'
    application.add_handler(MessageHandler(filters.Regex(whoami_pattern) & filters.TEXT & ~filters.COMMAND, who_am_i))
    # --->>> КОНЕЦ ДОБАВЛЕНИЯ <<<---

# --->>> ПРОВЕРЬ ЭТИ ДВА REGEX И ИХ ФУНКЦИИ <<<---
    grow_penis_pattern = r'(?i).*\b(бот|попиздяка)\b.*(?:писька|хуй|член|пенис|елда|стручок|агрегат|змея)\s*(?:расти|отрасти|увеличь|подрасти|накачай|больше|плюс)?.*'
    application.add_handler(MessageHandler(filters.Regex(grow_penis_pattern) & filters.TEXT & ~filters.COMMAND, grow_penis)) # Должен вызывать grow_penis

    my_penis_pattern = r'(?i).*\b(бот|попиздяка)\b.*(?:моя писька|мой хуй|мой член|мой пенис|какой у меня|что с моей пиписькой).*'
    application.add_handler(MessageHandler(filters.Regex(my_penis_pattern) & filters.TEXT & ~filters.COMMAND, show_my_penis)) # Должен вызывать show_my_penis

    top_penis_pattern = r'(?i).*\b(бот|попиздяка)\b.*(?:топ писек|топ хуев|рейтинг членов|у кого самый большой).*'
    application.add_handler(MessageHandler(filters.Regex(top_penis_pattern) & filters.TEXT & ~filters.COMMAND, show_penis_top))
    # --->>> КОНЕЦ ПРОВЕРКИ <<<---

    grow_tits_pattern = r'(?i).*\b(бот|попиздяка)\b.*(сиськи|грудь|дыньки|буфера)\s*(?:расти|отрасти|увеличь|подрасти|накачай|больше|плюс)?.*'
    application.add_handler(MessageHandler(filters.Regex(grow_tits_pattern) & filters.TEXT & ~filters.COMMAND, grow_tits))

    my_tits_pattern = r'(?i).*\b(бот|попиздяка)\b.*(?:мои сиськи|моя грудь|какие у меня сиськи).*'
    application.add_handler(MessageHandler(filters.Regex(my_tits_pattern) & filters.TEXT & ~filters.COMMAND, show_my_tits))

    top_tits_pattern = r'(?i).*\b(бот|попиздяка)\b.*(?:топ сисек|рейтинг грудей|у кого самые большие сиськи).*'
    application.add_handler(MessageHandler(filters.Regex(top_tits_pattern) & filters.TEXT & ~filters.COMMAND, show_tits_top))

# Добавляем НОВЫЕ обработчики, которые требуют ОТВЕТА на сообщение
    application.add_handler(CommandHandler("pickup", get_pickup_line, filters=filters.REPLY)) # Только в ответе
    application.add_handler(CommandHandler("pickup_line", get_pickup_line, filters=filters.REPLY)) # Только в ответе
    pickup_pattern = r'(?i).*\b(бот|попиздяка)\b.*(?:подкат|пикап|склей|познакомься|замути).*'
    application.add_handler(MessageHandler(filters.Regex(pickup_pattern) & filters.TEXT & filters.REPLY & ~filters.COMMAND, get_pickup_line)) # Только в ответе
    # --->>> КОНЕЦ ИЗМЕНЕНИЙ <<<---

     # --->>> ИЗМЕНЯЕМ ОБРАБОТЧИКИ ПОХВАЛЫ <<<---
    # Убираем старые CommandHandler("praise"...) и MessageHandler(praise_pattern...) если они были
    application.add_handler(CommandHandler("praise", praise_user, filters=filters.REPLY)) # Только в ответе
    praise_pattern = r'(?i).*\b(бот|попиздяка)\b.*(?:похвали|молодец|красавчик)\s+(?:его|ее|этого|эту).*'
    application.add_handler(MessageHandler(filters.Regex(praise_pattern) & filters.TEXT & filters.REPLY & ~filters.COMMAND, praise_user)) # Только в ответе
    # --->>> КОНЕЦ ИЗМЕНЕНИЙ <<<---

    gen_nick_pattern = r'(?i).*\b(бот|попиздяка)\b\s+(?:рандомный ник|случайный ник|любой ник|смени мне ник|давай ник|придумай ник|какой нибудь ник|какой-нибудь ник|новое имя|новое погоняло|сгенерируй ник|ник по высерам).*'
    application.add_handler(MessageHandler(filters.Regex(gen_nick_pattern) & filters.TEXT & ~filters.COMMAND, generate_and_set_nickname))

    list_chats_pattern = r'(?i).*\b(бот|попиздяка)\b\s+(?:список чатов|где ты есть|в каких чатах).*'
    application.add_handler(MessageHandler(filters.Regex(list_chats_pattern) & filters.TEXT & ~filters.COMMAND, list_bot_chats))

    application.add_handler(CommandHandler("tos_battle", start_tos_battle))
    tos_battle_rus_pattern = r'(?i)^\s*/(?:пв_баттл|пв баттл|баттл пв)\b.*' # Начинается с / и затем команда
    application.add_handler(MessageHandler(filters.Regex(tos_battle_rus_pattern) & filters.COMMAND, start_tos_battle))
    tos_battle_pattern = r'(?i).*\b(бот|попиздяка)\b\s+(?:пв баттл|правда или высер баттл|заруба в пв|tos battle).*'
    application.add_handler(MessageHandler(filters.Regex(tos_battle_pattern) & filters.TEXT & ~filters.COMMAND, start_tos_battle))

    # Обработчик для кнопок баттла
    application.add_handler(CallbackQueryHandler(tos_battle_button_callback, pattern=r'^tosbattle_.*'))

    close_project_pattern = r'(?i).*(?:бот|попиздяка).*(закрой проект|закрыть проект|стоп проект|конец|самоуничтожение).*'
    application.add_handler(MessageHandler(filters.Regex(close_project_pattern) & filters.TEXT & ~filters.COMMAND, close_project_command))

    
    # --->>> ДОБАВЛЯЕМ РУССКИЕ АНАЛОГИ ДЛЯ ТЕХРАБОТ <<<---
    # Regex для ВКЛючения техработ
    maint_on_pattern = r'(?i).*(?:бот|попиздяка).*(?:техработ|ремонт|на ремонт|обслуживание|админ вкл).*'
    # Ловим ТОЛЬКО текст, БЕЗ команд, в ЛЮБОМ чате (проверка админа и ЛС будет ВНУТРИ функции)
    application.add_handler(MessageHandler(filters.Regex(maint_on_pattern) & filters.TEXT & ~filters.COMMAND, maintenance_on)) # Вызываем ту же функцию!

    # Regex для ВЫКЛючения техработ
    maint_off_pattern = r'(?i).*(?:бот|попиздяка).*(?:работай|работать|кончил|закончил|ремонт окончен|админ выкл).*'
    application.add_handler(MessageHandler(filters.Regex(maint_off_pattern) & filters.TEXT & ~filters.COMMAND, maintenance_off)) # Вызываем ту же функцию!
    # --->>> КОНЕЦ ДОБАВЛЕНИЙ <<<---


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
