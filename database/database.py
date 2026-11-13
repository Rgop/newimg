import motor.motor_asyncio
import base64
from config import DB_URI, DB_NAME
from datetime import datetime, timedelta

dbclient = motor.motor_asyncio.AsyncIOMotorClient(DB_URI)
database = dbclient[DB_NAME]

user_data = database['users']
channels_collection = database["channels"]
encoded_links_collection = database["links"]
banned_users_collection = database["banned_users"]

async def add_user(user_id: int):
    existing_user = await user_data.find_one({'_id': user_id})
    if existing_user:
        return 
    
    try:
        await user_data.insert_one({'_id': user_id})
    except Exception as e:
        print(f"Error adding user {user_id}: {e}")

async def present_user(user_id: int):
    found = await user_data.find_one({'_id': user_id})
    return bool(found)

async def full_userbase():
    user_docs = user_data.find()
    return [doc['_id'] async for doc in user_docs]

async def del_user(user_id: int):
    await user_data.delete_one({'_id': user_id})

##-------------------------------------------------------------------

async def is_admin(user_id: int):
    return bool(await admins_collection.find_one({'_id': user_id}))

##-------------------------------------------------------------------

async def save_channel(channel_id: int):
    """Save a channel_id to the database with invite link expiration."""
    await channels_collection.update_one(
        {"channel_id": channel_id},
        {"$set": {"channel_id": channel_id, "invite_link_expiry": None}}, 
        upsert=True
    )

async def get_channels():
    """Get all channels from the database (No limit)"""
    channels = await channels_collection.find().to_list(None) 
    return [channel["channel_id"] for channel in channels]


async def delete_channel(channel_id: int):
    """Delete a channel from the database"""
    await channels_collection.delete_one({"channel_id": channel_id})

##-------------------------------------------------------------------

async def save_encoded_link(channel_id: int):
    encoded_link = base64.urlsafe_b64encode(str(channel_id).encode()).decode()
    await channels_collection.update_one(
        {"channel_id": channel_id},
        {"$set": {"encoded_link": encoded_link, "status": "active"}},
        upsert=True
    )
    return encoded_link


async def get_channel_by_encoded_link(encoded_link: str):
    channel = await channels_collection.find_one({"encoded_link": encoded_link, "status": "active"})
    return channel["channel_id"] if channel else None

##-------------------------------------------------------------------

async def save_encoded_link2(channel_id: int, encoded_link: str):
    await channels_collection.update_one(
        {"channel_id": channel_id},
        {"$set": {"req_encoded_link": encoded_link, "status": "active"}},
        upsert=True
    )
    return encoded_link

async def get_channel_by_encoded_link2(encoded_link: str):
    channel = await channels_collection.find_one({"req_encoded_link": encoded_link, "status": "active"})
    return channel["channel_id"] if channel else None

async def save_channel_photo(channel_id: int, photo_link: str):
    """Save/Update the photo link for a channel."""
    await channels_collection.update_one(
        {"channel_id": channel_id},
        {"$set": {"photo_link": photo_link}},
        upsert=True
    )

async def get_channel_photo_link(channel_id: int):
    """Return the stored photo link for a channel, if any."""
    channel = await channels_collection.find_one({"channel_id": channel_id})
    if not channel:
        return None
    return channel.get("photo_link")

##-------------------------------------------------------------------

async def ban_user(user_id: int):
    """Ban a user from using the bot."""
    await banned_users_collection.insert_one({"_id": user_id, "banned_at": datetime.now()})

async def unban_user(user_id: int):
    """Unban a user."""
    await banned_users_collection.delete_one({"_id": user_id})

async def is_user_banned(user_id: int):
    """Check if a user is banned."""
    return bool(await banned_users_collection.find_one({"_id": user_id}))

async def get_all_banned_users():
    """Get list of all banned users."""
    banned = await banned_users_collection.find().to_list(None)
    return [doc["_id"] for doc in banned]
    

# Force Subscribe persistence. These collections are additive and preserve the
# existing users/channels/links architecture.
fsub_config_collection = database['fsub_config']
fsub_status_collection = database['fsub_status']
join_requests_collection = database['join_requests']

async def set_fsub_channels(channels: dict):
    await fsub_config_collection.update_one(
        {'_id': 'channels'}, {'$set': {'channels': channels}}, upsert=True
    )

async def get_fsub_channels() -> dict:
    doc = await fsub_config_collection.find_one({'_id': 'channels'})
    return (doc or {}).get('channels', {})

async def add_fsub_channel(channel_id: int, data):
    channels = await get_fsub_channels()
    channels[str(channel_id)] = data
    await set_fsub_channels(channels)

async def remove_fsub_channel(channel_id: int):
    channels = await get_fsub_channels()
    channels.pop(str(channel_id), None)
    await set_fsub_channels(channels)

async def update_fsub_status(user_id: int, channel_id: int, status: str):
    await fsub_status_collection.update_one(
        {'user_id': user_id, 'channel_id': channel_id},
        {'$set': {'status': status, 'last_updated': datetime.now()}}, upsert=True
    )

async def get_fsub_status(user_id: int, channel_id: int):
    doc = await fsub_status_collection.find_one({'user_id': user_id, 'channel_id': channel_id})
    return doc.get('status') if doc else None

async def add_channel_user(channel_id: int, user_id: int):
    await channels_collection.update_one(
        {'channel_id': channel_id}, {'$addToSet': {'users': user_id}}, upsert=True
    )

async def remove_channel_user(channel_id: int, user_id: int):
    await channels_collection.update_one(
        {'channel_id': channel_id}, {'$pull': {'users': user_id}}
    )

async def add_join_request(user_id: int, channel_id: int, request_id=None):
    await join_requests_collection.update_one(
        {'user_id': user_id, 'channel_id': channel_id},
        {'$set': {'request_id': request_id, 'status': 'pending',
                  'submitted_at': datetime.now(), 'last_updated': datetime.now()}},
        upsert=True
    )

async def update_join_request_status(user_id: int, channel_id: int, status: str):
    await join_requests_collection.update_one(
        {'user_id': user_id, 'channel_id': channel_id},
        {'$set': {'status': status, 'last_updated': datetime.now()}}
    )

async def get_join_request_status(user_id: int, channel_id: int):
    doc = await join_requests_collection.find_one({'user_id': user_id, 'channel_id': channel_id})
    return doc.get('status') if doc else None

async def has_submitted_join_request(user_id: int, channel_id: int) -> bool:
    return await join_requests_collection.find_one(
        {'user_id': user_id, 'channel_id': channel_id}
    ) is not None

async def remove_join_request(user_id: int, channel_id: int):
    await join_requests_collection.delete_one({'user_id': user_id, 'channel_id': channel_id})
