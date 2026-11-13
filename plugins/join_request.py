from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import ChatJoinRequest, ChatMemberUpdated

from database.database import (
    add_user, add_channel_user, remove_channel_user, add_join_request,
    update_fsub_status, update_join_request_status, has_submitted_join_request,
    remove_join_request,
)


def _active(status):
    return status in {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
        ChatMemberStatus.RESTRICTED,
    }


@Client.on_chat_join_request(filters.channel)
async def handle_join_request(client, request: ChatJoinRequest):
    channel_id = request.chat.id
    if channel_id not in getattr(client, "fsub_dict", {}):
        return
    user_id = request.from_user.id
    await add_user(user_id)
    await add_join_request(user_id, channel_id, getattr(request, "id", None))
    await update_fsub_status(user_id, channel_id, "request_submitted")
    await add_channel_user(channel_id, user_id)


@Client.on_chat_member_updated(filters.channel)
async def handle_member_update(client, update: ChatMemberUpdated):
    channel_id = update.chat.id
    if channel_id not in getattr(client, "fsub_dict", {}):
        return
    user = update.new_chat_member.user
    user_id = user.id
    old = getattr(update.old_chat_member, "status", None)
    new = getattr(update.new_chat_member, "status", None)
    await add_user(user_id)
    if _active(new) and not _active(old):
        await update_fsub_status(user_id, channel_id, "joined")
        await add_channel_user(channel_id, user_id)
        if await has_submitted_join_request(user_id, channel_id):
            await update_join_request_status(user_id, channel_id, "approved")
    elif _active(old) and not _active(new):
        await update_fsub_status(user_id, channel_id, "left")
        await remove_channel_user(channel_id, user_id)
        await remove_join_request(user_id, channel_id)
