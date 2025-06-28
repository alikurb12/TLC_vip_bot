import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, types
from aiogram.exceptions import TelegramForbiddenError
from models.user import User
from models.payment import Payment
from repositories.db import Repository
from services.crypto_service import CryptoService
from logger.logger import Logger

class BotService:
    TARIFFS = {
        "test": {"days": 1, "price": 5, "name": "Тестовый (1 день)"},
        "1month": {"days": 30, "price": 70, "name": "1 месяц"},
        "3months": {"days": 90, "price": 160, "name": "3 месяца (Выгода 50$)"},
        "6months": {"days": 180, "price": 320, "name": "6 месяцев (Выгода 100$)"},
        "12months": {"days": 365, "price": 640, "name": "12 месяцев (Выгода 200$)"}
    }

    SUPPORTED_EXCHANGES = ["Binance", "Bybit", "Kraken", "OKX"]

    def __init__(self, repo: Repository, crypto_service: CryptoService, logger: Logger):
        self.repo = repo
        self.crypto_service = crypto_service
        self.logger = logger

    async def request_exchange(self, user_id: int, message: types.Message, bot: Bot):
        keyboard = types.ReplyKeyboardMarkup(
            keyboard=[
                [types.KeyboardButton(text=exchange)] for exchange in self.SUPPORTED_EXCHANGES
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await bot.send_message(
            user_id,
            "Выберите биржу, с которой вы работаете:",
            reply_markup=keyboard
        )

    async def request_api_key(self, user_id: int, message: types.Message, bot: Bot):
        await bot.send_message(
            user_id,
            "Пожалуйста, предоставьте API-ключ для выбранной биржи.\n\n"
            "🔒 <b>О безопасности:</b>\n"
            "1. Мы используем ваш API-ключ только для чтения данных (например, баланса или торговой истории).\n"
            "2. Ваш ключ надежно хранится и не передается третьим лицам.\n"
            "3. Мы не можем использовать ваш API-ключ для вывода средств или других действий без вашего явного разрешения.\n"
            "4. Убедитесь, что ваш API-ключ настроен только с правами на чтение (без прав на торговлю или вывод).\n\n"
            "Введите API-ключ:",
            parse_mode="HTML",
            reply_markup=types.ReplyKeyboardRemove()
        )

    async def save_exchange_and_api(self, user_id: int, exchange: str, api_key: str, username: str = None):
        user = self.repo.get_user(user_id) or User(user_id=user_id, username=username)
        user.exchange = exchange
        user.api_key = api_key
        user.username = username or user.username
        self.logger.info(f"Попытка сохранить данные пользователя: user_id={user_id}, exchange={exchange}, api_key={api_key}, username={user.username}")
        try:
            self.repo.save_user(user)
            self.logger.info(f"Данные пользователя {user_id} успешно сохранены")
        except Exception as e:
            self.logger.error(f"Ошибка сохранения биржи и API для {user_id}: {str(e)}")
            raise

    async def process_payment(self, user_id: int, tariff_id: str, message: types.Message, bot: Bot):
        tariff = self.TARIFFS.get(tariff_id)
        if not tariff:
            await message.answer("Неверный тариф.")
            return

        invoice = self.crypto_service.create_invoice(user_id, tariff["price"], tariff["name"])
        if not invoice or not invoice.get("ok") or "result" not in invoice:
            self.logger.error("Ошибка создания инвойса")
            await message.answer("Ошибка при создании платежа. Попробуйте позже.")
            return

        invoice_id = invoice["result"]["invoice_id"]
        pay_url = invoice["result"]["pay_url"]

        payment = Payment(
            invoice_id=invoice_id,
            user_id=user_id,
            amount=tariff["price"],
            currency="USDT",
            status="created"
        )
        try:
            self.repo.save_payment(payment)
        except Exception as e:
            self.logger.error(f"Ошибка сохранения платежа: {e}")
            await message.answer("Ошибка при сохранении платежа.")
            return

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_payment:{tariff_id}")]
        ])
        await bot.send_message(
            user_id,
            f"💳 Оплатите {tariff['price']}$ за тариф <b>{tariff['name']}</b>\n"
            f"🔗 <a href='{pay_url}'>Ссылка для оплаты</a>\n\n"
            f"После оплаты нажмите кнопку ниже:",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await message.delete()

    async def check_payment(self, user_id: int, message: types.Message, bot: Bot, username: str = None, tariff_id: str = None):
        payment = self.repo.get_last_payment(user_id)
        if not payment:
            await message.answer("У вас нет активных платежей для проверки.")
            return

        invoice = self.crypto_service.check_invoice(payment.invoice_id)
        if not invoice or not invoice.get("ok") or not invoice["result"]["items"]:
            self.logger.error("Ошибка проверки статуса платежа")
            await message.answer("Ошибка при проверке статуса платежа. Попробуйте позже.")
            return

        if invoice["result"]["items"][0]["status"] != "paid":
            await message.answer("Платеж еще не подтвержден. Попробуйте снова.")
            return

        amount = float(invoice["result"]["items"][0]["amount"])
        self.logger.info(f"Полученная сумма платежа: {amount}, tariff_id: {tariff_id}")
        tariff_id = next((tid for tid, t in self.TARIFFS.items() if abs(t["price"] - amount) < 0.01), None)
        if not tariff_id:
            self.logger.error(f"Ошибка определения тарифа для суммы: {amount}")
            await message.answer("Ошибка определения тарифа. Свяжитесь с поддержкой.")
            return

        user = self.repo.get_user(user_id)
        current = datetime.now()
        if user and user.subscription_end and user.subscription_end > current:
            current = user.subscription_end

        new_end = current + timedelta(days=self.TARIFFS[tariff_id]["days"])
        user = User(
            user_id=user_id,
            subscription_end=new_end,
            exchange=user.exchange if user else None,
            api_key=user.api_key if user else None,
            username=username or (user.username if user else None)
        )
        try:
            self.repo.save_user(user)
            self.repo.update_payment_status(payment.invoice_id, "paid")
        except Exception as e:
            self.logger.error(f"Ошибка обновления подписки: {e}")
            await message.answer("Ошибка при обновлении подписки.")
            return

        await message.answer(
            f"✅ Оплата подтверждена! Ваша подписка активна до: <b>{new_end.strftime('%Y-%m-%d %H:%M:%S')}</b>",
            parse_mode="HTML"
        )
        # Запрашиваем биржу после успешной оплаты, если она еще не указана
        if not user or not user.exchange:
            await self.request_exchange(user_id, message, bot)

    async def check_subscriptions(self, bot: Bot):
        while True:
            try:
                expired_users = self.repo.get_expired_users()
                for user_id in expired_users:
                    try:
                        await bot.send_message(user_id, "Ваша подписка истекла. Пожалуйста, продлите её.")
                    except TelegramForbiddenError:
                        self.logger.error(f"Бот заблокирован пользователем {user_id}")
                    except Exception as e:
                        self.logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
                    self.repo.delete_user(user_id)
            except Exception as e:
                self.logger.error(f"Ошибка проверки подписок: {e}")
            await asyncio.sleep(3600)  # Проверка каждый час