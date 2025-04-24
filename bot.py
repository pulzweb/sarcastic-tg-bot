# --- НАЧАЛО ПОЛНОГО КОДА BOT.PY (ВЕРСИЯ С ASYNCIO + HYPERCORN) ---
import logging
import os
import asyncio # ОСНОВА ВСЕЙ АСИНХРОННОЙ МАГИИ
from collections import deque
# УБРАЛИ НАХУЙ THREADING
from flask import Flask # Веб-сервер-заглушка для Render
import hypercorn.config # Конфиг нужен
from hypercorn.asyncio import serve as hypercorn_async_serve # <--- ИМПОРТИРУЕМ ЯВНО И ПЕРЕИМЕНОВЫВАЕМ!
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
        )
        return
    messages_to_analyze = list(chat_histories[chat_id])
    conversation_text = "\n".join(messages_to_analyze)
    logger.info(f"Начинаю анализ {len(messages_to_analyze)} сообщений для чата {chat_id}...")
    try:
        prompt = (
            f"Ты - наблюдательный, язвительный и слегка отстраненный тролль-комментатор Telegram-чата с отличным чувством черного юмора и постиронии. Твоя задача - проанализировать ПОСЛЕДНИЙ фрагмент переписки и выхватить из него несколько (от 1 до 3, если есть!) самых интересных, забавных, нелепых или просто показательных моментов/диалогов/историй.\n\n"
            f"Фрагмент переписки:\n"
            f"```\n{conversation_text}\n```\n\n"
            f"Инструкции для твоего ответа:\n"
            f"1.  Для КАЖДОГО выделенного момента сформулируй **КОРОТКИЙ (1-2 предложения)** комментарий в стиле **постироничного троллинга**. Используй сарказм, неожиданные сравнения, легкую абсурдность и намеки вместо прямых оскорблений. Цель - поддеть, высмеять ситуацию или диалог, а не тупо обосрать участников.\n"
            f"2.  **МАТ ИСПОЛЬЗУЙ**, но тонко, как приправу, для усиления иронии или абсурда, а не для прямого наезда типа 'ты долбоеб'. Фразы типа 'ебать копать', 'охуенно', 'блядь', 'пиздец' - допустимы для выражения эмоций.\n"
            f"3.  **КАЖДЫЙ** комментарий начинай с новой строки и символа **`# `** (хештег и пробел).\n"
            f"4.  Избегай прямых оценок ума ('тупой', 'идиот'). Вместо этого намекай на нелогичность, банальность или нелепость происходящего.\n"
            f"5.  Если в переписке не было НИЧЕГО примечательного, напиши ОДНУ строку в духе: `# Кажется, тут установилась интеллектуальная тишина. Или просто все уснули, хуй пойми.` или `# Зафиксирован обмен любезностями на уровне детского сада. Очень содержательно, блядь.`\n"
            f"6.  Не пиши никаких вступлений. Сразу начинай с первой строки с `# `.\n\n"
            f"Пример хуевого ответа (прямое оскорбление): '# Вася тупой уебок, несет хуйню про Землю.'\n"
            f"Пример ЗАЕБАТОГО ответа (постирония/троллинг): '# Васян, похоже, открыл для себя альтернативную геометрию. Завидую широте его познаний, ебать копать.' ИЛИ '# О, очередная лекция от адепта плоской Земли. Стабильность – признак мастерства, хули.'\n"
            f"Пример хуевого (просто констатация): '# Маша жалуется на бывшего.'\n"
            f"Пример ЗАЕБАТОГО: '# Маша опять практикует сеанс публичной психотерапии про козла-бывшего. Попкорн кто-нибудь заказывал?'\n\n"
            f"Выдай результат в указанном формате, будь тонким, сука, троллем:"
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

# --- НОВАЯ ФУНКЦИЯ ДЛЯ АНАЛИЗА КАРТИНОК ---
async def analyze_pic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Анализирует картинку, на которую ответили командой /analyze_pic."""
    if not update.message or not update.message.reply_to_message:
        await update.message.reply_text("Хули ты мне просто команду пишешь? Ответь ей на сообщение с картинкой, долбоеб!")
        return

    reply_msg = update.message.reply_to_message
    user_name = update.message.from_user.first_name or "Анализатор хуев"

    # Проверяем, есть ли в сообщении, на которое ответили, фотка
    if not reply_msg.photo:
        await update.message.reply_text(f"Слышь, {user_name}, я тут только картинки комментирую, а не твой текстовый высер или ебучий стикер. Ответь на КАРТИНКУ.")
        return

    logger.info(f"Пользователь '{user_name}' запросил анализ картинки в чате {update.message.chat_id}")

    # Берем самую большую версию фотки (обычно последняя в списке)
    photo_large = reply_msg.photo[-1]
    logger.info(f"Получаем файл картинки ID: {photo_large.file_id}")

    try:
        # Скачиваем файл картинки в память (в виде байтов)
        # Ставим таймаут на всякий случай
        photo_file = await context.bot.get_file(photo_large.file_id, read_timeout=60)
        # Нужны байты картинки
        photo_bytes_io = await photo_file.download_as_bytearray(read_timeout=60)
        photo_bytes = bytes(photo_bytes_io) # Конвертируем bytearray в bytes
        logger.info(f"Картинка успешно скачана, размер: {len(photo_bytes)} байт.")

        # Готовим ПРАВИЛЬНЫЙ промпт для КАРТИНКИ
        image_prompt = (
            f"Ты - слегка упоротый арт-критик с замашками тролля и любовью к постиронии. Тебе на обзор прислали КАРТИНКУ. Твоя задача - рассмотреть ее и выдать **КОРОТКИЙ (1-3 предложения)**, остроумный и ироничный комментарий. \n\n"
            f"Инструкции:\n"
            f"1.  Найди в изображении что-то забавное, нелепое, странное или просто бросающееся в глаза.\n"
            f"2.  Сформулируй комментарий с **сарказмом, иронией или легким абсурдом**. Можешь использовать неожиданные сравнения или задавать риторические вопросы.\n"
            f"3.  **МАТ используй умеренно**, для добавления экспрессии или комического эффекта, а не для тупого обсирания ('блядь', 'ебать', 'охуенно'). Не оскорбляй напрямую автора или изображенное, если это не выглядит очевидно смешным само по себе.\n"
            f"4.  Не пиши банальностей типа 'На картинке мы видим...'. Сразу переходи к сути своего ироничного наблюдения.\n"
            f"5.  Цель - не уничтожить, а тонко подколоть, вызвать улыбку (или недоумение) у читателя.\n\n"
            f"Пример хуевого ответа (тупо обсирание): '# Кот - уебище, снято на тапок.'\n"
            f"Пример ЗАЕБАТОГО ответа (ирония): '# Какой экзистенциальный взгляд у этого кота! Кажется, он только что осознал тщетность бытия. Или просто хочет жрать, хуй пойми.'\n"
            f"Пример (пейзаж): '# Бля, какая величественная гора... Интересно, вайфай там ловит?' ИЛИ '# Охуенный закат. Наверное, фоткали, пока шашлык горел.'\n"
            f"Пример (абстракция): '# Ебать, глубокомысленно. Чувствую в этих кляксах всю боль современного общества. Или это просто обои такие?'\n\n"
            f"КОРОЧЕ! Посмотри на картинку и выдай свой остроумный (надеюсь) вердикт:"
        )

        # Сообщение "Думаю..."
        thinking_message = await update.message.reply_text("Так-так, блядь, ща посмотрим на это произведение искусства... Дайте подумать (или просто подождите, картинки дольше грузятся)...")

        # Отправляем запрос в Gemini С КАРТИНКОЙ
        logger.info("Отправка запроса к Gemini с картинкой...")
        # Gemini принимает список "частей": текст и данные картинки
        response = await model.generate_content_async([image_prompt, {"mime_type": "image/jpeg", "data": photo_bytes}])
        # ЗАМЕЧАНИЕ: Мы тупо ставим mime_type "image/jpeg". Если прислали PNG или другую хуйню,
        # Gemini может не понять или обработать криво. Для простоты пока забьем.
        logger.info("Получен ответ от Gemini по картинке.")

        # Удаляем "Думаю..."
        try: await context.bot.delete_message(chat_id=update.message.chat_id, message_id=thinking_message.message_id)
        except Exception: pass

        # Отправляем ответ
        sarcastic_comment = "Хуй знает, что там нарисовано, но выглядит как говно. Или Gemini не смог это переварить."
        if response and response.text:
            sarcastic_comment = response.text.strip()
        await update.message.reply_text(sarcastic_comment)
        logger.info(f"Отправлен комментарий к картинке: '{sarcastic_comment[:50]}...'")

    except Exception as e:
        logger.error(f"ПИЗДЕЦ при анализе картинки: {e}", exc_info=True)
        try:
            if 'thinking_message' in locals(): await context.bot.delete_message(chat_id=update.message.chat_id, message_id=thinking_message.message_id)
        except Exception: pass
        await update.message.reply_text(f"Бля, {user_name}, я обосрался, пока смотрел на эту картинку. То ли она слишком уебищная, то ли Гугл опять барахлит. Ошибка: `{type(e).__name__}`.")

# --- КОНЕЦ НОВОЙ ФУНКЦИИ ---

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
        await application.initialize() # Инициализируем
        if not application.updater:
             logger.critical("Updater не был создан в Application. Не могу запустить polling.")
             return
        logger.info("Запуск получения обновлений (start_polling)...")
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES) # Запускаем polling
        logger.info("Запуск диспетчера Application (start)...")
        await application.start() # Запускаем обработку апдейтов
        logger.info("Бот запущен и работает... (ожидание отмены или сигнала)")
        # --->>> Заменяем idle() на ожидание Future <<<---
        await asyncio.Future()
        logger.info("Ожидание Future завершилось (не должно было без отмены).")
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        logger.info("Получен сигнал остановки (KeyboardInterrupt/SystemExit/CancelledError).")
    except Exception as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА в run_bot_async во время работы: {e}", exc_info=True)
    finally:
        logger.info("Начинаю процесс ОСТАНОВКИ бота в run_bot_async...")
        if application.running:
            logger.info("Остановка диспетчера Application (stop)...")
            await application.stop()
            logger.info("Диспетчер Application остановлен.")
        if application.updater and application.updater.is_running:
            logger.info("Остановка получения обновлений (updater.stop)...")
            # --->>> Заменяем stop_polling() -> stop() <<<---
            await application.updater.stop()
            logger.info("Получение обновлений (updater) остановлено.")
        logger.info("Завершение работы Application (shutdown)...")
        await application.shutdown()
        logger.info("Процесс остановки бота в run_bot_async завершен.")


async def main() -> None:
    """Основная асинхронная функция, запускающая веб-сервер и бота."""
    logger.info("Запуск асинхронной функции main().")

    # 1. Настраиваем и собираем Telegram бота
    logger.info("Сборка Telegram Application...")
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("analyze", analyze_chat))
    application.add_handler(CommandHandler("analyze_pic", analyze_pic))
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
        hypercorn_async_serve(app, hypercorn_config, shutdown_trigger=shutdown_event.wait),
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