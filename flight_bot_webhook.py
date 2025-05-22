import logging
import os
import requests
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
)
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
AMADEUS_API_KEY = os.getenv("AMADEUS_API_KEY")
AMADEUS_API_SECRET = os.getenv("AMADEUS_API_SECRET")

LANGUAGE, FROM_CITY, TO_CITY, TRIP_TYPE, DEPARTURE_DATE, RETURN_DATE, SHOW_FLIGHTS, CHOOSE_FROM, CHOOSE_TO = range(9)

user_data = {}
logger = logging.getLogger(__name__)

def get_amadeus_token():
    response = requests.post(
        "https://test.api.amadeus.com/v1/security/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": AMADEUS_API_KEY,
            "client_secret": AMADEUS_API_SECRET,
        },
    )
    return response.json().get("access_token")

def get_city_options(city_name, token):
    url = "https://test.api.amadeus.com/v1/reference-data/locations"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"keyword": city_name, "subType": "CITY"}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    locations = data.get("data", [])
    return locations[:3]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("English", callback_data="en")],
        [InlineKeyboardButton("Español", callback_data="es")],
        [InlineKeyboardButton("中文", callback_data="zh")],
        [InlineKeyboardButton("日本語", callback_data="ja")],
        [InlineKeyboardButton("Русский", callback_data="ru")],
        [InlineKeyboardButton("Deutsch", callback_data="de")],
        [InlineKeyboardButton("Svenska", callback_data="sv")],
        [InlineKeyboardButton("Schweizerdeutsch", callback_data="ch")],
    ]
    await update.message.reply_text("Please choose your language:", reply_markup=InlineKeyboardMarkup(keyboard))
    return LANGUAGE

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data[query.from_user.id] = {"language": query.data}
    await query.message.reply_text("Enter your departure city:")
    return FROM_CITY

async def from_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = get_amadeus_token()
    cities = get_city_options(update.message.text, token)
    if not cities:
        await update.message.reply_text("City not found. Please try again.")
        return FROM_CITY
    user_data[update.message.from_user.id]["from_city_choices"] = cities
    keyboard = [
        [InlineKeyboardButton(f"{c['address']['cityName']} ({c['iataCode']})", callback_data=c['iataCode'])]
        for c in cities
    ]
    await update.message.reply_text("Please choose the correct departure city:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_FROM

async def choose_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data[query.from_user.id]["from_code"] = query.data
    await query.message.reply_text("Enter your destination city:")
    return TO_CITY

async def to_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = get_amadeus_token()
    cities = get_city_options(update.message.text, token)
    if not cities:
        await update.message.reply_text("City not found. Please try again.")
        return TO_CITY
    user_data[update.message.from_user.id]["to_city_choices"] = cities
    keyboard = [
        [InlineKeyboardButton(f"{c['address']['cityName']} ({c['iataCode']})", callback_data=c['iataCode'])]
        for c in cities
    ]
    await update.message.reply_text("Please choose the correct destination city:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_TO

async def choose_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data[query.from_user.id]["to_code"] = query.data
    await query.message.reply_text("Is this a one-way or round trip? (Enter: one-way / round)")
    return TRIP_TYPE

async def trip_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if text not in ["one-way", "round"]:
        await update.message.reply_text("Please enter either 'one-way' or 'round'")
        return TRIP_TYPE
    user_data[update.message.from_user.id]["trip_type"] = text
    await update.message.reply_text("Enter departure date (YYYY-MM-DD):")
    return DEPARTURE_DATE

async def departure_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.message.from_user.id]["departure_date"] = update.message.text
    if user_data[update.message.from_user.id]["trip_type"] == "round":
        await update.message.reply_text("Enter return date (YYYY-MM-DD):")
        return RETURN_DATE
    return await show_flights(update, context)

async def return_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.message.from_user.id]["return_date"] = update.message.text
    return await show_flights(update, context)

async def show_flights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    token = get_amadeus_token()
    headers = {"Authorization": f"Bearer {token}"}
    base_url = "https://test.api.amadeus.com/v2/shopping/flight-offers"

    params = {
        "originLocationCode": user_data[uid]["from_code"],
        "destinationLocationCode": user_data[uid]["to_code"],
        "departureDate": user_data[uid]["departure_date"],
        "adults": 1,
        "nonStop": False,
        "max": 3,
    }

    if user_data[uid]["trip_type"] == "round":
        params["returnDate"] = user_data[uid]["return_date"]

    response = requests.get(base_url, headers=headers, params=params)
    data = response.json()

    if not data.get("data"):
        await update.message.reply_text("No flights found.")
        return ConversationHandler.END

    msg = "Here are some flight options:\n"

    for flight in data["data"]:
        itinerary = flight["itineraries"][0]["segments"][0]
        from_code = itinerary["departure"]["iataCode"]
        to_code = itinerary["arrival"]["iataCode"]
        dep = itinerary["departure"]["at"]
        arr = itinerary["arrival"]["at"]
        price = flight["price"]["total"]
        
        msg += f"From: {from_code} to {to_code}\n"
        msg += f"Departure: {dep}\n"
        msg += f"Arrival: {arr}\n"
        msg += f"Price: {price} USD\n\n"

    await update.message.reply_text(msg)
    return ConversationHandler.END

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANGUAGE: [CallbackQueryHandler(language_chosen)],
            FROM_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, from_city)],
            CHOOSE_FROM: [CallbackQueryHandler(choose_from)],
            TO_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, to_city)],
            CHOOSE_TO: [CallbackQueryHandler(choose_to)],
            TRIP_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, trip_type)],
            DEPARTURE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, departure_date)],
            RETURN_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, return_date)],
        },
        fallbacks=[],
    )

    application.add_handler(conv_handler)
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        webhook_url=os.environ.get("RENDER_EXTERNAL_URL") + "/webhook"
    )

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
