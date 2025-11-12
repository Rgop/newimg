import os
import asyncio
import sys
import time
import base64
from collections import defaultdict
from pyrogram import Client, filters, __version__
from pyrogram.enums import ParseMode, ChatMemberStatus, ChatAction
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, User
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, UserNotParticipant, ChatIdInvalid

from datetime import datetime, timedelta
from config import ADMINS, OWNER_ID
from helper_func import encode, decode
from database.database import save_encoded_link, get_channel_by_encoded_link, save_encoded_link2, get_channel_by_encoded_link2
from database.database import add_user, del_user, full_userbase, present_user, is_admin, get_channel_photo_link, is_user_banned
        
#=====================================================================================##

def _escape_md_v2(text: str) -> str:
    # Escape all MDV2 special chars
    if not text:
        return text
    specials = r"_*[]()~`>#+-=|{}.!\\"
    escaped = ""
    for ch in text:
        if ch in specials:
            escaped += f"\\{ch}"
        else:
            escaped += ch
    return escaped

def _escape_md_v2_url(url: str) -> str:
    if not url:
        return url
    # In MarkdownV2 link target, escape backslashes and parentheses only
    return url.replace("\\", "\\\\").replace("(", "\$$").replace(")", "\$$")

@Client.on_message(filters.command('start') & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id

    # Check if the user is banned
    if await is_user_banned(user_id):
        return  # Silently ignore banned users, no response

    # Proceed with the original functionality if the user is not banned
    text = message.text
    await add_user(user_id)  # Add user to DB
    
    placeholder = None
    try:
        await client.send_chat_action(message.chat.id, ChatAction.TYPING)
    except Exception:
        pass

    if len(text) > 7:
        try:
            base64_string = text.split(" ", 1)[1].strip()  # strip whitespace from the start payload for safety
            is_request = base64_string.startswith("req_")
            
            if is_request:
                base64_string = base64_string[4:]
                channel_id = await get_channel_by_encoded_link2(base64_string)
            else:
                channel_id = await get_channel_by_encoded_link(base64_string)
            
            if not channel_id:
                if placeholder:
                    try: await placeholder.delete()
                    except Exception: pass
                return await message.reply_text("⚠️ Invalid or expired invite link.")

            # Compute and reuse expire_at to keep time consistent in caption
            expire_at = datetime.now() + timedelta(minutes=10)
            expire_seconds = int((expire_at - datetime.now()).total_seconds())

            invite = await client.create_chat_invite_link(
                chat_id=channel_id,
                expire_date=expire_at,
                creates_join_request=is_request
            )

            button_text = "🛎️ Request to Join" if is_request else "🔗 Join Channel"
            button = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, url=invite.invite_link)]])

            # If a photo_link is available, send a photo with a MarkdownV2 caption; else fallback to text
            photo_link = await get_channel_photo_link(channel_id)
            if photo_link:
                # Fetch channel name
                chat = await client.get_chat(channel_id)
                channel_handle = f"@{getattr(chat, 'username', None)}" if getattr(chat, "username", None) else (chat.title or "Channel")
                # Build caption in MarkdownV2
                linked_title = "[" + _escape_md_v2("Title'-") + f"]({_escape_md_v2_url(photo_link)})"
                caption = (
                    f"{linked_title}{_escape_md_v2(channel_handle)}"
                    f"{_escape_md_v2('𝖳𝗁𝗂𝗌 𝗅𝗂𝗇𝗄 𝗐𝗂𝗅𝗅 𝖾𝗑𝗉𝗂𝗋𝖾 𝗂𝗇 ')}{_escape_md_v2(str(expire_seconds))}"
                    f"{_escape_md_v2(' seconds.')}"
                )
                try:
                    await message.reply_photo(
                        photo=photo_link,
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN_V2,
                        reply_markup=button
                    )
                except Exception as e:
                    print(f"[start] send_photo markdown failed: {e}")
                    fallback_caption = f"Title'- {channel_handle} This link will expire in {expire_seconds} seconds."
                    await message.reply_photo(
                        photo=photo_link,
                        caption=fallback_caption,
                        reply_markup=button
                    )
            else:
                # Fallback to previous text behavior
                await message.reply_text("Here is your link! Click below to proceed:", reply_markup=button)

            asyncio.create_task(revoke_invite_after_10_minutes(client, channel_id, invite.invite_link, is_request))

        except Exception as e:
            # Ensure placeholder is removed on errors to avoid clutter
            if placeholder:
                try: await placeholder.delete()
                except Exception: pass
            await message.reply_text("⚠️ Invalid or expired link.")
            print(f"Decoding error: {e}")
    else:
        # Remove any stray placeholder in no-payload branch
        if placeholder:
            try: await placeholder.delete()
            except Exception: pass
        inline_buttons = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("About Me", callback_data="help"),
                 InlineKeyboardButton("Close", callback_data="close")]
            ]
        )
        
        await message.reply_text(
            "<b><i>Welcome to the advanced links sharing bot.\nWith this bot, you can share links and keep your channels safe from copyright issues</i></b>",
            reply_markup=inline_buttons
        )
        
#=====================================================================================##

WAIT_MSG = """"<b>Processing ....</b>"""

REPLY_ERROR = """<code>Use this command as a reply to any telegram message with out any spaces.</code>"""

#=====================================================================================##

@Client.on_message(filters.command('users') & filters.user(OWNER_ID))
async def get_users(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id != OWNER_ID:
        return
    msg = await client.send_message(chat_id=message.chat.id, text=WAIT_MSG)
    users = await full_userbase()
    await msg.edit(f"{len(users)} users are using this bot")


#=====================================================================================##

@Client.on_message(filters.private & filters.command('broadcast') & filters.user(OWNER_ID))
async def send_text(client: Client, message: Message):
    if message.reply_to_message:
        query = await full_userbase()
        broadcast_msg = message.reply_to_message
        total = 0
        successful = 0
        blocked = 0
        deleted = 0
        unsuccessful = 0

        pls_wait = await message.reply("<i>Broadcasting Message.. This will Take Some Time </i>")
        for chat_id in query:
            try:
                await broadcast_msg.copy(chat_id)
                successful += 1
            except FloodWait as e:
                await asyncio.sleep(e.x)
                await broadcast_msg.copy(chat_id)
                successful += 1
            except UserIsBlocked:
                await del_user(chat_id)
                blocked += 1
            except InputUserDeactivated:
                await del_user(chat_id)
                deleted += 1
            except:
                unsuccessful += 1
                pass
            total += 1

        status = f"""<b><u>Broadcast Completed</u>

Total Users: <code>{total}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""

        return await pls_wait.edit(status)

    else:
        msg = await message.reply(REPLY_ERROR)
        await asyncio.sleep(8)
        await msg.delete()

#=====================================================================================##

@Client.on_callback_query(filters.regex("help"))
async def help_callback(client: Client, callback_query):
    # Define the inline keyboard with the "Close" button
    inline_buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Close", callback_data="close")]
        ]
    )
    
    
    await callback_query.answer()
    await callback_query.message.edit_text("<b><i>About Us..\n\n‣ Made for : @Anime_X_Hunters\n‣ Owned by : @Okabe_xRintarou\n‣ Developer : @The_Seishiro_Nagi\n\n Adios !!</i></b>", reply_markup=inline_buttons)

@Client.on_callback_query(filters.regex("close"))
async def close_callback(client: Client, callback_query):
    await callback_query.answer()
    await callback_query.message.delete()

#=====================================================================================##


user_message_count = {}
user_banned_until = {}

MAX_MESSAGES = 3
TIME_WINDOW = timedelta(seconds=10)  # Capturing frames
BAN_DURATION = timedelta(hours=1)  # User ko ban rakhne ka time. hours ko minutes karlena

@Client.on_message(filters.private)
async def monitor_messages(client: Client, message: Message):
    user_id = message.from_user.id
    now = datetime.now()

    if user_id in ADMINS:
        return 

    
    if user_id in user_banned_until and now < user_banned_until[user_id]:
        await message.reply_text("⚠️ You are temporarily banned from using commands due to spamming. Try again later.")
        return

    if user_id not in user_message_count:
        user_message_count[user_id] = []

    user_message_count[user_id].append(now)

    user_message_count[user_id] = [time for time in user_message_count[user_id] if now - time <= TIME_WINDOW]

    if len(user_message_count[user_id]) > MAX_MESSAGES:
        user_banned_until[user_id] = now + BAN_DURATION
        await message.reply_text("🚫 You have been temporarily banned for spamming. Try again in 1 hour.")
        return

async def revoke_invite_after_10_minutes(client: Client, channel_id: int, invite_link: str, is_request: bool):
    await asyncio.sleep(600)  # Sleep for 10 minutes
    try:
        await client.revoke_chat_invite_link(chat_id=channel_id, invite_link=invite_link)
    except Exception as e:
        print(f"Error revoking invite link: {e}")

