import asyncio
from datetime import datetime, timedelta
from functools import wraps

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import RPCError

from config import ADMINS, OWNER_ID
from database.database import (
    get_fsub_channels, get_fsub_status, get_join_request_status,
)


def is_fsub_admin(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in ADMINS


def _channel_value(data, key, index, default=None):
    if isinstance(data, dict):
        return data.get(key, default)
    try:
        return data[index]
    except (IndexError, TypeError):
        return default


def _is_active_member(member) -> bool:
    return getattr(member, "status", None) in {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
        ChatMemberStatus.RESTRICTED,
    }


async def _has_access(client, user_id: int, channel_id: int, data) -> bool:
    request_mode = bool(_channel_value(data, "request", 2, False))
    try:
        member = await client.get_chat_member(channel_id, user_id)
        if _is_active_member(member):
            return True
    except RPCError:
        pass

    if request_mode:
        status = await get_join_request_status(user_id, channel_id)
        return status in {"pending", "request_submitted", "approved", "joined"}
    return False


async def _invite_for(client, channel_id: int, data):
    request_mode = bool(_channel_value(data, "request", 2, False))
    timer = int(_channel_value(data, "timer", 3, 0) or 0)
    kwargs = {"chat_id": channel_id, "creates_join_request": request_mode}
    if timer > 0:
        kwargs["expire_date"] = datetime.now() + timedelta(minutes=timer)
    invite = await client.create_chat_invite_link(**kwargs)
    if timer > 0:
        asyncio.create_task(_revoke_after(client, channel_id, invite.invite_link, timer * 60))
    return invite.invite_link


async def _revoke_after(client, channel_id, invite_link, seconds):
    await asyncio.sleep(seconds)
    try:
        await client.revoke_chat_invite_link(channel_id, invite_link)
    except RPCError:
        pass


async def send_fsub_prompt(client, message):
    rows = []
    for channel_id, data in client.fsub_dict.items():
        name = _channel_value(data, "name", 0, str(channel_id))
        try:
            link = await _invite_for(client, channel_id, data)
            rows.append([InlineKeyboardButton(f"Join {name}", url=link)])
        except RPCError:
            continue
    rows.append([InlineKeyboardButton("Try Again", callback_data="fsub_try")])
    text = getattr(client, "fsub_message", None) or (
        "<b>Join all required channels, then tap <i>Try Again</i> to continue.</b>"
    )
    photo = getattr(client, "fsub_photo", "")
    markup = InlineKeyboardMarkup(rows)
    if photo:
        return await client.send_photo(message.chat.id, photo=photo, caption=text, reply_markup=markup)
    return await message.reply_text(text, reply_markup=markup)


async def check_force_sub(client, message, user_id=None) -> bool:
    if not getattr(client, "fsub_enabled", True) or not client.fsub_dict:
        return True
    user_id = user_id or message.from_user.id
    if is_fsub_admin(user_id):
        return True
    for channel_id, data in client.fsub_dict.items():
        if not await _has_access(client, user_id, channel_id, data):
            await send_fsub_prompt(client, message)
            return False
    return True


def force_sub(func):
    @wraps(func)
    async def wrapped(client, message, *args, **kwargs):
        if not await check_force_sub(client, message):
            return
        return await func(client, message, *args, **kwargs)
    return wrapped


@Client.on_callback_query(filters.regex(r"^fsub_try$"))
async def fsub_try(client, query: CallbackQuery):
    if await check_force_sub(client, query.message, query.from_user.id):
        await query.answer("Verified. Please retry your command.", show_alert=True)
        try:
            await query.message.delete()
        except RPCError:
            pass
    else:
        await query.answer("You must join every required channel first.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^fsub$"))
async def fsub_panel(client, query: CallbackQuery):
    if not is_fsub_admin(query.from_user.id):
        return await query.answer("Admins only.", show_alert=True)
    lines = []
    for channel_id, data in client.fsub_dict.items():
        name = _channel_value(data, "name", 0, "Unknown")
        req = "Join Request" if _channel_value(data, "request", 2, False) else "Normal Join"
        timer = int(_channel_value(data, "timer", 3, 0) or 0)
        lines.append(f"• <b>{name}</b> <code>{channel_id}</code> — {req}, timer: {'∞' if timer == 0 else f'{timer}m'}")
    text = "<b>Force Subscribe Channels</b>\n\n" + ("\n".join(lines) if lines else "<i>None configured.</i>")
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("Add channel", callback_data="add_fsub"), InlineKeyboardButton("Remove channel", callback_data="rm_fsub")],
        [InlineKeyboardButton("Toggle enabled", callback_data="toggle_fsub")],
        [InlineKeyboardButton("Back", callback_data="settings")],
    ])
    await query.message.edit_text(text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^(add_fsub|rm_fsub|toggle_fsub)$"))
async def fsub_admin_action(client, query: CallbackQuery):
    if not is_fsub_admin(query.from_user.id):
        return await query.answer("Admins only.", show_alert=True)
    action = query.data
    await query.answer()
    if action == "toggle_fsub":
        client.fsub_enabled = not getattr(client, "fsub_enabled", True)
        await query.message.edit_text(f"Force Subscribe is now {'enabled' if client.fsub_enabled else 'disabled'}.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="settings")]]))
        return
    prompt = "Send channel ID, request mode (yes/no), and timer in minutes. Example: <code>-1001234567890 yes 5</code>" if action == "add_fsub" else "Send the channel ID to remove."
    await query.message.edit_text(prompt)
    try:
        answer = await client.ask(query.from_user.id, prompt, filters=filters.text, timeout=60)
        parts = answer.text.split()
        channel_id = int(parts[0])
        if action == "rm_fsub":
            if channel_id not in client.fsub_dict:
                return await answer.reply_text("That channel is not configured.")
            client.fsub_dict.pop(channel_id, None)
            from database.database import remove_fsub_channel
            await remove_fsub_channel(channel_id)
            return await answer.reply_text("Force Subscribe channel removed.")
        if len(parts) != 3 or parts[1].lower() not in {"yes", "no", "true", "false", "on", "off"}:
            raise ValueError("Use: channel_id yes/no timer")
        chat = await client.get_chat(channel_id)
        request_mode = parts[1].lower() in {"yes", "true", "on"}
        timer = int(parts[2])
        if timer < 0:
            raise ValueError("Timer cannot be negative")
        record = {"name": chat.title or str(channel_id), "link": None, "request": request_mode, "timer": timer}
        if timer == 0:
            record["link"] = (await _invite_for(client, channel_id, record))
        client.fsub_dict[channel_id] = record
        from database.database import add_fsub_channel
        await add_fsub_channel(channel_id, record)
        await answer.reply_text(f"Added <b>{chat.title}</b> as a Force Subscribe channel.")
    except Exception as exc:
        await query.message.reply_text(f"Could not update Force Subscribe: <code>{exc}</code>")
