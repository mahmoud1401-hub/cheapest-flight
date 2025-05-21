import logging
import os
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AMADEUS_CLIENT_ID = os.getenv("AMADEUS_CLIENT_ID")
AMADEUS_CLIENT_SECRET = os.getenv("AMADEUS_CLIENT_SECRET")

languages = {
    "English": "en",
    "Español": "es",
    "中文": "zh",
    "日本語": "ja",
    "Русский": "ru",
    "Deutsch": "de",
    "Svenska": "sv",
    "Français": "fr",
    "Italiano": "it",
    "عربي": "ar"
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

def start(update: Update, context: CallbackContext):
    reply_keyboard = [[lang] for lang in languages.keys()]
    update.message.reply_text(
        "Please choose your language / الرجاء اختيار لغتك:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )

def handle_language(update: Update, context: CallbackContext):
    lang = update.message.text
    if lang in languages:
        user_data[update.message.chat_id] = {"language": languages[lang]}
        update.message.reply_text("Enter departure city (IATA code, e.g. LAX):")
        return
    update.message.reply_text("Invalid choice. Please choose a language from the list.")

def collect_input(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    text = update.message.text.strip().upper()

    if chat_id not in user_data:
        user_data[chat_id] = {}

    step = user_data[chat_id].get("step", "from")

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

def search_flight(update: Update, context: CallbackContext):
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

def main():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_language))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, collect_input))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
