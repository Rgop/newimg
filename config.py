import os
from os import environ
import logging
from logging.handlers import RotatingFileHandler

#Recommended
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "8135643079:AAFKS9w4S4q3i3jkjZuWcTOPg30md-uRDd0")
APP_ID = int(os.environ.get("APP_ID", "26457673"))
API_HASH = os.environ.get("API_HASH", "bb4a4d48ea0b0e7194119b9facd96ab6")

##----------------------------------------------------------------------------------->

#Main 
OWNER_ID = int(os.environ.get("OWNER_ID", "1327021082"))
PORT = os.environ.get("PORT", "8010")

##----------------------------------------------------------------------------------->

#Database
DB_URI = os.environ.get("DATABASE_URL", "mongodb+srv://ruhan:ruhan@isrg.bzrvwbh.mongodb.net/?retryWrites=true&w=majority&appName=isrg")
DB_NAME = os.environ.get("DATABASE_NAME", "postbot")

##----------------------------------------------------------------------------------->
#Default
TG_BOT_WORKERS = int(os.environ.get("TG_BOT_WORKERS", "4"))
START_MSG = os.environ.get("START_MESSAGE", "") #No Need keep it blank
try:
    ADMINS=[]
    for x in (os.environ.get("ADMINS", "5090651635").split()):
        ADMINS.append(int(x))
except ValueError:
        raise Exception("Your Admins list does not contain valid integers.")

##---------------------------------------------------------------------------------------------------        

#Default
BOT_STATS_TEXT = "<b>BOT UPTIME</b>\n{uptime}"
USER_REPLY_TEXT = None

##---------------------------------------------------------------------------------------------------

#Admin == OWNERID
ADMINS.append(OWNER_ID)
ADMINS.append(5090651635)

##---------------------------------------------------------------------------------------------------

#Default
LOG_FILE_NAME = "links-sharingbot.txt"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%d-%b-%y %H:%M:%S',
    handlers=[
        RotatingFileHandler(
            LOG_FILE_NAME,
            maxBytes=50000000,
            backupCount=10
        ),
        logging.StreamHandler()
    ]
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)


def LOGGER(name: str) -> logging.Logger:
    return logging.getLogger(name)
   
##---------------------------------------------------------------------------------------------------
