from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pymongo import MongoClient
import google.generativeai as genai
import requests
from datetime import datetime

# Singleton MongoDB connection
class MongoDBConnection:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBConnection, cls).__new__(cls)
            cls._instance.client = MongoClient('mongodb://localhost:27017/')
            cls._instance.db = cls._instance.client['Telegram_Bot']  # Ensure this matches the existing database name
        return cls._instance

# Use the singleton connection
mongo_connection = MongoDBConnection()
db = mongo_connection.db
users_collection = db['users']
chats_collection = db['chats']
files_collection = db['files']

# Gemini API setup
genai.configure(api_key='AIzaSyBSZ1pQbTmi-lndKbSycUeguiecnvX2cH8')
model = genai.GenerativeModel('gemini-pro')

# Telegram Bot Token
TOKEN = '7623560646:AAHdr6C4c1Jk-KlvI5bF0-pB3p8AbSJgZhI'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = {
        'first_name': user.first_name,
        'username': user.username,
        'chat_id': user.id,
        'phone_number': None
    }
    users_collection.update_one({'chat_id': user.id}, {'$set': user_data}, upsert=True)
    await update.message.reply_text('Please share your contact details using the contact button.')

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    phone_number = update.message.contact.phone_number
    users_collection.update_one({'chat_id': user.id}, {'$set': {'phone_number': phone_number}})
    await update.message.reply_text('Thank you for sharing your contact details!')

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    response = model.generate_content(user_input)
    chat_data = {
        'chat_id': update.effective_chat.id,
        'user_input': user_input,
        'bot_response': response.text,
        'timestamp': datetime.now()
    }
    chats_collection.insert_one(chat_data)
    await update.message.reply_text(response.text)

async def analyze_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.photo[-1].get_file()
    file_path = f"downloads/{file.file_id}.jpg"
    await file.download_to_drive(file_path)
    description = model.generate_content(f"Describe this image: {file_path}")
    file_data = {
        'chat_id': update.effective_chat.id,
        'filename': file_path,
        'description': description.text,
        'timestamp': datetime.now()
    }
    files_collection.insert_one(file_data)
    await update.message.reply_text(description.text)

async def web_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = ' '.join(context.args)
    search_url = f"https://api.duckduckgo.com/?q={query}&format=json"
    response = requests.get(search_url).json()
    summary = model.generate_content(f"Summarize this: {response['AbstractText']}")
    await update.message.reply_text(f"{summary.text}\n\nMore info: {response['AbstractURL']}")

async def sentiment_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ' '.join(context.args)
    sentiment = model.generate_content(f"Analyze the sentiment of this text: {text}")
    await update.message.reply_text(sentiment.text)

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.CONTACT, contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    application.add_handler(MessageHandler(filters.PHOTO, analyze_image))
    application.add_handler(CommandHandler("websearch", web_search))
    application.add_handler(CommandHandler("sentiment", sentiment_analysis))
    application.run_polling()

if __name__ == '__main__':
    main()