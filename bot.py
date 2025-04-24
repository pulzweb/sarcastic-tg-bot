# --- НАЧАЛО СУПЕР-МЕГА-ПОЛНОГО КОДА BOT.PY (GROQ, ИСПРАВЛЕННЫЕ ФИЛЬТРЫ И МОДЕЛЬ) ---
import logging
import os
import asyncio
from collections import deque
from flask import Flask
import hypercorn.config
from hypercorn.asyncio import serve as hypercorn_async_serve
import signal

# Импорты для OpenAI-совместимого API (Groq)
from openai import OpenAI, AsyncOpenAI
import httpx

# Импорты Telegram
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes # Убрали ChatMemberUpdatedHandler

from dotenv import load_dotenv

# Загружаем секреты (.env для локального запуска)
load_dotenv()

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# СКОЛЬКО ПОСЛЕДНИХ СООБЩЕНИЙ ХРАНИМ И АНАЛИЗИРУЕМ
# 500 - ЭТО ДОХУЯ, МОЖЕТ БЫТЬ МЕДЛЕННО/ДОРОГО. ПОСТАВЬ 50-100 ДЛЯ НАЧАЛА!
MAX_MESSAGES_TO_ANALYZE = 50

# Проверка ключей
if not TELEGRAM_BOT_TOKEN: raise ValueError("НЕ НАЙДЕН TELEGRAM_BOT_TOKEN!")
if not GROQ_API_KEY: raise ValueError("НЕ НАЙДЕН GROQ_API_KEY!")

# --- Логирование ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("hypercorn").setLevel(logging.INFO)
logging.getLogger("openai").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

# --- НАСТРОЙКА КЛИЕНТА GROQ API ---
try:
    groq_client = AsyncOpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )
    logger.info("Клиент AsyncOpenAI для Groq API настроен.")
except Exception as e:
     logger.critical(f"ПИЗДЕЦ при настройке клиента Groq: {e}", exc_info=True)
     raise SystemExit(f"Не удалось настроить клиента Groq: {e}")

# ID МОДЕЛИ НА GROQ (УБЕДИСЬ, ЧТО ОНА ДОСТУПНА!)
GROQ_MODEL_ID = "deepseek-r1-distill-llama-70b" # ТВОЯ МОДЕЛЬ! ПЕРЕПРОВЕРЬ! Если нет, ставь llama3-8b-8192
logger.info(f"Будет использоваться модель Groq: {GROQ_MODEL_ID}")

# --- Хранилище истории ---
chat_histories = {}
logger.info(f"Максимальная длина истории сообщений для анализа: {MAX_MESSAGES_TO_ANALYZE}")

# --- ОБРАБОТЧИК СООБЩЕНИЙ (Сохраняет текст, фото/стикеры как заглушки) ---
async def store_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user:
        return
    message_text = None
    chat_id = update.message.chat_id
    user_name = update.message.from_user.first_name or "Анонимный долбоеб"

    if update.message.text:
        message_text = update.message.text
    elif update.message.photo:
        message_text = "[ОТПРАВИЛ(А) КАРТИНКУ]" # Заглушка
    elif update.message.sticker:
        emoji = update.message.sticker.emoji or ''
        message_text = f"[ОТПРАВИЛ(А) СТИКЕР {emoji}]" # Заглушка

    if message_text:
        if chat_id not in chat_histories:
            chat_histories[chat_id] = deque(maxlen=MAX_MESSAGES_TO_ANALYZE)
        prefix = f"{user_name}"
        chat_histories[chat_id].append(f"{prefix}: {message_text}")
        # logger.debug(f"Сообщение от {user_name} добавлено в историю чата {chat_id}.")

# --- ОБРАБОТЧИК КОМАНДЫ /analyze ---
async def analyze_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user: return
    chat_id = update.message.chat_id
    user_name = update.message.from_user.first_name or "Эй ты там"
    logger.info(f"Пользователь '{user_name}' запросил анализ в чате {chat_id} через Groq ({GROQ_MODEL_ID})")
    min_msgs = 10
    history = chat_histories.get(chat_id)
    history_len = len(history) if history else 0

    if not history or history_len < min_msgs:
        logger.info(f"В чате {chat_id} слишком мало сообщений ({history_len}/{min_msgs}) для анализа.")
        await update.message.reply_text(f"Слышь, {user_name}, надо {min_msgs} сообщений, а у меня {history_len}. Попизди еще.")
        return

    # Берем ПОСЛЕДНИЕ N сообщений, N = MAX_MESSAGES_TO_ANALYZE
    messages_to_analyze = list(history) # deque сам хранит только N последних
    conversation_text = "\n".join(messages_to_analyze)
    logger.info(f"Начинаю анализ {len(messages_to_analyze)} сообщений для чата {chat_id} через Groq...")

    try:
        # Промпт для Groq (с 🗿 и попыткой имен)
        system_prompt = (
             f"Ты - въедливый и язвительный сплетник-летописец Telegram-чата. Твоя задача - проанализировать диалог, выхватить 1-3 интересных момента И ОБЯЗАТЕЛЬНО УКАЗАТЬ, КТО (по именам/никам) что сказал/сделал. "
             f"Отвечай КОРОТКО (1-2 предложения на момент) в стиле постироничного троллинга с МАТОМ (умеренно). Начинай КАЖДЫЙ комментарий с '🗿 '. Обязательно включай имена. Если ничего нет - напиши '🗿 Безликая масса опять переливала из пустого в порожнее.' НЕ ПИШИ ВСТУПЛЕНИЙ."
         )
        messages_for_api = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": conversation_text}
        ]

        thinking_message = await update.message.reply_text(f"Так, блядь, щас подключу быстрые мозги Groq ({GROQ_MODEL_ID.split('-')[0]}) и подумаю...")

        logger.info(f"Отправка запроса к Groq API ({GROQ_MODEL_ID})...")
        response = await groq_client.chat.completions.create(
            model=GROQ_MODEL_ID,
            messages=messages_for_api,
            max_tokens=300, # Можно подкрутить
            temperature=0.7,
        )
        logger.info("Получен ответ от Groq API.")
        try: await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass

        sarcastic_summary = "[Groq промолчал или спизданул хуйню]"
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            sarcastic_summary = response.choices[0].message.content.strip()

        await update.message.reply_text(sarcastic_summary)
        logger.info(f"Отправил результат анализа Groq '{sarcastic_summary[:50]}...' в чат {chat_id}")

    except Exception as e:
        logger.error(f"ПИЗДЕЦ при вызове Groq API для чата {chat_id}: {e}", exc_info=True)
        try:
            if 'thinking_message' in locals(): await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception: pass
        await update.message.reply_text(
            f"Бля, {user_name}, мои новые быстрые мозги Groq дали сбой. Ошибка: `{type(e).__name__}`. Попробуй позже."
        )

# --- ФУНКЦИЯ analyze_pic ЗАГЛУШЕНА ---
async def analyze_pic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text("Ответь командой /analyze_pic на КАРТИНКУ, дятел!")
        return
    user_name = update.message.from_user.first_name or "Пикассо недоделанный"
    logger.info(f"Пользователь '{user_name}' запросил анализ картинки, но Groq API это не умеет.")
    await update.message.reply_text(
        f"Слышь, {user_name}, я теперь на Groq, он быстрый, но КАРТИНКИ НЕ ВИДИТ. Обсирать не буду. 🗿"
    )

# --- АСИНХРОННАЯ ЧАСТЬ С HYPERCORN ---
app = Flask(__name__)
@app.route('/')
def index():
    logger.info("Получен GET запрос на '/', отвечаю OK.")
    return "Я саркастичный бот, и я все еще жив (наверное)."

async def run_bot_async(application: Application) -> None:
    # Запускает и корректно останавливает бота
    try:
        logger.info("Инициализация Telegram Application...")
        await application.initialize()
        if not application.updater: logger.critical("Updater не был создан!"); return
        logger.info("Запуск получения обновлений (start_polling)...")
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Запуск диспетчера Application (start)...")
        await application.start()
        logger.info("Бот запущен и работает... (ожидание отмены или сигнала)")
        await asyncio.Future() # Ожидаем вечно
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        logger.info("Получен сигнал остановки.")
    except Exception as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА в run_bot_async: {e}", exc_info=True)
    finally:
        # Корректная остановка
        logger.info("Начинаю процесс ОСТАНОВКИ бота...")
        if application.running:
            logger.info("Остановка диспетчера Application (stop)..."); await application.stop(); logger.info("Диспетчер Application остановлен.")
        if application.updater and application.updater.is_running:
            logger.info("Остановка получения обновлений (updater.stop)..."); await application.updater.stop(); logger.info("Получение обновлений (updater) остановлено.")
        logger.info("Завершение работы Application (shutdown)..."); await application.shutdown(); logger.info("Процесс остановки бота завершен.")

async def main() -> None:
    # Основная асинхронная функция
    logger.info("Запуск асинхронной функции main().")
    logger.info("Сборка Telegram Application...")
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    # Добавляем обработчики
    application.add_handler(CommandHandler("analyze", analyze_chat))
    application.add_handler(CommandHandler("analyze_pic", analyze_pic)) # Оставляем заглушку

    # --->>> ТРИ ОТДЕЛЬНЫХ ОБРАБОТЧИКА ДЛЯ store_message <<<---
    # 1. Только для ТЕКСТА (без команд)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, store_message))
    # 2. Только для ФОТО
    application.add_handler(MessageHandler(filters.PHOTO, store_message))
    # 3. Только для СТИКЕРОВ
    application.add_handler(MessageHandler(filters.Sticker, store_message))
    # --->>> КОНЕЦ ТРЕХ ОТДЕЛЬНЫХ ОБРАБОТЧИКОВ <<<---

    # Убрали ChatMemberUpdatedHandler
    logger.info("Обработчики Telegram добавлены.")
    # Настройка и запуск Hypercorn + бота
    port = int(os.environ.get("PORT", 8080))
    hypercorn_config = hypercorn.config.Config()
    hypercorn_config.bind = [f"0.0.0.0:{port}"]
    hypercorn_config.worker_class = "asyncio"
    hypercorn_config.shutdown_timeout = 60.0
    logger.info(f"Конфигурация Hypercorn: {hypercorn_config.bind}, worker={hypercorn_config.worker_class}")
    logger.info("Создание и запуск конкурентных задач для Hypercorn и Telegram бота...")
    shutdown_event = asyncio.Event()
    bot_task = asyncio.create_task(run_bot_async(application), name="TelegramBotTask")
    server_task = asyncio.create_task(
        hypercorn_async_serve(app, hypercorn_config, shutdown_trigger=shutdown_event.wait), # Используем импортированную функцию
        name="HypercornServerTask"
    )
    # Ожидание завершения
    done, pending = await asyncio.wait([bot_task, server_task], return_when=asyncio.FIRST_COMPLETED)
    logger.warning(f"Одна из основных задач завершилась! Done: {done}, Pending: {pending}")
    # Корректное завершение остальных задач
    if server_task in pending: logger.info("Сигнализируем Hypercorn серверу на остановку..."); shutdown_event.set()
    logger.info("Отменяем и ожидаем завершения оставшихся задач...")
    for task in pending: task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    # Проверка ошибок
    for task in done:
        logger.info(f"Проверка завершенной задачи: {task.get_name()}")
        try: await task
        except asyncio.CancelledError: logger.info(f"Задача {task.get_name()} была отменена.")
        except Exception as e: logger.error(f"Задача {task.get_name()} завершилась с ошибкой: {e}", exc_info=True)
    logger.info("Асинхронная функция main() завершила работу.")

# --- Точка входа в скрипт ---
if __name__ == "__main__":
    logger.info(f"Скрипт bot.py запущен как основной (__name__ == '__main__').")
    # Создаем .env шаблон, если надо
    if not os.path.exists('.env') and not os.getenv('RENDER'):
        logger.warning("Файл .env не найден...")
        try:
            with open('.env', 'w') as f: f.write(f"TELEGRAM_BOT_TOKEN=...\nGROQ_API_KEY=...\n") # Обновленный шаблон
            logger.warning("Создан ШАБЛОН файла .env...")
        except Exception as e: logger.error(f"Не удалось создать шаблон .env файла: {e}")
    # Проверяем ключи
    if not TELEGRAM_BOT_TOKEN or not GROQ_API_KEY: logger.critical("ОТСУТСТВУЮТ КЛЮЧИ!"); exit(1)
    # Запускаем
    try:
        logger.info("Запускаю asyncio.run(main())...")
        asyncio.run(main())
        logger.info("asyncio.run(main()) завершен.")
    except Exception as e: logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА на верхнем уровне: {e}", exc_info=True); exit(1)
    finally: logger.info("Скрипт bot.py завершает работу.")

# --- КОНЕЦ СУПЕР-МЕГА-ПОЛНОГО КОДА BOT.PY (GROQ, ИСПРАВЛЕННЫЕ ФИЛЬТРЫ И МОДЕЛЬ) ---