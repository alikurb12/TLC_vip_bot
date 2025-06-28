import requests 
from logger.logger import Logger

class CryptoService:
    def __init__(self, token: str, logger: Logger):
        self.token = token
        self.logger = logger

    def create_invoice(self, user_id: int, amount: float, description: str) -> dict:
        url = "https://pay.crypt.bot/api/createInvoice"
        headers = {"Crypto-Pay-API-Token": self.token}
        params = {
            "asset": "USDT",
            "amount": amount,
            "description": description,
            "hidden_message": "Спасибо за оплату!",
            "payload": f"user_{user_id}"
        }
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Ошибка создания инвойса: {e}")
            return None

    def check_invoice(self, invoice_id: int) -> dict:
        url = "https://pay.crypt.bot/api/getInvoices"
        headers = {"Crypto-Pay-API-Token": self.token}
        params = {"invoice_ids": invoice_id}
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Ошибка проверки инвойса {invoice_id}: {e}")
            return None