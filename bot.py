from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pymongo import MongoClient
import google.generativeai as genai
import requests
from datetime import datetime
import os
from langchain_community.tools import DuckDuckGoSearchRun
from PIL import Image
import PyPDF2
from io import BytesIO

# Singleton MongoDB connection
class MongoDBConnection:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBConnection, cls).__new__(cls)
            cls._instance.client = MongoClient('mongodb://localhost:27017/')
            cls._instance.db = cls._instance.client['Telegram_Bot']
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

# Ensure the downloads directory exists
if not os.path.exists('downloads'):
    os.makedirs('downloads')

# Request Phone Number Button
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = {
        'first_name': user.first_name,
        'username': user.username,
        'chat_id': user.id,
        'phone_number': None,
        'referral_code': None
    }
    users_collection.update_one({'chat_id': user.id}, {'$set': user_data}, upsert=True)
    
    # Create a keyboard with a "Share Contact" button
    contact_button = KeyboardButton(text="Share Contact", request_contact=True)
    reply_markup = ReplyKeyboardMarkup([[contact_button]], one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        'Welcome! Please share your contact details using the button below.',
        reply_markup=reply_markup
    )

# Handle Contact Sharing
async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    phone_number = update.message.contact.phone_number
    users_collection.update_one({'chat_id': user.id}, {'$set': {'phone_number': phone_number}})
    await update.message.reply_text('Thank you for sharing your contact details!')

# Handle Text Messages (Gemini Chat)
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    try:
        response = model.generate_content(user_input)
        chat_data = {
            'chat_id': update.effective_chat.id,
            'user_input': user_input,
            'bot_response': response.text,
            'timestamp': datetime.now()
        }
        chats_collection.insert_one(chat_data)
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")

# Handle Image/File Uploads
async def analyze_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.document:
            file = await update.message.document.get_file()
            file_extension = update.message.document.file_name.split('.')[-1].lower()
        elif update.message.photo:
            file = await update.message.photo[-1].get_file()
            file_extension = 'jpg'
        else:
            await update.message.reply_text("Unsupported file type.")
            return

        file_path = f"downloads/{file.file_id}.{file_extension}"
        await file.download_to_drive(file_path)

        if file_extension in ['jpg', 'jpeg', 'png']:
            # Open and process the image
            with Image.open(file_path) as img:
                img_description = "This is an image."
                # You can add more image processing logic here
            description = model.generate_content(f"Describe this image: {img_description}")
        elif file_extension == 'pdf':
            # Extract text from PDF
            with open(file_path, 'rb') as pdf_file:
                reader = PyPDF2.PdfReader(pdf_file)
                text = ''.join([page.extract_text() for page in reader.pages])
            description = model.generate_content(f"Summarize the content of this PDF: {text}")
        else:
            await update.message.reply_text("Unsupported file type.")
            return

        file_data = {
            'chat_id': update.effective_chat.id,
            'filename': file_path,
            'description': description.text,
            'timestamp': datetime.now()
        }
        files_collection.insert_one(file_data)
        await update.message.reply_text(description.text)
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")

# Web Search with AI Agent (LangChain)
async def web_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = ' '.join(context.args).strip()
    if not query:
        await update.message.reply_text("Please provide a search query. Usage: /websearch <query>")
        return

    try:
        search_tool = DuckDuckGoSearchRun()
        search_results = search_tool.run(query)
        summary = model.generate_content(f"Summarize this: {search_results}")
        await update.message.reply_text(f"{summary.text}\n\nMore info: {search_results}")
    except Exception as e:
        await update.message.reply_text(f"An error occurred during the search: {str(e)}")

# Bonus Feature: Referral System
async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referral_code = context.args[0] if context.args else None

    if referral_code:
        users_collection.update_one({'chat_id': user.id}, {'$set': {'referral_code': referral_code}})
        await update.message.reply_text(f"Thank you for using referral code: {referral_code}")
    else:
        await update.message.reply_text("Please provide a referral code. Usage: /referral <code>")

# Main Function
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.CONTACT, contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, analyze_file))
    application.add_handler(CommandHandler("websearch", web_search))
    application.add_handler(CommandHandler("referral", referral))
    application.run_polling()

if __name__ == '__main__':
    main()