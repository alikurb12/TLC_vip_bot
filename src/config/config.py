import os
from dotenv import load_dotenv

class Config:
    def __init__(self):
        load_dotenv()
        self.bot_token = os.getenv("BOT_TOKEN")
        self.crypto_bot_token = os.getenv("CRYPTO_BOT_TOKEN")
        self.db_config = {
            "host": os.getenv("DB_HOST"),
            "port": os.getenv("DB_PORT"),
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD"),
            "database": os.getenv("DB_NAME")
        }

    def validate(self):
        if not all([
            self.bot_token,
            self.crypto_bot_token,
            self.db_config["host"],
            self.db_config["port"],
            self.db_config["user"],
            self.db_config["password"],
            self.db_config["database"]
        ]):
            raise ValueError("Не все переменные окружения заданы")

config = Config()