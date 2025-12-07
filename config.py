import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота (получить у @BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# ID администраторов (можно добавить несколько через запятую)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# Пути к папкам
FOLDERS = {
    "pending_review": "На проверку",
    "pending_payment": "На оплату"
}

