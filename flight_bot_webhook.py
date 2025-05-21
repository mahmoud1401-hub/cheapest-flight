import logging
import os
import requests
from flask import Flask, request
from telegram import Bot, Update, ReplyKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AMADEUS_CLIENT_ID = os.getenv("AMADEUS_CLIENT_ID")
AMADEUS_CLIENT_SECRET = os.getenv("AMADEUS_CLIENT_SECRET")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # عنوان السيرفر على Render

bot = Bot(token=TELEGRAM_TOKEN)
dispatcher = Dispatcher(bot=bot, update_queue=None, workers=4, use_context=True)

languages = {
    "English": "en", "Español": "es", "中文": "zh", "日本語": "ja",
    "Русский": "ru", "Deutsch": "de", "Svenska": "sv",
    "Français": "fr", "Italiano": "it", "عربي": "ar"
}
user_data = {}

def get_amadeus_token():
    url = "https://test.api.amadeus.com/v1/security/oauth2/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": AMADEUS_CLIENT_ID,
        "client_secret": AMADEUS_CLIENT_SECRET
    }
    response = requests.post(url, data=data)
    return response.json().get("access_token")

def start(update, context):
    reply_keyboard = [[lang] for lang in languages.keys()]
    update.message.reply_text(
        "Please choose your language / الرجاء اختيار لغتك:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )

def handle_language(update, context):
    lang = update.message.text
    if lang in languages:
        user_data[update.message.chat_id] = {"language": languages[lang], "step": "from"}
        update.message.reply_text("Enter departure city (IATA code, e.g. LAX):")
    else:
        update.message.reply_text("Invalid choice. Please choose a language from the list.")

def collect_input(update, context):
    chat_id = update.message.chat_id
    text = update.message.text.strip().upper()
    if chat_id not in user_data:
        user_data[chat_id] = {"step": "from"}

    step = user_data[chat_id]["step"]

    if step == "from":
        user_data[chat_id]["from"] = text
        user_data[chat_id]["step"] = "to"
        update.message.reply_text("Enter arrival city (IATA code, e.g. DXB):")
    elif step == "to":
        user_data[chat_id]["to"] = text
        user_data[chat_id]["step"] = "date"
        update.message.reply_text("Enter departure date (YYYY-MM-DD):")
    elif step == "date":
        user_data[chat_id]["date"] = text
        user_data[chat_id]["step"] = "trip_type"
        update.message.reply_text("One-way or Round-trip? (Type: one or round)")
    elif step == "trip_type":
        user_data[chat_id]["trip_type"] = text
        search_flight(update, context)

def search_flight(update, context):
    chat_id = update.message.chat_id
    data = user_data[chat_id]
    token = get_amadeus_token()

    if not token:
        update.message.reply_text("Failed to get access token from Amadeus.")
        return

    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "originLocationCode": data["from"],
        "destinationLocationCode": data["to"],
        "departureDate": data["date"],
        "adults": 1,
        "nonStop": False,
        "max": 1
    }
    if data["trip_type"].lower() == "round":
        params["returnDate"] = data["date"]

    url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        update.message.reply_text("Error fetching flight data.")
        return

    result = response.json()
    try:
        offer = result["data"][0]
        price = offer["price"]["total"]
        airline = offer["validatingAirlineCodes"][0]
        update.message.reply_text(f"Cheapest flight: Airline: {airline} Price: ${price}")
    except Exception:
        update.message.reply_text("No flights found or response parsing failed.")

@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return 'ok'

@app.route("/")
def index():
    return "Bot is running with webhook!"

def main():
    bot.set_webhook(f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}")

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_language))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, collect_input))

if __name__ == "__main__":
    main()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
