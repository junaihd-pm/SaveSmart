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
        
        # Optional breakdown
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
        """Get detailed expense or fallback to total"""
        breakdown = sum(self.expenses.values())
        return breakdown if breakdown > 0 else self.total_expense
    
    def get_weekly_spending(self) -> float:
        """Calculate current week spending"""
        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        total = 0.0
        for exp in self.weekly_spending:
            if datetime.fromisoformat(exp['date']) >= week_start:
                total += exp['amount']
        return total
    
    def get_disposable(self) -> float:
        """Calculate disposable income"""
        return self.income - self.get_expense_total()
    
    def get_after_savings(self) -> float:
        """Calculate after savings"""
        return self.get_disposable() - self.savings_goal
    
    def get_health_score(self) -> int:
        """Simple health score 0-100"""
        score = 0
        
        # Savings rate (50 points)
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
        
        # Emergency fund (50 points)
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


def progress_bar(percentage: float) -> str:
    """Create simple progress bar"""
    filled = int((percentage / 100) * 10)
    return "█" * filled + "░" * (10 - filled)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start bot"""
    user_id = update.effective_user.id
    profile = profile_manager.load_profile(user_id)
    context.user_data['profile'] = profile
    
    if profile.onboarding_completed:
        return await show_dashboard(update, context)
    
    await update.message.reply_text(
        "👋 *Welcome to Expat's Financier*\n\n"
        "Quick setup - 5 questions only!\n\n"
        "What's your name?",
        parse_mode='Markdown'
    )
    return ONBOARDING_NAME


async def onboarding_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    profile = context.user_data['profile']
    profile.name = update.message.text.strip()
    
    await update.message.reply_text(f"Hi {profile.name}!\n\nYour job position?")
    return ONBOARDING_JOB


async def onboarding_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    profile = context.user_data['profile']
    profile.job_position = update.message.text.strip()
    
    await update.message.reply_text("Monthly income in AED?")
    return ONBOARDING_INCOME


async def onboarding_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        income = float(update.message.text.replace(',', '').strip())
        profile = context.user_data['profile']
        profile.income = income
        
        await update.message.reply_text(
            f"✅ AED {income:,.0f}\n\n"
            f"Total monthly expenses?"
        )
        return ONBOARDING_EXPENSE
    except ValueError:
        await update.message.reply_text("Enter a valid number:")
        return ONBOARDING_INCOME


async def onboarding_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        expense = float(update.message.text.replace(',', '').strip())
        profile = context.user_data['profile']
        profile.total_expense = expense
        
        await update.message.reply_text(
            f"✅ AED {expense:,.0f}\n\n"
            f"Monthly savings goal?"
        )
        return ONBOARDING_SAVINGS
    except ValueError:
        await update.message.reply_text("Enter a valid number:")
        return ONBOARDING_EXPENSE


async def onboarding_savings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        savings = float(update.message.text.replace(',', '').strip())
        profile = context.user_data['profile']
        profile.savings_goal = savings
        
        await update.message.reply_text(
            f"✅ AED {savings:,.0f}\n\n"
            f"Current emergency fund?"
        )
        return ONBOARDING_EMERGENCY
    except ValueError:
        await update.message.reply_text("Enter a valid number:")
        return ONBOARDING_SAVINGS


async def onboarding_emergency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        emergency = float(update.message.text.replace(',', '').strip())
        profile = context.user_data['profile']
        profile.emergency_fund = emergency
        profile.onboarding_completed = True
        profile_manager.save_profile(profile)
        send_to_google_sheets(profile)
        
        await update.message.reply_text(
            f"🎉 *Done!*\n\n"
            f"Loading your dashboard...",
            parse_mode='Markdown'
        )
        return await show_dashboard(update, context)
    except ValueError:
        await update.message.reply_text("Enter a valid number:")
        return ONBOARDING_EMERGENCY


async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show clean dashboard with progress bars"""
    profile = context.user_data['profile']
    
    expense = profile.get_expense_total()
    disposable = profile.get_disposable()
    after_savings = profile.get_after_savings()
    weekly = profile.get_weekly_spending()
    weekly_budget = expense / 4
    health = profile.get_health_score()
    
    expense_pct = (expense / profile.income * 100) if profile.income > 0 else 0
    savings_pct = (profile.savings_goal / profile.income * 100) if profile.income > 0 else 0
    weekly_pct = (weekly / weekly_budget * 100) if weekly_budget > 0 else 0
    emergency_pct = (profile.emergency_fund / (expense * 6) * 100) if expense > 0 else 0
    
    text = (
        f"*{profile.name}'s Dashboard*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        
        f"💰 *Income*\n"
        f"AED {profile.income:,.0f}\n\n"
        
        f"📊 *Monthly Spending*\n"
        f"AED {expense:,.0f}\n"
        f"{progress_bar(min(expense_pct, 100))} {expense_pct:.0f}%\n\n"
        
        f"📅 *This Week*\n"
        f"AED {weekly:,.0f} / {weekly_budget:,.0f}\n"
        f"{progress_bar(min(weekly_pct, 100))} {weekly_pct:.0f}%\n\n"
        
        f"💵 *Disposable*\n"
        f"AED {disposable:,.0f}\n\n"
        
        f"💰 *Savings Goal*\n"
        f"AED {profile.savings_goal:,.0f}/month\n"
        f"{progress_bar(min(savings_pct, 100))} {savings_pct:.0f}%\n\n"
        
        f"🚨 *Emergency Fund*\n"
        f"AED {profile.emergency_fund:,.0f}\n"
        f"{progress_bar(min(emergency_pct, 100))} {emergency_pct:.0f}%\n\n"
        
        f"📈 *Health Score*\n"
        f"{health}/100\n"
        f"{progress_bar(health)}"
    )
    
    if health >= 70:
        text += " ✅"
    elif health >= 40:
        text += " 💡"
    else:
        text += " ⚠️"
    
    keyboard = [
        [InlineKeyboardButton("⚙️ Update", callback_data='menu')],
        [InlineKeyboardButton("🔄 Refresh", callback_data='refresh')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, reply_markup=reply_markup, parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            text, reply_markup=reply_markup, parse_mode='Markdown'
        )
    
    return DASHBOARD


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show simple menu"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("💰 Income", callback_data='up_income')],
        [InlineKeyboardButton("📊 Expenses", callback_data='up_expense')],
        [InlineKeyboardButton("📅 Log Weekly", callback_data='up_weekly')],
        [InlineKeyboardButton("💰 Savings", callback_data='up_savings')],
        [InlineKeyboardButton("🚨 Emergency", callback_data='up_emergency')],
        [InlineKeyboardButton("« Back", callback_data='back')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("*Update*\n\nWhat to change?", reply_markup=reply_markup, parse_mode='Markdown')
    return MAIN_MENU


async def show_expense_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show expense breakdown"""
    query = update.callback_query
    await query.answer()
    
    profile = context.user_data['profile']
    
    keyboard = [
        [InlineKeyboardButton(f"🏠 Remittance ({profile.expenses['home_remittance']:,.0f})", callback_data='ex_rem')],
        [InlineKeyboardButton(f"🏠 Rent ({profile.expenses['room_rent']:,.0f})", callback_data='ex_rent')],
        [InlineKeyboardButton(f"🍽️ Food ({profile.expenses['food']:,.0f})", callback_data='ex_food')],
        [InlineKeyboardButton(f"🚗 Transport ({profile.expenses['transport']:,.0f})", callback_data='ex_trans')],
        [InlineKeyboardButton(f"📦 Other ({profile.expenses['miscellaneous']:,.0f})", callback_data='ex_misc')],
        [InlineKeyboardButton("« Back", callback_data='menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    total = sum(profile.expenses.values())
    await query.edit_message_text(
        f"*Expenses*\n\nTotal: AED {total:,.0f}\n\nSelect category:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return MAIN_MENU


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle all callbacks"""
    query = update.callback_query
    await query.answer()
    action = query.data
    
    if action == 'refresh' or action == 'back':
        return await show_dashboard(update, context)
    
    elif action == 'menu':
        return await show_menu(update, context)
    
    elif action == 'up_income':
        await query.edit_message_text("Enter new monthly income:")
        context.user_data['updating'] = 'income'
        return UPDATE_INCOME
    
    elif action == 'up_expense':
        return await show_expense_menu(update, context)
    
    elif action == 'up_weekly':
        await query.edit_message_text("Amount spent this week?")
        return UPDATE_WEEKLY
    
    elif action == 'up_savings':
        await query.edit_message_text("New savings goal?")
        context.user_data['updating'] = 'savings'
        return UPDATE_SAVINGS
    
    elif action == 'up_emergency':
        await query.edit_message_text("Current emergency fund?")
        context.user_data['updating'] = 'emergency'
        return UPDATE_EMERGENCY
    
    elif action.startswith('ex_'):
        exp_map = {
            'ex_rem': ('home_remittance', 'Remittance'),
            'ex_rent': ('room_rent', 'Rent'),
            'ex_food': ('food', 'Food'),
            'ex_trans': ('transport', 'Transport'),
            'ex_misc': ('miscellaneous', 'Other'),
        }
        category, name = exp_map[action]
        context.user_data['updating_expense'] = category
        await query.edit_message_text(f"{name} amount?")
        return UPDATE_EXPENSE
    
    return MAIN_MENU


async def handle_income_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.replace(',', '').strip())
        profile = context.user_data['profile']
        profile.income = amount
        profile_manager.save_profile(profile)
        await update.message.reply_text(f"✅ Updated to AED {amount:,.0f}")
        return await show_dashboard(update, context)
    except ValueError:
        await update.message.reply_text("Enter valid number:")
        return UPDATE_INCOME


async def handle_expense_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.replace(',', '').strip())
        profile = context.user_data['profile']
        category = context.user_data.get('updating_expense')
        if category:
            profile.expenses[category] = amount
            profile_manager.save_profile(profile)
            await update.message.reply_text(f"✅ Updated to AED {amount:,.0f}")
        return await show_dashboard(update, context)
    except ValueError:
        await update.message.reply_text("Enter valid number:")
        return UPDATE_EXPENSE


async def handle_weekly_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.replace(',', '').strip())
        profile = context.user_data['profile']
        profile.weekly_spending.append({
            'date': datetime.now().isoformat(),
            'amount': amount
        })
        profile_manager.save_profile(profile)
        await update.message.reply_text(f"✅ Logged AED {amount:,.0f}")
        return await show_dashboard(update, context)
    except ValueError:
        await update.message.reply_text("Enter valid number:")
        return UPDATE_WEEKLY


async def handle_savings_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.replace(',', '').strip())
        profile = context.user_data['profile']
        profile.savings_goal = amount
        profile_manager.save_profile(profile)
        await update.message.reply_text(f"✅ Updated to AED {amount:,.0f}")
        return await show_dashboard(update, context)
    except ValueError:
        await update.message.reply_text("Enter valid number:")
        return UPDATE_SAVINGS


async def handle_emergency_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.replace(',', '').strip())
        profile = context.user_data['profile']
        profile.emergency_fund = amount
        profile_manager.save_profile(profile)
        await update.message.reply_text(f"✅ Updated to AED {amount:,.0f}")
        return await show_dashboard(update, context)
    except ValueError:
        await update.message.reply_text("Enter valid number:")
        return UPDATE_EMERGENCY


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelled")
    return await show_dashboard(update, context)


def main():
    token = "8306299902:AAEN6Np299sYAnOkYb14LrcmWpm2YbyeB44"
    
    app = Application.builder().token(token).build()
    
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
    
    app.add_handler(conv_handler)
    
    logger.info("Expat's Financier started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == '__main__':
    main()
