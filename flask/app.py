import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)
import random

# Enable detailed logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Bot configuration
TOKEN = "7122337005:AAEwnhDhu7VfXhk75i2nZRGPjvs1zn2dJ7Y"
ADMIN_ID = 5963478252  # Admin's Telegram user ID

# Store user states, pairings, skip counts, and ad
user_states = {}  # {user_id: "waiting" or "chatting" or "idle"}
user_pairs = {}   # {user_id: partner_id}
waiting_users = [] # List of users waiting to be paired
skip_counts = {}  # {user_id: number_of_skips}
ad_content = {"type": None, "content": None}  # Store ad (text, photo, or video)
AD_SKIP_MIN = 20
AD_SKIP_MAX = 30

# Inline keyboard based on user state
def get_chat_keyboard(user_state: str) -> InlineKeyboardMarkup:
    """Return appropriate buttons based on user state."""
    if user_state == "idle":
        keyboard = [[InlineKeyboardButton("Find New Chat", callback_data="find")]]
    elif user_state == "chatting":
        keyboard = [
            [
                InlineKeyboardButton("Stop Chat", callback_data="stop"),
                InlineKeyboardButton("Find New Chat", callback_data="find"),
            ]
        ]
    else:  # waiting state
        keyboard = []  # No buttons while waiting
    return InlineKeyboardMarkup(keyboard) if keyboard else None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user_id = update.effective_user.id
    user_states[user_id] = "idle"
    skip_counts[user_id] = skip_counts.get(user_id, 0)
    await update.message.reply_text(
        "Welcome to the Anonymous Chat Bot! Click 'Find New Chat' to connect with someone.",
        reply_markup=get_chat_keyboard("idle")
    )
    logger.debug(f"User {user_id} started bot, set to idle")

async def set_ad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allow admin to set an ad (text, photo, or video)."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("Only the admin can set ads.")
        logger.warning(f"Non-admin {user_id} tried to set ad")
        return

    if update.message.text and len(update.message.text.split()) > 1:
        ad_content["type"] = "text"
        ad_content["content"] = " ".join(update.message.text.split()[1:])
        await update.message.reply_text("Ad set as text.")
        logger.info(f"Admin set text ad: {ad_content['content']}")
    elif update.message.photo:
        ad_content["type"] = "photo"
        ad_content["content"] = update.message.photo[-1].file_id
        await update.message.reply_text("Ad set as photo.")
        logger.info(f"Admin set photo ad: {ad_content['content']}")
    elif update.message.video:
        ad_content["type"] = "video"
        ad_content["content"] = update.message.video.file_id
        await update.message.reply_text("Ad set as video.")
        logger.info(f"Admin set video ad: {ad_content['content']}")
    else:
        await update.message.reply_text(
            "Please send a text message, photo, or video with /setad."
        )
        logger.warning(f"Admin {user_id} sent invalid /setad command")

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /find command or button to start looking for a chat partner."""
    user_id = update.effective_user.id
    logger.debug(f"User {user_id} triggered /find, current state: {user_states.get(user_id)}")

    if user_id in user_states and user_states[user_id] == "chatting":
        await update.message.reply_text(
            "You are already in a chat. Click 'Stop Chat' to end it.",
            reply_markup=get_chat_keyboard("chatting")
        )
        logger.debug(f"User {user_id} already in chat, cannot find new partner")
        return

    if user_id in waiting_users:
        await update.message.reply_text(
            "You are already waiting for a partner. Please wait."
            # No buttons while waiting
        )
        logger.debug(f"User {user_id} already in waiting list")
        return

    # Clean up stale states
    if user_id in user_pairs:
        partner_id = user_pairs.pop(user_id, None)
        if partner_id in user_pairs:
            del user_pairs[partner_id]
        logger.debug(f"Cleaned up stale pairing for {user_id}")

    # Add user to waiting list
    waiting_users.append(user_id)
    user_states[user_id] = "waiting"
    await update.message.reply_text(
        "Looking for a chat partner..."  # No buttons while waiting
    )
    logger.debug(f"User {user_id} added to waiting list: {waiting_users}")

    # Try to pair users
    if len(waiting_users) >= 2:
        user1 = waiting_users.pop(0)
        user2 = waiting_users.pop(0)
        
        # Ensure users are still valid
        if user1 not in user_states or user2 not in user_states:
            logger.warning(f"Invalid users in waiting list: {user1}, {user2}")
            return
        
        # Update states and pairings
        user_states[user1] = "chatting"
        user_states[user2] = "chatting"
        user_pairs[user1] = user2
        user_pairs[user2] = user1

        # Notify both users
        await context.bot.send_message(
            user1, "Connected to someone! Start chatting.", reply_markup=get_chat_keyboard("chatting")
        )
        await context.bot.send_message(
            user2, "Connected to someone! Start chatting.", reply_markup=get_chat_keyboard("chatting")
        )
        logger.info(f"Paired users {user1} and {user2}")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stop command or button to end the chat."""
    user_id = update.effective_user.id
    logger.debug(f"User {user_id} triggered /stop, current state: {user_states.get(user_id)}")

    if user_id not in user_states or user_states[user_id] != "chatting":
        await update.message.reply_text(
            "You are not in a chat. Click 'Find New Chat' to start one.",
            reply_markup=get_chat_keyboard("idle")
        )
        logger.debug(f"User {user_id} not in chat, cannot stop")
        return

    # Increment skip count
    skip_counts[user_id] = skip_counts.get(user_id, 0) + 1
    ad_threshold = random.randint(AD_SKIP_MIN, AD_SKIP_MAX)
    logger.debug(f"User {user_id} skip count: {skip_counts[user_id]}, threshold: {ad_threshold}")

    # Get partner ID
    partner_id = user_pairs.get(user_id)

    # Update states and remove pairings
    user_states[user_id] = "idle"
    if partner_id:
        user_states[partner_id] = "idle"
        await context.bot.send_message(
            partner_id,
            "Your chat partner has disconnected.",
            reply_markup=get_chat_keyboard("idle")
        )
        del user_pairs[partner_id]
        del user_pairs[user_id]
        logger.debug(f"User {user_id} disconnected from {partner_id}")

    # Remove from waiting list if present
    if user_id in waiting_users:
        waiting_users.remove(user_id)
        logger.debug(f"Removed {user_id} from waiting list")

    # Show ad if skip count reaches threshold
    if skip_counts[user_id] >= ad_threshold and ad_content["type"]:
        if ad_content["type"] == "text":
            await context.bot.send_message(user_id, ad_content["content"])
        elif ad_content["type"] == "photo":
            await context.bot.send_photo(user_id, ad_content["content"])
        elif ad_content["type"] == "video":
            await context.bot.send_video(user_id, ad_content["content"])
        skip_counts[user_id] = 0  # Reset skip count
        logger.info(f"Showed ad to user {user_id}")

    await update.message.reply_text(
        "Chat ended. Click 'Find New Chat' to start a new one.",
        reply_markup=get_chat_keyboard("idle")
    )

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to inspect bot state."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("Only the admin can use /debug.")
        return

    debug_info = (
        f"Waiting users: {waiting_users}\n"
        f"User states: {user_states}\n"
        f"User pairs: {user_pairs}\n"
        f"Skip counts: {skip_counts}\n"
        f"Ad content: {ad_content}"
    )
    await update.message.reply_text(debug_info)
    logger.info(f"Admin {user_id} ran /debug: {debug_info}")

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button presses."""
    query = update.callback_query
    await query.answer()

    # Create a pseudo-update for find/stop to reuse the same logic
    class PseudoUpdate:
        def __init__(self, query):
            self.message = query.message
            self.effective_user = query.from_user

    pseudo_update = PseudoUpdate(query)

    if query.data == "stop":
        await stop(pseudo_update, context)
    elif query.data == "find":
        await find(pseudo_update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle messages between paired users."""
    user_id = update.effective_user.id
    logger.debug(f"User {user_id} sent message, state: {user_states.get(user_id)}")

    if user_id not in user_states or user_states[user_id] != "chatting":
        await update.message.reply_text(
            "You are not in a chat. Click 'Find New Chat' to start one.",
            reply_markup=get_chat_keyboard("idle")
        )
        logger.debug(f"User {user_id} not in chat, cannot send message")
        return

    # Get partner ID
    partner_id = user_pairs.get(user_id)
    if partner_id:
        # Forward the message based on type
        if update.message.text:
            await context.bot.send_message(partner_id, update.message.text)
            logger.debug(f"Forwarded text from {user_id} to {partner_id}")
        elif update.message.photo:
            await context.bot.send_photo(partner_id, update.message.photo[-1].file_id)
            logger.debug(f"Forwarded photo from {user_id} to {partner_id}")
        elif update.message.video:
            await context.bot.send_video(partner_id, update.message.video.file_id)
            logger.debug(f"Forwarded video from {user_id} to {partner_id}")

async def error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors."""
    logger.error(f"Update {update} caused error {context.error}")

def main() -> None:
    """Run the bot."""
    application = Application.builder().token(TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setad", set_ad))
    application.add_handler(CommandHandler("find", find))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("debug", debug))
    application.add_handler(CallbackQueryHandler(handle_button))
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.VIDEO) & ~filters.COMMAND, handle_message
        )
    )
    application.add_error_handler(error)

    # Start the bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
