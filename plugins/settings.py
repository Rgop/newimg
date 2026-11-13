from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from config import ADMINS, OWNER_ID


def _is_admin(user_id):
    return user_id == OWNER_ID or user_id in ADMINS


@Client.on_callback_query(filters.regex(r"^settings$"))
async def settings(client, query: CallbackQuery):
    if not _is_admin(query.from_user.id):
        return await query.answer("Admins only.", show_alert=True)
    status = "enabled" if getattr(client, "fsub_enabled", True) else "disabled"
    text = (
        "<b>Admin Settings</b>\n\n"
        f"Force Subscribe: <b>{status}</b>\n"
        f"Configured channels: <code>{len(getattr(client, 'fsub_dict', {}))}</code>"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("Force Subscribe", callback_data="fsub")],
        [InlineKeyboardButton("Back", callback_data="close")],
    ])
    await query.message.edit_text(text, reply_markup=markup)
    await query.answer()
