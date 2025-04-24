# --- НАЧАЛО ПОЛНОГО КОДА BOT.PY (ВЕРСИЯ С ASYNCIO + HYPERCORN) ---
import logging
import os
import asyncio # ОСНОВА ВСЕЙ АСИНХРОННОЙ МАГИИ
from collections import deque
# УБРАЛИ НАХУЙ THREADING
from flask import Flask # Веб-сервер-заглушка для Render
import hypercorn # Асинхронный веб-сервер для запуска Flask под asyncio
import hypercorn.config # Для настройки Hypercorn
import signal # Для корректной обработки сигналов остановки (хотя asyncio.run сам умеет)

import google.generativeai as genai
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv # Чтобы читать твой .env файл или переменные Render

# Загружаем секреты
load_dotenv()

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MAX_MESSAGES_TO_ANALYZE = 50 # Меняй на свой страх и риск

# Проверка ключей
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("НЕ НАЙДЕН TELEGRAM_BOT_TOKEN!")
if not GEMINI_API_KEY:
    raise ValueError("НЕ НАЙДЕН GEMINI_API_KEY!")

# --- Логирование ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("hypercorn").setLevel(logging.INFO) # Чтобы видеть логи Hypercorn
logger = logging.getLogger(__name__)

# --- Настройка Gemini ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("Модель Gemini успешно настроена.")
except Exception as e:
    logger.critical(f"ПИЗДЕЦ при настройке Gemini API: {e}", exc_info=True)
    raise SystemExit(f"Не удалось настроить Gemini API: {e}")

# --- Хранилище истории ---
chat_histories = {}
logger.info(f"Максимальная длина истории сообщений для анализа: {MAX_MESSAGES_TO_ANALYZE}")

# --- ОБРАБОТЧИКИ СООБЩЕНИЙ И КОМАНД (БЕЗ ИЗМЕНЕНИЙ) ---
async def store_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or not update.message.from_user:
        return
    chat_id = update.message.chat_id
    message_text = update.message.text
    user_name = update.message.from_user.first_name or "Анонимный долбоеб"
    if chat_id not in chat_histories:
        chat_histories[chat_id] = deque(maxlen=MAX_MESSAGES_TO_ANALYZE)
        # logger.info(f"Создана новая история для чата {chat_id}") # Убрал лишний лог
    chat_histories[chat_id].append(f"{user_name}: {message_text}")

async def analyze_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user:
        return
    chat_id = update.message.chat_id
    user_name = update.message.from_user.first_name or "Эй ты там"
    logger.info(f"Пользователь '{user_name}' (ID: {update.message.from_user.id}) запросил анализ в чате {chat_id}")
    min_msgs = 10
    history_len = len(chat_histories.get(chat_id, []))
    if chat_id not in chat_histories or history_len < min_msgs:
        logger.info(f"В чате {chat_id} слишком мало сообщений ({history_len}/{min_msgs}) для анализа.")
        await update.message.reply_text(
            f"Слышь, {user_name}, ты заебал. Я тут недавно (или вы молчали как рыбы), сообщений кот наплакал "
            f"(всего {history_len} штук в моей памяти, а надо хотя бы {min_msgs}).\n"
            f"Попиздите еще хотя бы немного, потом посмотрим на ваш балаган.\n"
            f"(Или я просто просыпаюсь после спячки Render, подожди секунд 30 и попробуй еще раз, нетерпеливый уебок)."
        )
        return
    messages_to_analyze = list(chat_histories[chat_id])
    conversation_text = "\n".join(messages_to_analyze)
    logger.info(f"Начинаю анализ {len(messages_to_analyze)} сообщений для чата {chat_id}...")
    try:
        prompt = ( # ТВОЙ ДЛИННЫЙ ОХУЕННЫЙ ПРОМПТ ЗДЕСЬ
            f"Ты - саркастичный и циничный ассистент, анализирующий переписки в Telegram-чатах. "
            f"Тебе предоставили фрагмент диалога:\n\n"
            f"--- НАЧАЛО ДИАЛОГА ---\n{conversation_text}\n--- КОНЕЦ ДИАЛОГА ---\n\n"
            f"Твоя задача:\n"
            f"1. Прочитай этот диалог и выдели САМУЮ ГЛАВНУЮ СУТЬ, основную тему или итоговый вывод. Игнорируй флуд, приветствия, прощания и прочую незначащую поебень.\n"
            f"2. Сформулируй этот вывод **МАКСИМАЛЬНО САРКАСТИЧНО, ЯЗВИТЕЛЬНО, ПРЕЗРИТЕЛЬНО И ЦИНИЧНО**. Используй РУССКУЮ НЕНОРМАТИВНУЮ ЛЕКСИКУ (мат), но используй ее УМЕСТНО, чтобы подчеркнуть идиотизм ситуации или тупость обсуждающих. Твой стиль - злой, уставший от тупости мира циник.\n"
            f"3. Ответ должен быть **КОРОТКИМ**, сука, 1-3 предложения. Никаких вступлений типа 'Проанализировав диалог...'. СРАЗУ выдавай свой саркастичный вердикт.\n"
            f"4. Не обращайся напрямую к пользователям чата в своем ответе. Просто констатируй факт в своей манере.\n\n"
            f"Пример хуевого ответа: 'Пользователи обсуждали планы на выходные.'\n"
            f"Пример ЗАЕБАТОГО ответа: 'Похоже, эти бездари опять пытаются придумать, как просрать очередные выходные. Уровень дискуссии - /dev/null.' ИЛИ 'Охуеть, сборище интеллектуалов решает глобальную проблему выбора пива. Мир точно в безопасности.'\n\n"
            f"КОРОЧЕ, НЕ НУДИ! ДЕЛАЙ СМЕШНО, ЗЛО И ПО СУТИ! Выдай свой вердикт:"
        )
        thinking_message = await update.message.reply_text("Так, блядь, щас напрягу свои кремниевые мозги и попробую понять смысл вашего высокоинтеллектуального бреда... Не мешайте, я в процессе (или тупо сплю, хуй знает)...")
        logger.debug(f"Отправил сообщение 'думаю' (ID: {thinking_message.message_id}) в чат {chat_id}")
        logger.info(f"Отправляю запрос к Gemini для чата {chat_id}...")
        response = await model.generate_content_async(prompt)
        logger.info(f"Получен ответ от Gemini для чата {chat_id}")
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
            logger.debug(f"Удалил сообщение 'думаю' (ID: {thinking_message.message_id}) в чате {chat_id}")
        except Exception as delete_err:
            logger.warning(f"Не смог удалить сообщение 'думаю' (ID: {thinking_message.message_id}) в чате {chat_id}: {delete_err}")
        sarcastic_summary = "Бля, хуйню какую-то нейронка выдала или вообще пустой ответ. Видимо, ваш треп настолько бессмысленный, что даже ИИ повесился."
        if response and response.text:
             sarcastic_summary = response.text.strip()
        await update.message.reply_text(sarcastic_summary)
        logger.info(f"Отправил результат анализа '{sarcastic_summary[:50]}...' в чат {chat_id}")
    except Exception as e:
        logger.error(f"ПИЗДЕЦ при выполнении анализа для чата {chat_id}: {e}", exc_info=True)
        try:
            if 'thinking_message' in locals():
                 await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception as inner_e:
            logger.warning(f"Не удалось удалить сообщение 'думаю' после ошибки: {inner_e}")
        await update.message.reply_text(
            f"Бля, {user_name}, все сломалось нахуй в процессе анализа. То ли Гугл меня наебал, то ли я сам криворукий мудак, то ли ваш диалог сломал мне мозг. "
            f"Ошибка типа: `{type(e).__name__}`. Можешь попробовать позже, но я не гарантирую, что это говно починится само."
        )

# --- НОВАЯ АСИНХРОННАЯ ЧАСТЬ (ЗАМЕНЯЕТ FLASK, ПОТОКИ И СТАРУЮ MAIN) ---

# Flask app остается для Render заглушки
app = Flask(__name__)

@app.route('/')
def index():
    """Отвечает на HTTP GET запросы для проверки живости сервиса Render."""
    logger.info("Получен GET запрос на '/', отвечаю OK.")
    return "Я саркастичный бот, и я все еще жив (наверное). Иди нахуй из браузера, пиши в Telegram."

async def run_bot_async(application: Application) -> None:
    """Асинхронная функция для запуска и корректной остановки бота."""
    try:
        logger.info("Инициализация Telegram Application...")
        await application.initialize() # Инициализируем первыми
        if application.updater: # Убедимся что апдейтер создан
            logger.info("Запуск получения обновлений (start_polling)...")
            await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Запуск диспетчера Application (start)...")
        await application.start() # Запускаем обработку
        logger.info("Бот запущен и работает... (ожидание сигнала остановки через idle)")
        # idle() будет ждать сигналов SIGINT, SIGTERM, SIGABRT
        if application.updater:
            await application.updater.idle()
        else: # Если вдруг апдейтера нет (хотя не должно быть с run_polling), просто висим
            while True: await asyncio.sleep(3600)

        logger.info("Получен сигнал остановки (idle завершился).")
    except (KeyboardInterrupt, SystemExit):
        logger.info("Получен KeyboardInterrupt/SystemExit, начинаем остановку.")
    except Exception as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА в run_bot_async: {e}", exc_info=True)
    finally:
        logger.info("Начинаю процесс остановки бота...")
        # Проверяем что application было запущено перед остановкой
        if application.running:
            logger.info("Остановка диспетчера Application (stop)...")
            await application.stop()
        # Проверяем что апдейтер был запущен перед остановкой
        if application.updater and application.updater.running:
            logger.info("Остановка получения обновлений (stop_polling)...")
            await application.updater.stop_polling()
        logger.info("Завершение работы Application (shutdown)...")
        await application.shutdown() # Освобождаем ресурсы
        logger.info("Процесс остановки бота завершен.")


async def main() -> None:
    """Основная асинхронная функция, запускающая веб-сервер и бота."""
    logger.info("Запуск асинхронной функции main().")

    # 1. Настраиваем и собираем Telegram бота
    logger.info("Сборка Telegram Application...")
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("analyze", analyze_chat))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, store_message))
    logger.info("Обработчики Telegram добавлены.")

    # 2. Настраиваем Hypercorn для запуска Flask приложения
    port = int(os.environ.get("PORT", 8080)) # Render передает порт через $PORT
    hypercorn_config = hypercorn.config.Config()
    hypercorn_config.bind = [f"0.0.0.0:{port}"]
    hypercorn_config.worker_class = "asyncio" # Используем asyncio worker
    # Увеличим таймаут отключения, чтобы бот успел корректно остановиться
    hypercorn_config.shutdown_timeout = 60.0
    logger.info(f"Конфигурация Hypercorn: bind={hypercorn_config.bind}, worker={hypercorn_config.worker_class}, shutdown_timeout={hypercorn_config.shutdown_timeout}")

    # 3. Запускаем обе задачи (веб-сервер и бот) конкурентно в одном event loop
    logger.info("Создание и запуск конкурентных задач для Hypercorn и Telegram бота...")

    # Создаем задачи
    # Имя задачи полезно для логов
    bot_task = asyncio.create_task(run_bot_async(application), name="TelegramBotTask")
    # Hypercorn будет обслуживать Flask 'app'
    # Используем 'shutdown_trigger' Hypercorn чтобы он среагировал на сигнал остановки asyncio
    shutdown_event = asyncio.Event()
    server_task = asyncio.create_task(
        hypercorn.serve(app, hypercorn_config, shutdown_trigger=shutdown_event.wait),
        name="HypercornServerTask"
    )

    # Ожидаем завершения ЛЮБОЙ из задач. В норме они должны работать вечно.
    done, pending = await asyncio.wait(
        [bot_task, server_task], return_when=asyncio.FIRST_COMPLETED
    )

    logger.warning(f"Одна из основных задач завершилась! Done: {done}, Pending: {pending}")

    # Сигнализируем Hypercorn'у остановиться, если он еще работает
    if server_task in pending:
        logger.info("Сигнализируем Hypercorn серверу на остановку...")
        shutdown_event.set()

    # Пытаемся вежливо отменить и дождаться завершения оставшихся задач
    logger.info("Отменяем и ожидаем завершения оставшихся задач...")
    for task in pending:
        task.cancel()
    # Даем им шанс завершиться после отмены
    await asyncio.gather(*pending, return_exceptions=True)

    # Проверяем исключения в завершенных задачах
    for task in done:
        logger.info(f"Проверка завершенной задачи: {task.get_name()}")
        try:
            # Если в задаче было исключение, оно поднимется здесь
            await task
        except asyncio.CancelledError:
             logger.info(f"Задача {task.get_name()} была отменена.")
        except Exception as e:
            logger.error(f"Задача {task.get_name()} завершилась с ошибкой: {e}", exc_info=True)

    logger.info("Асинхронная функция main() завершила работу.")


# --- Точка входа в скрипт (ЗАПУСКАЕТ АСИНХРОННУЮ main) ---
if __name__ == "__main__":
    logger.info(f"Скрипт bot.py запущен как основной (__name__ == '__main__').")

    # Создаем .env шаблон, если надо (остается как было)
    if not os.path.exists('.env') and not os.getenv('RENDER'):
        logger.warning("Файл .env не найден...")
        try:
            with open('.env', 'w') as f:
                f.write(f"# Впиши сюда свои реальные ключи!\n")
                f.write(f"TELEGRAM_BOT_TOKEN=7209221587:AAEjoKdYh9uJXkvbvCiTCFdI7rvqkHw135s\n")
                f.write(f"GEMINI_API_KEY=AIzaSyBd4yq48KHH6vraW9ASrwZXLQlqiZx_yKw\n")
            logger.warning("Создан ШАБЛОН файла .env...")
        except Exception as e:
            logger.error(f"Не удалось создать шаблон .env файла: {e}")

    # Проверяем ключи (остается как было)
    if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
        logger.critical("ОТСУТСТВУЮТ КЛЮЧИ TELEGRAM_BOT_TOKEN или GEMINI_API_KEY. Не могу запуститься.")
        exit(1)

    # Запускаем всю эту АСИНХРОННУЮ хуйню через asyncio.run()
    try:
        logger.info("Запускаю asyncio.run(main())...")
        # asyncio.run() автоматически обрабатывает Ctrl+C (SIGINT)
        asyncio.run(main())
        logger.info("asyncio.run(main()) завершен.")
    # Явный перехват KeyboardInterrupt больше не нужен, т.к. asyncio.run и idle() его обрабатывают
    # except KeyboardInterrupt:
    #     logger.info("Получен KeyboardInterrupt (Ctrl+C). Завершаю работу...")
    except Exception as e:
        # Ловим любые другие ошибки на самом верхнем уровне
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА на верхнем уровне выполнения: {e}", exc_info=True)
        exit(1) # Выходим с кодом ошибки
    finally:
         logger.info("Скрипт bot.py завершает работу.")

# --- КОНЕЦ ПОЛНОГО КОДА BOT.PY (ВЕРСИЯ С ASYNCIO + HYPERCORN) ---