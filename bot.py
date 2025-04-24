# --- НАЧАЛО ПОЛНОГО КОДА ДЛЯ BOT.PY ---
import logging
import os
import asyncio
from collections import deque
from threading import Thread # Для запуска бота в отдельном потоке, чтоб не мешал веб-серверу
from flask import Flask # Сам веб-сервер-заглушка для Render

import google.generativeai as genai
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv # Чтобы читать твой сраный .env файл (или переменные Render)

# Загружаем секреты из файла .env (если он есть в папке) ИЛИ из переменных окружения Render
load_dotenv()

# --- НАСТРОЙКИ (твои ключи и прочая хуета) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Максимальное количество сообщений для анализа (от 10 до 1000, блядь, как ты и просил)
# Ставь поменьше (30-100), если не хочешь разорить Google на запросах или долго ждать ответа
MAX_MESSAGES_TO_ANALYZE = 50 # Можешь поменять, если не ссышь последствий

# Проверка, что ключи ты, сука, указал!
if not TELEGRAM_BOT_TOKEN:
    # Эта ошибка остановит запуск, если токена нет. И ПРАВИЛЬНО СДЕЛАЕТ!
    raise ValueError("НЕ НАЙДЕН TELEGRAM_BOT_TOKEN, долбоеб! Проверь .env файл или переменные окружения на Render.")
if not GEMINI_API_KEY:
    raise ValueError("НЕ НАЙДЕН GEMINI_API_KEY, кретин! Проверь .env файл или переменные окружения на Render.")

# Настройка логирования, чтобы хоть что-то понимать, когда все пойдет по пизде
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# Уменьшаем спам от библиотеки HTTP-запросов, которая под капотом у телеги и гугла
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Настройка Gemini API (гугло-мозга, который будет за тебя язвить)
try:
    genai.configure(api_key=GEMINI_API_KEY)
    # Используем модель побыстрее и подешевле ('flash'), а то денег у тебя нет
    model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("Модель Gemini успешно настроена.")
except Exception as e:
    logger.critical(f"ПИЗДЕЦ при настройке Gemini API: {e}", exc_info=True)
    # Если даже модель не можем настроить, дальше смысла нет работать
    raise SystemExit(f"Не удалось настроить Gemini API: {e}")

# Глобальный словарь для хранения истории высеров по чатам
# Ключ - chat_id, значение - deque (очередь) с сообщениями
chat_histories = {}
logger.info(f"Максимальная длина истории сообщений для анализа: {MAX_MESSAGES_TO_ANALYZE}")

# Функция для обработки обычных сообщений (сохраняем этот бред в память)
async def store_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Проверяем, что сообщение вообще есть и оно текстовое и от пользователя
    if not update.message or not update.message.text or not update.message.from_user:
        # logger.debug("Игнорируем нетекстовое или системное сообщение")
        return # Игнорим всякую хуйню без текста или от непонятно кого

    chat_id = update.message.chat_id
    message_text = update.message.text
    user_name = update.message.from_user.first_name or "Анонимный долбоеб" # На случай, если имени нет

    # Создаем очередь для чата, если ее еще нет
    if chat_id not in chat_histories:
        # deque - охуенная штука, сама выкидывает старое говно при добавлении нового
        chat_histories[chat_id] = deque(maxlen=MAX_MESSAGES_TO_ANALYZE)
        logger.info(f"Создана новая история для чата {chat_id}")

    # Добавляем сообщение в формате "Имя: Текст" в историю чата
    chat_histories[chat_id].append(f"{user_name}: {message_text}")
    # Закомментил логирование каждого сообщения, а то засрет все логи нахуй
    # logger.debug(f"Сохранено сообщение от {user_name} в чате {chat_id}. Размер истории: {len(chat_histories[chat_id])}")

# Функция для команды /analyze (главная функция - обосрать чат)
async def analyze_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Проверяем наличие сообщения и пользователя
    if not update.message or not update.message.from_user:
        logger.warning("Получена команда /analyze без необходимой информации. Игнорируем.")
        return

    chat_id = update.message.chat_id
    user_name = update.message.from_user.first_name or "Эй ты там" # Обращение к вызвавшему

    logger.info(f"Пользователь '{user_name}' (ID: {update.message.from_user.id}) запросил анализ в чате {chat_id}")

    # Проверяем, накопился ли хоть какой-то пиздеж для анализа
    if chat_id not in chat_histories or len(chat_histories[chat_id]) < 10: # Минимальный порог сообщений
        min_msgs = 10 # Можно вынести в константу, если не лень
        history_len = len(chat_histories.get(chat_id, []))
        logger.info(f"В чате {chat_id} слишком мало сообщений ({history_len}/{min_msgs}) для анализа.")
        await update.message.reply_text(
            f"Слышь, {user_name}, ты заебал. Я тут недавно (или вы молчали как рыбы), сообщений кот наплакал "
            f"(всего {history_len} штук в моей памяти, а надо хотя бы {min_msgs}).\n"
            f"Попиздите еще хотя бы немного, потом посмотрим на ваш балаган.\n"
            f"(Или я просто просыпаюсь после спячки Render, подожди секунд 30 и попробуй еще раз, нетерпеливый уебок)."
        )
        return

    # Получаем последние сообщения из нашей сохраненной истории
    # Копируем в список, чтобы не менять deque во время итерации (на всякий случай)
    messages_to_analyze = list(chat_histories[chat_id])
    conversation_text = "\n".join(messages_to_analyze)
    logger.info(f"Начинаю анализ {len(messages_to_analyze)} сообщений для чата {chat_id}...")

    # Отправляем запрос к Gemini
    try:
        # Составляем ПРОМПТ (инструкцию) для нейросети. Тут вся магия сарказма и мата!
        # МОЖЕШЬ МЕНЯТЬ ЭТОТ ПРОМПТ, ЕСЛИ ХОЧЕШЬ ДРУГОЙ СТИЛЬ ОТВЕТОВ!!!
        prompt = (
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

        # Показываем пользователю, что мы типа думаем (это занимает время, особенно после сна на Render)
        # Сохраняем сообщение, чтобы потом удалить
        thinking_message = await update.message.reply_text("Так, блядь, щас напрягу свои кремниевые мозги и попробую понять смысл вашего высокоинтеллектуального бреда... Не мешайте, я в процессе (или тупо сплю, хуй знает)...")
        logger.debug(f"Отправил сообщение 'думаю' (ID: {thinking_message.message_id}) в чат {chat_id}")

        # Асинхронный запрос к модели, чтобы не блокировать все нахуй пока она там думает
        logger.info(f"Отправляю запрос к Gemini для чата {chat_id}...")
        response = await model.generate_content_async(prompt)
        logger.info(f"Получен ответ от Gemini для чата {chat_id}")

        # Убираем нахуй сообщение "думаю" - оно свою роль сыграло
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
            logger.debug(f"Удалил сообщение 'думаю' (ID: {thinking_message.message_id}) в чате {chat_id}")
        except Exception as delete_err:
            # Похуй, если не удалилось, не критично
            logger.warning(f"Не смог удалить сообщение 'думаю' (ID: {thinking_message.message_id}) в чате {chat_id}: {delete_err}")

        # Обрабатываем ответ от Gemini
        sarcastic_summary = "Бля, хуйню какую-то нейронка выдала или вообще пустой ответ. Видимо, ваш треп настолько бессмысленный, что даже ИИ повесился."
        if response and response.text:
             sarcastic_summary = response.text.strip()

        # Отправляем результат анализа (или сообщение об ошибке, если нейронка сдохла)
        await update.message.reply_text(sarcastic_summary)
        logger.info(f"Отправил результат анализа '{sarcastic_summary[:50]}...' в чат {chat_id}")

    except Exception as e:
        logger.error(f"ПИЗДЕЦ при выполнении анализа для чата {chat_id}: {e}", exc_info=True)
        # Пытаемся удалить сообщение "думаю" даже если была ошибка
        try:
            if 'thinking_message' in locals(): # Проверяем, успели ли создать переменную
                 await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except Exception as inner_e:
            logger.warning(f"Не удалось удалить сообщение 'думаю' после ошибки: {inner_e}")

        # Сообщаем пользователю, что все пошло по пизде
        await update.message.reply_text(
            f"Бля, {user_name}, все сломалось нахуй в процессе анализа. То ли Гугл меня наебал, то ли я сам криворукий мудак, то ли ваш диалог сломал мне мозг. "
            f"Ошибка типа: `{type(e).__name__}`. Можешь попробовать позже, но я не гарантирую, что это говно починится само."
        )

# --- Создаем Flask приложение (веб-сервер-заглушка для Render) ---
# Это нужно, чтобы Render считал сервис рабочим и не убивал его сразу (хотя он все равно будет засыпать)
app = Flask(__name__)

@app.route('/') # Отвечаем на запросы к корневому URL /
def index():
    """Эта функция будет вызываться, когда Render проверяет жив ли сервис."""
    logger.info("Получен GET запрос на '/', отвечаю OK.")
    # Можно вернуть что угодно, главное статус 200 OK
    return "Я саркастичный бот, и я типа работаю (на костылях Render). Отъебись и иди в Telegram, тут смотреть нехуй."

# --- Функция для запуска основного цикла Telegram бота в отдельном потоке ---
def run_telegram_bot():
    """Эта функция запускает бесконечный цикл опроса Telegram API."""
    logger.info("Попытка создания и запуска Telegram Bot Application в отдельном потоке...")
    try:
        # Собираем приложение бота со всеми обработчиками
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        # Добавляем обработчик команды /analyze
        application.add_handler(CommandHandler("analyze", analyze_chat))
        # Добавляем обработчик ВСЕХ текстовых сообщений (КРОМЕ команд), чтобы сохранять их
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, store_message))

        logger.info("Запускаю application.run_polling() (это блокирующая операция)...")
        # Запускаем polling - это БЛОКИРУЮЩАЯ операция,
        # она будет выполняться в этом потоке, пока ее принудительно не остановят
        application.run_polling(allowed_updates=Update.ALL_TYPES) # Принимаем все типы апдейтов

        # Сюда код дойдет только при штатной остановке бота (Ctrl+C или сигнал)
        logger.info("Telegram бот application.run_polling() штатно завершен.")

    except Exception as e:
        # Логируем критическую ошибку, если весь цикл бота упал
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА в основном цикле Telegram бота: {e}", exc_info=True)
        # Тут можно было бы добавить механизм перезапуска, но для тебя, дебил, и так сойдет.
        # Просто смотри логи на Render, если бот перестанет отвечать.

# --- Основная функция main (ЗАПУСКАЕТ ВСЕ НАХУЙ) ---
def main() -> None:
    """Запускает Flask веб-сервер (для Render) и Telegram бота (в отдельном потоке)."""

    logger.info("Запуск основной функции main().")

    # 1. Запускаем Telegram бота в ОТДЕЛЬНОМ ПОТОКЕ
    # Это важно, чтобы он не блокировал основной поток, где будет работать веб-сервер Flask
    logger.info("Создание и запуск потока для Telegram бота...")
    # daemon=True означает, что этот поток умрет автоматически, когда умрет основной поток (Flask)
    telegram_thread = Thread(target=run_telegram_bot, daemon=True)
    telegram_thread.start()
    if telegram_thread.is_alive():
        logger.info(f"Поток Telegram бота успешно запущен (ID потока: {telegram_thread.ident}).")
    else:
        logger.error("НЕ УДАЛОСЬ ЗАПУСТИТЬ ПОТОК TELEGRAM БОТА!")
        # Можно тут выйти, раз бот не запустился, но Flask все равно попробует стартануть
        # raise SystemExit("Не удалось запустить поток бота.")


    # 2. Запускаем Flask веб-сервер в ЭТОМ (главном) потоке
    # Он будет слушать HTTP запросы, чтобы Render был доволен
    # Render сам передаст нужный порт через переменную окружения PORT
    # Используем 8080 по умолчанию, если запускаем локально и PORT не задан
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Запуск Flask веб-сервера на хосте 0.0.0.0 и порту {port}...")
    # Важно слушать на 0.0.0.0, чтобы Render мог достучаться до сервера извне контейнера
    # debug=False ОБЯЗАТЕЛЬНО на продакшене (на Render), чтобы не было уязвимостей и лишнего говна в логах
    # use_reloader=False тоже важно, чтобы Flask не пытался сам перезапускаться при изменениях кода
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

    # Сюда код дойдет только если Flask сервер по какой-то причине остановится (что не должно произойти штатно)
    logger.info("Flask веб-сервер остановлен.")

# --- Точка входа в скрипт (запускается при выполнении python bot.py) ---
if __name__ == "__main__":
    logger.info(f"Скрипт bot.py запущен как основной (__name__ == '__main__').")

    # Создаем файл .env ШАБЛОН, если его нет И мы НЕ на Render
    # Это нужно только для удобства локального запуска, чтобы ты, долбоеб, не забыл про ключи
    # На Render ключи берутся из Environment Variables, которые ты настраивал в интерфейсе Render
    if not os.path.exists('.env') and not os.getenv('RENDER'): # 'RENDER' - это переменная, которую Render обычно ставит
        logger.warning("Файл .env не найден и мы не на Render. Создаю ШАБЛОН .env...")
        try:
            with open('.env', 'w') as f:
                f.write(f"# Впиши сюда свои реальные ключи!\n")
                f.write(f"TELEGRAM_BOT_TOKEN=7209221587:AAEjoKdYh9uJXkvbvCiTCFdI7rvqkHw135s\n")
                f.write(f"GEMINI_API_KEY=AIzaSyBd4yq48KHH6vraW9ASrwZXLQlqiZx_yKw\n")
            logger.warning("Создан ШАБЛОН файла .env. НЕ ЗАБУДЬ ВПИСАТЬ ТУДА СВОИ КЛЮЧИ ПЕРЕД ЛОКАЛЬНЫМ ЗАПУСКОМ!")
            # Можно раскомментить exit(), чтобы скрипт остановился, пока ты не впишешь ключи локально
            # logger.info("Останавливаю скрипт, чтобы ты мог заполнить .env")
            # exit()
        except Exception as e:
            logger.error(f"Пиздец! Не удалось создать шаблон .env файла: {e}")

    # Проверяем наличие ключей еще раз перед запуском main()
    if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
        logger.critical("ОТСУТСТВУЮТ КЛЮЧИ TELEGRAM_BOT_TOKEN или GEMINI_API_KEY. Не могу запуститься.")
        exit(1) # Выходим с ошибкой

    # Запускаем всю эту хуйню через функцию main()
    main()

# --- КОНЕЦ ПОЛНОГО КОДА ДЛЯ BOT.PY ---