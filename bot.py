import asyncio
import sys
from datetime import datetime
from pyrogram import Client
from pyrogram.enums import ParseMode
from config import API_HASH, APP_ID, LOGGER, TG_BOT_TOKEN, TG_BOT_WORKERS, PORT
from plugins import web_server
import pyrogram.utils
from aiohttp import web
from database.database import get_fsub_channels
pyrogram.utils.MIN_CHANNEL_ID = -1009147483647

name = """
Links Sharing Started
"""

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="Bot",
            api_hash=API_HASH,
            api_id=APP_ID,
            plugins={"root": "plugins"},
            workers=TG_BOT_WORKERS,
            bot_token=TG_BOT_TOKEN,
        )
        self.LOGGER = LOGGER

    async def start(self, use_qr=None, except_ids=None, *args, **kwargs):
        await super().start(*args, use_qr=use_qr, except_ids=except_ids, **kwargs)
        usr_bot_me = await self.get_me()
        self.uptime = datetime.now()

        self.set_parse_mode(ParseMode.HTML)
        self.LOGGER(__name__).info("Bot Running..!\n\nCreated by \nhttps://t.me/Okabe_xRintarou")
        self.LOGGER(__name__).info(f"{name}")
        self.username = usr_bot_me.username
        stored_fsub = await get_fsub_channels()
        self.fsub_dict = {int(channel_id): data for channel_id, data in stored_fsub.items()}
        self.fsub_enabled = True
        self.fsub_message = None
        self.fsub_photo = ""

        # Web-response
        app = web.AppRunner(await web_server())
        await app.setup()
        bind_address = "0.0.0.0"
        await web.TCPSite(app, bind_address, PORT).start()

    async def stop(self, *args):
        await super().stop()
        self.LOGGER(__name__).info("Bot stopped.")
