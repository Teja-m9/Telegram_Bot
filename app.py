import logging
from telegram import Update, ForceReply
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackContext
from pymongo import MongoClient
import requests

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB Setup (use your connection string here)
client = MongoClient("mongodb://localhost:27017/")  # Ensure MongoDB is running locally, or replace with your MongoDB Atlas connection string
db = client['Chatbot_db']  # Use your database name
user_details_collection = db['user_details']  # Use your collection name
chat_history_collection = db['chat_history']  # Collection for saving chat history
files_collection = db['files_metadata']  # Collection for saving file metadata

# Telegram bot setup
TOKEN = '7623560646:AAHdr6C4c1Jk-KlvI5bF0-pB3p8AbSJgZhI'
GEMINI_API_KEY = 'AIzaSyBSZ1pQbTmi-lndKbSycUeguiecnvX2cH8'

# Conversation States
FIRST_NAME, PHONE_NUMBER = range(2)

# Start Command - User registration
async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat_id = user.id

    # Check if the user already exists in MongoDB
    existing_user = user_details_collection.find_one({"chat_id": chat_id})
    if not existing_user:
        # New user, ask for phone number after capturing first name
        await update.message.reply_text(
            f"Welcome {user.first_name}, please share your phone number to complete registration.",
            reply_markup=ForceReply(selective=True)
        )
        user_details_collection.insert_one({
            "chat_id": chat_id,
            "first_name": user.first_name,
            "username": user.username,
            "phone_number": None
        })
        return FIRST_NAME
    else:
        # Greet existing user
        await update.message.reply_text(f"Welcome back, {user.first_name}!")
        return ConversationHandler.END

# Register phone number
async def register_phone(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat_id = user.id
    phone_number = update.message.contact.phone_number

    # Update phone number in MongoDB
    user_details_collection.update_one({"chat_id": chat_id}, {"$set": {"phone_number": phone_number}})

    await update.message.reply_text(f"Thank you for sharing your phone number, {user.first_name}!")
    return ConversationHandler.END

# Handle user queries
async def handle_message(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat_id = user.id
    user_input = update.message.text

    # Call Gemini API to generate a response
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
        json={"contents": [{"parts": [{"text": user_input}]}]}
    )
    
    # Get the generated text
    bot_response = response.json().get('candidates')[0].get('content').get('parts')[0].get('text')

    # Save chat history
    chat_history_collection.insert_one({
        "chat_id": chat_id,
        "user_input": user_input,
        "bot_response": bot_response,
        "timestamp": update.message.date
    })

    # Send the response to the user
    await update.message.reply_text(bot_response)

# Handle images/files and analyze them
async def handle_files(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat_id = user.id
    file = update.message.document or update.message.photo[-1]

    # Download the file
    file_id = file.file_id
    file_path = (await context.bot.get_file(file_id)).file_path
    file_name = file.file_name or "image.jpg"
    
    # Send file metadata to MongoDB
    files_collection.insert_one({
        "chat_id": chat_id,
        "file_name": file_name,
        "file_url": file_path,
        "timestamp": update.message.date
    })

    # Use Gemini to analyze the content
    file_response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
        json={"contents": [{"parts": [{"text": f"Describe the content of the file: {file_name}"}]}]}
    )

    # Get the analysis result
    analysis_result = file_response.json().get('candidates')[0].get('content').get('parts')[0].get('text')

    # Reply with the analysis result
    await update.message.reply_text(f"File analysis result: {analysis_result}")

# Handle web search
async def web_search(update: Update, context: CallbackContext) -> None:
    query = ' '.join(context.args)
    if not query:
        await update.message.reply_text("Please provide a search query after the /websearch command.")
        return

    # Perform web search (simplified for demonstration)
    search_response = requests.get(f"https://api.duckduckgo.com/?q={query}&format=json")
    search_results = search_response.json()

    # Get the top search results
    search_summary = search_results.get("AbstractText", "No relevant summary found.")
    search_links = [result["FirstURL"] for result in search_results.get("RelatedTopics", [])]

    # Send the results to the user
    await update.message.reply_text(f"Search results for '{query}':\n\n{search_summary}\n\nTop Links:\n" + "\n".join(search_links))

# Main function to set up the bot
def main() -> None:
    application = Application.builder().token(TOKEN).build()

    # Define conversation handler for registration
    conversation_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_phone)],
        },
        fallbacks=[],
    )

    application.add_handler(conversation_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO | filters.DOCUMENT, handle_files))
    application.add_handler(CommandHandler('websearch', web_search))

    # Run the bot
    application.run_polling()

if __name__ == '__main__':
    main()
