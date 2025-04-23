import logging
import os
import asyncio
from collections import deque # Для хранения последних сообщений

import google.generativeai as genai
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Загружаем секреты из файла .env (если он есть)
load_dotenv()

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Максимальное количество сообщений для анализа (от 10 до 1000, как ты хотел)
MAX_MESSAGES_TO_ANALYZE = 50 # Можешь поменять это число, но помни про лимиты API и здравый смысл
# --- КОНЕЦ НАСТРОЕК ---

# Проверка, что ключи загружены
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Не найден TELEGRAM_BOT_TOKEN. Проверь .env файл или переменные окружения.")
if not GEMINI_API_KEY:
    raise ValueError("Не найден GEMINI_API_KEY. Проверь .env файл или переменные окружения.")

# Настройка логирования, чтобы видеть, что бот делает (или почему сдох)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING) # Меньше спама от библиотеки запросов
logger = logging.getLogger(__name__)

# Настройка Gemini API
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash') # Используем быструю и дешевую модель

# Глобальный словарь для хранения истории сообщений по чатам
# Ключ - chat_id, значение - deque (очередь) с сообщениями
chat_histories = {}

# Функция для обработки обычных сообщений (сохраняем их)
async def store_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    message_text = update.message.text

    if not message_text: # Игнорим фотки, стикеры и прочую хуйню
        return

    if chat_id not in chat_histories:
        # deque - это как список, но эффективно удаляет старые элементы при добавлении новых
        chat_histories[chat_id] = deque(maxlen=MAX_MESSAGES_TO_ANALYZE)

    # Добавляем сообщение в формате "Имя: Текст"
    user_name = update.message.from_user.first_name
    chat_histories[chat_id].append(f"{user_name}: {message_text}")
    # logger.info(f"Stored message from {user_name} in chat {chat_id}. History size: {len(chat_histories[chat_id])}")

# Функция для команды /analyze (или как ты ее назовешь)
async def analyze_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    user_name = update.message.from_user.first_name

    logger.info(f"User {user_name} requested analysis in chat {chat_id}")

    if chat_id not in chat_histories or len(chat_histories[chat_id]) < 10: # Минимальный порог сообщений для анализа
        await update.message.reply_text(
            f"Слышь, {user_name}, я тут недавно, сообщений кот наплакал (меньше 10). "
            f"Попиздите еще, потом проанализирую ваш балаган. Или я просто еще не все загрузил, подожди пару сек."
        )
        return

    # Получаем последние сообщения из нашей сохраненной истории
    messages_to_analyze = list(chat_histories[chat_id]) # Копируем в список
    conversation_text = "\n".join(messages_to_analyze)

    # Отправляем запрос к Gemini
    try:
        # Составляем ПРОМПТ (инструкцию) для нейросети. Тут вся магия сарказма и мата!
        prompt = (
            f"Проанализируй следующий фрагмент переписки из Telegram-чата:\n\n"
            f"```\n{conversation_text}\n```\n\n"
            f"Твоя задача:\n"
            f"1. Выдели самую суть, главную тему или итог этого обсуждения.\n"
            f"2. Сформулируй этот итог **МАКСИМАЛЬНО САРКАСТИЧНО И ЯЗВИТЕЛЬНО**. Используй нецензурную лексику (мат), но в меру, чтобы было смешно, а не тупо. Будь дерзким и ехидным.\n"
            f"3. Ответ должен быть коротким, 1-3 предложения. Не пиши приветствий или вступлений, сразу выдавай саркастичный итог.\n\n"
            f"Пример херового ответа: 'Пользователи обсуждали погоду'.\n"
            f"Пример охуенного ответа: 'Похоже, эти долбоебы опять ноют про погоду, как будто от их пиздежа что-то изменится. Мда.'\n\n"
            f"Выдай результат:"
        )

        # Показываем пользователю, что мы думаем (это занимает время)
        thinking_message = await update.message.reply_text("Так, блядь, щас подумаю над вашим бредом...")

        response = await model.generate_content_async(prompt) # Асинхронный запрос

        # Удаляем сообщение "думаю"
        await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)

        # Отправляем результат
        sarcastic_summary = response.text
        await update.message.reply_text(sarcastic_summary)
        logger.info(f"Sent analysis result to chat {chat_id}")

    except Exception as e:
        logger.error(f"Ошибка при анализе чата {chat_id}: {e}", exc_info=True)
        try:
            # Попытка удалить сообщение "думаю", если произошла ошибка
            await context.bot.delete_message(chat_id=chat_id, message_id=thinking_message.message_id)
        except:
            pass # Похуй, если не удалилось
        await update.message.reply_text(
            f"Бля, че-то пошло не так. То ли Гугл охуел, то ли я рукожоп. "
            f"Ошибка: {e}. Попробуй позже, может пройдет."
        )

# Основная функция запуска бота
def main() -> None:
    """Запускаем бота."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Добавляем обработчик команды /analyze
    application.add_handler(CommandHandler("analyze", analyze_chat)) # Можешь поменять команду на /sumiruy или /obosri

    # Добавляем обработчик всех текстовых сообщений для сохранения истории
    # Важно: он должен быть ПОСЛЕ обработчика команд, чтобы команды не сохранялись как обычный текст
    # `~filters.COMMAND` - игнорирует команды
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, store_message))

    logger.info("Бот запускается...")
    # Запускаем бота (он будет работать, пока не остановишь принудительно - Ctrl+C)
    application.run_polling()

if __name__ == "__main__":
    # Создаем файл .env, если его нет, чтобы ты не забыл про ключи
    if not os.path.exists('.env'):
        with open('.env', 'w') as f:
            f.write("TELEGRAM_BOT_TOKEN=ТВОЙ_ТОКЕН_СЮДА\n")
            f.write("GEMINI_API_KEY=ТВОЙ_API_КЛЮЧ_GEMINI_СЮДА\n")
        logger.warning("Создан файл .env. Не забудь вписать туда свои ключи!")
        # exit() # Можно раскомментить, чтобы скрипт остановился, пока ты не впишешь ключи

    main()