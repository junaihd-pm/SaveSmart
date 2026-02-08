class UserProfile:
    def __init__(self, user_id, name, balance=0):
        self.user_id = user_id
        self.name = name
        self.balance = balance

    def update_balance(self, amount):
        self.balance += amount

    def get_profile_info(self):
        return {'user_id': self.user_id, 'name': self.name, 'balance': self.balance}


class ProfileManager:
    def __init__(self):
        self.profiles = {}

    def add_profile(self, user_profile):
        self.profiles[user_profile.user_id] = user_profile

    def get_profile(self, user_id):
        return self.profiles.get(user_id, None)

    def update_profile_balance(self, user_id, amount):
        profile = self.get_profile(user_id)
        if profile:
            profile.update_balance(amount)


async def start_handler(update, context):
    await context.bot.send_message(chat_id=update.effective_chat.id, text='Welcome! You can manage your finances here.')


async def help_handler(update, context):
    await context.bot.send_message(chat_id=update.effective_chat.id, text='Here are the commands you can use...')


async def balance_handler(update, context):
    user_id = update.effective_user.id
    profile_manager = ProfileManager()  # Assuming instance creation
    profile = profile_manager.get_profile(user_id)
    if profile:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Your balance is: {profile.balance}')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text='Profile not found!')


async def update_balance_handler(update, context):
    user_id = update.effective_user.id
    amount = float(context.args[0]) if context.args else 0
    profile_manager = ProfileManager()  # Assuming instance creation
    profile_manager.update_profile_balance(user_id, amount)
    await context.bot.send_message(chat_id=update.effective_chat.id, text='Balance updated!')
