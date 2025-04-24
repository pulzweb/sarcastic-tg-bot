# --- НАЧАЛО ПОЛНОГО КОДА BOT.PY (ВЕРСИЯ ДЛЯ GROQ API) ---
import logging
import os
import asyncio
from collections import deque
from flask import Flask
import hypercorn.config
from hypercorn.asyncio import serve as hypercorn_async_serve
import signal

# --->>> УБРАЛИ ИМПОРТЫ GEMINI <<<---
# --->>> ДОБАВИЛИ ИМПОРТЫ OPENAI <<<---
from openai import OpenAI, AsyncOpenAI # Используем библиотеку OpenAI
import httpx # Она нужна openai >= 1.0
# --->>> КОНЕЦ ИЗМЕНЕНИЙ В ИМПОРТАХ <<<---

from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Загружаем секреты (.env для локального запуска, Render использует переменные окружения)
load_dotenv()

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# --->>> ДОБАВИЛИ КЛЮЧ GROQ <<<---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# --->>> КОНЕЦ ДОБАВЛЕНИЙ <<<---
MAX_MESSAGES_TO_ANALYZE = 500

# Проверка ключей
if not TELEGRAM_BOT_TOKEN: raise ValueError("НЕ НАЙДЕН TELEGRAM_BOT_TOKEN!")
if not GROQ_API_KEY: raise ValueError("НЕ НАЙДЕН GROQ_API_KEY! Добавь его в переменные окружения Render!") # <-- Изменили проверку

# --- Логирование (без изменений) ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("hypercorn").setLevel(logging.INFO)
# Добавим логгер для OpenAI, чтобы видеть запросы (опционально)
logging.getLogger("openai").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

# --- НАСТРОЙКА КЛИЕНТА GROQ API ---
try:
    # Используем АСИНХРОННЫЙ клиент OpenAI, но для эндпоинта Groq
    groq_client = AsyncOpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1" # СТАНДАРТНЫЙ ЭНДПОИНТ GROQ - ПРОВЕРЬ В ДОКЕ НА ВСЯКИЙ!
    )
    logger.info("Клиент AsyncOpenAI для Groq API настроен.")
except Exception as e:
     logger.critical(f"ПИЗДЕЦ при настройке клиента Groq: {e}", exc_info=True)
     raise SystemExit(f"Не удалось настроить клиента Groq: {e}")

# УКАЗЫВАЕМ ID МОДЕЛИ, КОТОРУЮ ТЫ ВЫБРАЛ
# УБЕДИСЬ, ЧТО ОНА ТОЧНО ЕСТЬ В СПИСКЕ НА GROQ.COM/API/MODELS !!!
GROQ_MODEL_ID = "deepseek-r1-distill-llama-70b" # <--- ТВОЙ ВЫБОР (ПРОВЕРЬ НАЛИЧИЕ!)
# Если ее нет, попробуй: "llama3-8b-8192" или "mixtral-8x7b-32768"
logger.info(f"Будет использоваться модель Groq: {GROQ_MODEL_ID}")
# --- КОНЕЦ НАСТРОЙКИ КЛИЕНТА GROQ API ---

# --- Хранилище истории (без изменений) ---
chat_histories = {}
logger.info(f"Максимальная длина истории сообщений для анализа: {MAX_MESSAGES_TO_ANALYZE}")

# --- ОБРАБОТЧИКИ СООБЩЕНИЙ (store_message без изменений) ---
async def store_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (код store_message остается ТОЧНО ТАКИМ ЖЕ, как в последней версии)
    # ... (он НЕ ДОЛЖЕН вызывать распознавание голоса или картинок)
    if not update.message or not update.message.from_user: return
    message_text = None
    is_voice = False # Не используем, но оставим пока
    chat_id = update.message.chat_id
    user_name = update.message.from_user.first_name or "Анонимный долбоеб"
    if update.message.text: message_text = update.message.text
    # --- Заглушки для фото/стикеров (ЕСЛИ РЕАЛИЗОВЫВАЛИ) ---
    elif update.message.photo: message_text = "[ОТПРАВИЛ(А) КАРТИНКУ]" # Пример заглушки
    elif update.message.sticker: message_text = f"[ОТПРАВИЛ(А) СТИКЕР {update.message.sticker.emoji or ''}]" # Пример заглушки
    # --- Конец заглушек ---
    if message_text:
        if chat_id not in chat_histories: chat_histories[chat_id] = deque(maxlen=MAX_MESSAGES_TO_ANALYZE)
        prefix = f"{user_name}"
        chat_histories[chat_id].append(f"{prefix}: {message_text}")

# --- ОБРАБОТЧИК КОМАНДЫ /analyze (ПЕРЕПИСАН ПОД GROQ / OPENAI API) ---
async def analyze_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (начало функции: проверки, получение user_name, chat_id, проверка истории - как было) ...
    if not update.message or not update.message.from_user: return
    chat_id = update.message.chat_id
    user_name = update.message.from_user.first_name or "Эй ты там"
    logger.info(f"Пользователь '{user_name}' (ID: {update.message.from_user.id}) запросил анализ в чате {chat_id} через Groq ({GROQ_MODEL_ID})")
    min_msgs = 10
    history_len = len(chat_histories.get(chat_id, []))
    if chat_id not in chat_histories or history_len < min_msgs:
        logger.info(f"В чате {chat_id} слишком мало сообщений ({history_len}/{min_msgs}) для анализа.")
        await update.message.reply_text(f"Слышь, {user_name}, надо {min_msgs} сообщений, а у меня {history_len}. Попизди еще.")
        return
    messages_to_analyze = list(chat_histories[chat_id])
    conversation_text = "\n".join(messages_to_analyze) # Передаем всю историю одним куском
    logger.info(f"Начинаю анализ {len(messages_to_analyze)} сообщений для чата {chat_id} через Groq...")

    try:
        # --->>> НОВЫЙ КОД ВЫЗОВА GROQ API <<<---
        system_prompt = (
            f"Ты - въедливый и язвительный сплетник-летописец Telegram-чата. Твоя задача - проанализировать ПОСЛЕДНИЙ фрагмент переписки, выхватить из него несколько (1-10) самых интересных моментов И ОБЯЗАТЕЛЬНО УКАЗАТЬ, КТО ИЗ УЧАСТНИКОВ (по именам/никам из диалога) что сказал или сделал в этом моменте. **ТАКЖЕ ОБРАЩАЙ ВНИМАНИЕ НА СООБЩЕНИЯ ОТ ДРУГИХ БОТОВ (@PredskazBot, @PenisMeterBot и т.п.), ЕСЛИ ОНИ АДРЕСОВАНЫ КОНКРЕТНОМУ ПОЛЬЗОВАТЕЛЮ (@username).\n\n"
            f"Фрагмент переписки:\n"
            f"```\n{conversation_text}\n```\n\n"
            f"Инструкции для твоего ответа:\n"
            f"1.  Для КАЖДОГО выделенного момента сформулируй **КОРОТКИЙ (1-2 предложения)** комментарий в стиле **постироничного троллинга с упоминанием имен ИЛИ ЦЕЛИ сообщения другого бота**. Используй сарказм, намеки, легкий абсурд. Поддевай конкретных участников или высмеивай предсказания/измерения, адресованные им.\n"
            f"2.  **МАТ ИСПОЛЬЗУЙ** умеренно, для усиления иронии.\n"
            f"3.  **КАЖДЫЙ** комментарий начинай с новой строки и символа **`🗿 `** (Моаи и пробел).\n"
            f"4.  **ОБЯЗАТЕЛЬНО включай имена участников**, о которых идет речь. **Если комментируешь сообщение от другого бота, укажи, КОМУ (@username) оно было адресовано.** Если имя не очевидно, не придумывай.\n"
            f"5.  Если не можешь выделить конкретных участников или интересный момент, напиши ОДНУ строку в духе: `🗿 Безликая масса опять переливала из пустого в порожнее. Имен героев история не сохранила.`\n"
            f"6.  Не пиши вступлений. Сразу начинай с `🗿 `.\n\n"
            f"Пример ЗАЕБАТОГО ответа (с учетом другого бота):\n"
            f"🗿 Похоже, Вася пытался убедить Петю...\n"
            f"🗿 А Маша в это время очень вовремя вставила историю...\n"
            f"🗿 @PredskazBot выдал @depil_estet предсказание в стиле 'отдохни, псина'. Звучит как план, хули.\n" # <--- ПРИМЕР
            f"🗿 @PenisMeterBot сообщил @nagibator666, что у него 15 см. Стандартно, но хоть не 5. Бывало и хуже.\n" # <--- ПРИМЕР
            f"\nВыдай результат в указанном формате, НЕ ЗАБЫВАЯ ИМЕНА и ЦЕЛИ сообщений других ботов:"
        )
        messages_for_api = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": conversation_text} # Вся история как один запрос юзера
        ]

        thinking_message = await update.message.reply_text(f"Так, блядь, щас подключу быстрые мозги Groq ({GROQ_MODEL_ID.split('-')[0]}) и подумаю...")

        logger.info(f"Отправка запроса к Groq API ({GROQ_MODEL_ID})...")
        response = await groq_client.chat.completions.create(
            model=GROQ_MODEL_ID, # Используем выбранную тобой модель
            messages=messages_for_api,
            max_tokens=250, # Можно чуть больше, модели умнее
            temperature=0.7, # Немного креативности
            # stream=False # Не используем стриминг для простоты
        )
        logger.info("Получен ответ от Groq API.")
        try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass

        # Извлекаем ответ
        sarcastic_summary = "[Groq промолчал или вернул хуйню]"
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            sarcastic_summary = response.choices[0].message.content.strip()

        await update.message.reply_text(sarcastic_summary)
        logger.info(f"Отправил результат анализа Groq '{sarcastic_summary[:50]}...' в чат {chat_id}")
        # --->>> КОНЕЦ НОВОГО КОДА ВЫЗОВА GROQ API <<<---

    except Exception as e:
        # Обработка ошибок Groq API
        logger.error(f"ПИЗДЕЦ при вызове Groq API для чата {chat_id}: {e}", exc_info=True)
        try:
            if 'thinking_message' in locals(): await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass
        await update.message.reply_text(
            f"Бля, {user_name}, мои новые быстрые мозги Groq дали сбой. То ли API упал, то ли ты им хуйню подсунул. "
            f"Ошибка типа: `{type(e).__name__}`. Попробуй позже."
        )

# --- ОБРАБОТЧИК КОМАНДЫ /analyze_pic (ЗАГЛУШКА!) ---
async def analyze_pic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сообщает, что не умеет анализировать картинки через Groq API."""
    if not update.message or not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text("Ответь командой /analyze_pic на КАРТИНКУ, дятел!")
        return
    user_name = update.message.from_user.first_name or "Пикассо недоделанный"
    logger.info(f"Пользователь '{user_name}' запросил анализ картинки, но Groq API это не умеет.")
    await update.message.reply_text(
        f"Слышь, {user_name}, я теперь на Groq, он быстрый как понос, но СМОТРЕТЬ КАРТИНКИ НЕ УМЕЕТ (через этот API). "
        f"Так что обсирать твой 'шедевр' не буду. Только текст, только хардкор. 🗿"
    )

# --- ОБРАБОТЧИК greet_chat_member (БЕЗ ИЗМЕНЕНИЙ) ---
async def greet_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (код greet_chat_member остается ТОЧНО ТАКИМ ЖЕ) ...
    result = update.chat_member; #... и так далее ...

# --- АСИНХРОННАЯ ЧАСТЬ С HYPERCORN (main, run_bot_async - БЕЗ ИЗМЕНЕНИЙ В ЛОГИКЕ ЗАПУСКА) ---
app = Flask(__name__)
@app.route('/')
def index(): #... как было ...
async def run_bot_async(application: Application) -> None: #... как было ...
async def main() -> None: #... как было, НО ИСПОЛЬЗУЕТ НОВЫЙ КЛИЕНТ groq_client ...
    logger.info("Запуск асинхронной функции main().")
    logger.info("Сборка Telegram Application...")
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    # Добавляем обработчики
    application.add_handler(CommandHandler("analyze", analyze_chat)) # Вызывает новую версию
    application.add_handler(CommandHandler("analyze_pic", analyze_pic)) # Вызывает заглушку
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, store_message))
    application.add_handler(ChatMemberUpdatedHandler(greet_chat_member, ChatMemberUpdated.MY_CHAT_MEMBER))
    logger.info("Обработчики Telegram добавлены.")
    # ... (настройка Hypercorn и запуск задач как было) ...
    port = int(os.environ.get("PORT", 8080)); #... и так далее ...
    hypercorn_config = hypercorn.config.Config(); #... и так далее ...
    bot_task = asyncio.create_task(run_bot_async(application), name="TelegramBotTask"); #... и так далее ...
    server_task = asyncio.create_task(hypercorn_async_serve(app, hypercorn_config, shutdown_trigger=shutdown_event.wait), name="HypercornServerTask"); #... и так далее ...
    # ... (обработка завершения задач как было) ...

# --- Точка входа в скрипт (БЕЗ ИЗМЕНЕНИЙ, кроме проверки ключа) ---
if __name__ == "__main__":
    logger.info(f"Скрипт bot.py запущен как основной (__name__ == '__main__').")
    # ... (создание шаблона .env как было, НО МОЖНО УДАЛИТЬ СТРОКУ ПРО GEMINI_API_KEY) ...
    if not os.path.exists('.env') and not os.getenv('RENDER'):
        try:
            with open('.env', 'w') as f: f.write(f"TELEGRAM_BOT_TOKEN=...\nGROQ_API_KEY=...\n") # <-- Убрали Gemini
            logger.warning("Создан ШАБЛОН файла .env...")
        except Exception as e: logger.error(f"Не удалось создать шаблон .env файла: {e}")
    # ПРОВЕРЯЕМ ОБА КЛЮЧА ПЕРЕД ЗАПУСКОМ!
    if not TELEGRAM_BOT_TOKEN or not GROQ_API_KEY:
        logger.critical("ОТСУТСТВУЮТ КЛЮЧИ TELEGRAM_BOT_TOKEN или GROQ_API_KEY!"); exit(1) # <-- Изменили проверку
    # ... (запуск asyncio.run(main()) как было) ...
    try: logger.info("Запускаю asyncio.run(main())..."); asyncio.run(main()); #... и так далее ...

# --- КОНЕЦ ПОЛНОГО КОДА BOT.PY (ВЕРСИЯ ДЛЯ GROQ API) ---