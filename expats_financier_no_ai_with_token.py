"""
Expat's Financier Bot - No AI Version
Simple financial tracking bot for UAE expats
"""
import requests
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

# ---------- NEW IMPORTS FOR RENDER (WEBHOOK MODE) ----------
from flask import Flask, request
import asyncio
# ----------------------------------------------------------

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Storage directory
STORAGE_DIR = Path("user_profiles")
STORAGE_DIR.mkdir(exist_ok=True)

# Onboarding states (only 5 questions!)
(ONBOARDING_NAME, ONBOARDING_JOB, ONBOARDING_INCOME,
 ONBOARDING_EXPENSE, ONBOARDING_SAVINGS, ONBOARDING_EMERGENCY) = range(6)

# Main states
(DASHBOARD, MAIN_MENU, UPDATE_INCOME, UPDATE_EXPENSE_MENU, UPDATE_EXPENSE,
 UPDATE_WEEKLY, UPDATE_SAVINGS, UPDATE_EMERGENCY) = range(6, 14)


class UserProfile:
    """User's financial profile"""
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.name = ""
        self.job_position = ""
        self.income = 0.0
        self.total_expense = 0.0
        
        self.expenses = {
            'home_remittance': 0.0,
            'room_rent': 0.0,
            'food': 0.0,
            'transport': 0.0,
            'miscellaneous': 0.0
        }
        
        self.weekly_spending = []
        self.savings_goal = 0.0
        self.emergency_fund = 0.0
        self.onboarding_completed = False
        self.created_at = datetime.now().isoformat()
        self.last_updated = datetime.now().isoformat()
    
    def get_expense_total(self) -> float:
        breakdown = sum(self.expenses.values())
        return breakdown if breakdown > 0 else self.total_expense
    
    def get_weekly_spending(self) -> float:
        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        total = 0.0
        for exp in self.weekly_spending:
            if datetime.fromisoformat(exp['date']) >= week_start:
                total += exp['amount']
        return total
    
    def get_disposable(self) -> float:
        return self.income - self.get_expense_total()
    
    def get_after_savings(self) -> float:
        return self.get_disposable() - self.savings_goal
    
    def get_health_score(self) -> int:
        score = 0
        
        if self.income > 0:
            savings_rate = (self.savings_goal / self.income) * 100
            if savings_rate >= 20:
                score += 50
            elif savings_rate >= 15:
                score += 35
            elif savings_rate >= 10:
                score += 20
            elif savings_rate >= 5:
                score += 10
        
        if self.total_expense > 0:
            months_covered = self.emergency_fund / self.total_expense
            if months_covered >= 6:
                score += 50
            elif months_covered >= 3:
                score += 30
            elif months_covered >= 1:
                score += 15
        
        return score
    
    def to_dict(self) -> dict:
        return {
            'user_id': self.user_id,
            'name': self.name,
            'job_position': self.job_position,
            'income': self.income,
            'total_expense': self.total_expense,
            'expenses': self.expenses,
            'weekly_spending': self.weekly_spending,
            'savings_goal': self.savings_goal,
            'emergency_fund': self.emergency_fund,
            'onboarding_completed': self.onboarding_completed,
            'created_at': self.created_at,
            'last_updated': self.last_updated
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        profile = cls(data['user_id'])
        profile.name = data.get('name', '')
        profile.job_position = data.get('job_position', '')
        profile.income = data.get('income', 0.0)
        profile.total_expense = data.get('total_expense', 0.0)
        profile.expenses = data.get('expenses', {
            'home_remittance': 0.0,
            'room_rent': 0.0,
            'food': 0.0,
            'transport': 0.0,
            'miscellaneous': 0.0
        })
        profile.weekly_spending = data.get('weekly_spending', [])
        profile.savings_goal = data.get('savings_goal', 0.0)
        profile.emergency_fund = data.get('emergency_fund', 0.0)
        profile.onboarding_completed = data.get('onboarding_completed', False)
        profile.created_at = data.get('created_at', datetime.now().isoformat())
        profile.last_updated = data.get('last_updated', datetime.now().isoformat())
        return profile


class ProfileManager:
    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir
    
    def get_profile_file(self, user_id: int) -> Path:
        return self.storage_dir / f"user_{user_id}.json"
    
    def load_profile(self, user_id: int) -> UserProfile:
        profile_file = self.get_profile_file(user_id)
        if profile_file.exists():
            try:
                with open(profile_file, 'r') as f:
                    return UserProfile.from_dict(json.load(f))
            except Exception as e:
                logger.error(f"Error loading profile: {e}")
        return UserProfile(user_id)
    
    def save_profile(self, profile: UserProfile):
        try:
            profile.last_updated = datetime.now().isoformat()
            with open(self.get_profile_file(profile.user_id), 'w') as f:
                json.dump(profile.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Error saving profile: {e}")


GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbzevey7XlnQHiiMYLLgO7Abf2wcd7DL77dOsh1xZJFoWx6TvUWBdRtlXXqYVhAu63ku/exec"

def send_to_google_sheets(profile: UserProfile):
    data = {
        "user_id": profile.user_id,
        "name": profile.name,
        "job": profile.job_position,
        "income": profile.income,
        "expense": profile.total_expense,
        "savings": profile.savings_goal,
        "emergency": profile.emergency_fund
    }
    try:
        requests.post(GOOGLE_SHEET_URL, json=data, timeout=10)
    except Exception as e:
        logger.error(f"Google Sheets error: {e}")


profile_manager = ProfileManager(STORAGE_DIR)

# ===================== NEW: FLASK + WEBHOOK =====================

app_flask = Flask(__name__)
bot_app = None

@app_flask.route("/", methods=["POST"])
def webhook():
    global bot_app
    if bot_app is None:
        return "Bot not ready", 500

    update = Update.de_json(request.get_json(), bot_app.bot)
    asyncio.run(bot_app.process_update(update))
    return "OK"

# ================================================================


# (ALL YOUR EXISTING HANDLERS ARE UNCHANGED FROM HERE DOWN)
# ... [your start(), onboarding_*, show_dashboard(), menus, etc. remain exactly as you sent] ...
# I am not repeating them here to avoid duplication — they stay as-is.


def main():
    global bot_app

    # USE ENV VARIABLE ON RENDER (safer than hardcoding)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        # fallback (only if you really want)
        token = "8306299902:AAEN6Np299sYAnOkYb14LrcmWpm2YbyeB44"

    bot_app = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ONBOARDING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_name)],
            ONBOARDING_JOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_job)],
            ONBOARDING_INCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_income)],
            ONBOARDING_EXPENSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_expense)],
            ONBOARDING_SAVINGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_savings)],
            ONBOARDING_EMERGENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_emergency)],
            DASHBOARD: [CallbackQueryHandler(handle_callback)],
            MAIN_MENU: [CallbackQueryHandler(handle_callback)],
            UPDATE_INCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_income_update)],
            UPDATE_EXPENSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_expense_update)],
            UPDATE_WEEKLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_weekly_update)],
            UPDATE_SAVINGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_savings_update)],
            UPDATE_EMERGENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_emergency_update)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    bot_app.add_handler(conv_handler)

    # Start Flask server (Render-friendly)
    app_flask.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))


if __name__ == '__main__':
    main()
