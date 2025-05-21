import logging
from flask import Flask, request
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
import requests
import os

# إعدادات تسجيل الأحداث
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# تعريف الخطوات
LANGUAGE, FROM_CITY, TO_CITY, DEPARTURE_DATE, RETURN_DATE, TRIP_TYPE = range(6)

# لغات مدعومة
languages = {
    "English": "en",
    "Español": "es",
    "中文": "zh",
    "日本語": "ja",
    "Deutsch": "de",
    "Русский": "ru",
    "Svenska": "sv",
    "Français": "fr"
}

# حفظ الحالات
user_data = {}

# إعدادات Flask
app = Flask(__name__)

# إعداد التوكن
TOKEN = os.environ.get("TELEGRAM_TOKEN")
AMADEUS_CLIENT_ID = os.environ.get("AMADEUS_CLIENT_ID")
AMADEUS_CLIENT_SECRET = os.environ.get("AMADEUS_CLIENT_SECRET")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

# جلب توكن Amadeus
def get_amadeus_token():
    url = "https://test.api.amadeus.com/v1/security/oauth2/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": AMADEUS_CLIENT_ID,
        "client_secret": AMADEUS_CLIENT_SECRET
    }
    response = requests.post(url, data=data)
    return response.json()["access_token"]

# تحويل اسم مدينة إلى رمز IATA
def get_iata_code(city_name, token):
    url = "https://test.api.amadeus.com/v1/reference-data/locations"
    params = {
        "keyword": city_name,
        "subType": "CITY"
    }
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    if "data" in data and len(data["data"]) > 0:
        return data["data"][0]["iataCode"]
    return None

# بدء المحادثة
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton(lang)] for lang in languages.keys()]
    await update.message.reply_text("Please choose a language / Veuillez choisir une langue:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return LANGUAGE

# تحديد اللغة
async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = update.message.text
    if lang not in languages:
        await update.message.reply_text("Please select a valid language.")
        return LANGUAGE
    context.user_data["language"] = languages[lang]
    await update.message.reply_text("Enter departure city:")
    return FROM_CITY

# مدينة الانطلاق
async def from_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from_city_name"] = update.message.text
    await update.message.reply_text("Enter destination city:")
    return TO_CITY

# مدينة الوصول
async def to_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["to_city_name"] = update.message.text
    await update.message.reply_text("Enter departure date (YYYY-MM-DD):")
    return DEPARTURE_DATE

# تاريخ الذهاب
async def departure_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["departure_date"] = update.message.text
    keyboard = [[KeyboardButton("One Way")], [KeyboardButton("Round Trip")]]
    await update.message.reply_text("Is it a one-way or round trip?", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return TRIP_TYPE

# نوع الرحلة
async def trip_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["trip_type"] = update.message.text
    if update.message.text == "Round Trip":
        await update.message.reply_text("Enter return date (YYYY-MM-DD):")
        return RETURN_DATE
    return await search_flights(update, context)

# تاريخ العودة
async def return_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["return_date"] = update.message.text
    return await search_flights(update, context)

# البحث عن الرحلات
async def search_flights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = get_amadeus_token()
    from_code = get_iata_code(context.user_data["from_city_name"], token)
    to_code = get_iata_code(context.user_data["to_city_name"], token)

    if not from_code or not to_code:
        await update.message.reply_text("City not found. Please try again.")
        await update.message.reply_text("Enter departure city:")
        return FROM_CITY

    url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
    params = {
        "originLocationCode": from_code,
        "destinationLocationCode": to_code,
        "departureDate": context.user_data["departure_date"],
        "adults": 1,
        "currencyCode": "USD",
        "max": 3
    }
    if context.user_data.get("trip_type") == "Round Trip":
        params["returnDate"] = context.user_data["return_date"]

    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    if "data" not in data or len(data["data"]) == 0:
        await update.message.reply_text("No flights found.")
        return ConversationHandler.END

    msg = "Here are some flight options:

"
    for flight in data["data"]:
        price = flight["price"]["total"]
        itinerary = flight["itineraries"][0]
        dep = itinerary["segments"][0]["departure"]["at"]
        arr = itinerary["segments"][-1]["arrival"]["at"]
        msg += f"From: {from_code} to {to_code}
Departure: {dep}
Arrival: {arr}
Price: {price} USD

"

    await update.message.reply_text(msg)
    return ConversationHandler.END

# إعداد Flask webhook
from telegram.ext import ApplicationBuilder
application = Application.builder().token(TOKEN).build()

from telegram.ext import CommandHandler, MessageHandler, filters

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_language)],
        FROM_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, from_city)],
        TO_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, to_city)],
        DEPARTURE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, departure_date)],
        TRIP_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, trip_type)],
        RETURN_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, return_date)],
    },
    fallbacks=[]
)

application.add_handler(conv_handler)

@app.route("/", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put(update)
    return "ok"

if __name__ == "__main__":
    application.run_webhook(
        listen="0.0.0.0",
        port=10000,
        webhook_url=WEBHOOK_URL
    )