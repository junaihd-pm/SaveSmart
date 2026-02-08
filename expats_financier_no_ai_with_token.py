# Complete Telegram Bot Code

import telebot

API_TOKEN = 'YOUR_API_TOKEN'  # Replace with your actual API token
bot = telebot.TeleBot(API_TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Welcome! This is your Telegram bot.")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, message.text)

if __name__ == '__main__':
    bot.polling()