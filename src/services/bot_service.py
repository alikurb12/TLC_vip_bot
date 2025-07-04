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
        "regular": {
            "test": {"days": 1, "price": 5, "name": "Тестовый (1 день)"},
            "1month": {"days": 30, "price": 70, "name": "1 месяц"},
            "3months": {"days": 90, "price": 160, "name": "3 месяца (Выгода 50$)"},
            "6months": {"days": 180, "price": 320, "name": "6 месяцев (Выгода 100$)"},
            "12months": {"days": 365, "price": 640, "name": "12 месяцев (Выгода 200$)"}
        },
        "referral": {
            "test": {"days": 1, "price": 2.5, "name": "Тестовый (1 день, реферал)"},
            "1month": {"days": 30, "price": 35, "name": "1 месяц (реферал)"},
            "3months": {"days": 90, "price": 80, "name": "3 месяца (реферал, Выгода 25$)"},
            "6months": {"days": 180, "price": 160, "name": "6 месяцев (реферал, Выгода 50$)"},
            "12months": {"days": 365, "price": 320, "name": "12 месяцев (реферал, Выгода 100$)"}
        }
    }

    SUPPORTED_EXCHANGES = ["Binance", "Bybit", "Kraken", "OKX"]

    def __init__(self, repo: Repository, crypto_service: CryptoService, logger: Logger):
        self.repo = repo
        self.crypto_service = crypto_service
        self.logger = logger

    def get_profile_text(self, user: User) -> str:
        if not user:
            return (
                "👤 <b>Ваш профиль</b>\n"
                "Статус подписки: <b>Отсутствует</b>\n"
                "Пожалуйста, выберите тип подписки."
            )
        subscription_status = (
            f"Активна до: <b>{user.subscription_end.strftime('%Y-%m-%d %H:%M:%S')}</b>"
            if user.subscription_end and user.subscription_end > datetime.now()
            else "Истекла или отсутствует"
        )
        subscription_type = (
            "Реферальная" if user.is_referral else "Обычная" if user.subscription_type else "Не выбрана"
        )
        exchange_info = user.exchange if user.exchange else "Не указана"
        api_key_info = "Установлен" if user.api_key else "Не установлен"
        return (
            f"👤 <b>Ваш профиль</b>\n"
            f"ID: <b>{user.user_id}</b>\n"
            f"Username: <b>@{user.username}</b>\n"
            f"Тип подписки: <b>{subscription_type}</b>\n"
            f"Статус подписки: <b>{subscription_status}</b>\n"
            f"Биржа: <b>{exchange_info}</b>\n"
            f"API-ключ: <b>{api_key_info}</b>"
        )

    async def request_exchange(self, user_id: int, message: types.Message, bot: Bot):
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=exchange, callback_data=f"exchange:{exchange}")]
            for exchange in self.SUPPORTED_EXCHANGES
        ])
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(text="📞 Поддержка", callback_data="support"),
            types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
        ])
        await bot.send_message(
            user_id,
            "Выберите биржу, с которой вы работаете:",
            reply_markup=keyboard
        )

    async def request_api_key(self, user_id: int, message: types.Message, bot: Bot):
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
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
            reply_markup=keyboard
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
        user = self.repo.get_user(user_id)
        subscription_type = user.subscription_type if user and user.subscription_type else "regular"
        tariff = self.TARIFFS[subscription_type].get(tariff_id)
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
            [types.InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_payment:{tariff_id}")],
            [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
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
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            await message.answer("Вернитесь в главное меню:", reply_markup=keyboard)
            return

        invoice = self.crypto_service.check_invoice(payment.invoice_id)
        if not invoice or not invoice.get("ok") or not invoice["result"]["items"]:
            self.logger.error("Ошибка проверки статуса платежа")
            await message.answer("Ошибка при проверке статуса платежа. Попробуйте позже.")
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            await message.answer("Вернитесь в главное меню:", reply_markup=keyboard)
            return

        if invoice["result"]["items"][0]["status"] != "paid":
            await message.answer("Платеж еще не подтвержден. Попробуйте снова.")
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🏠 Главое меню", callback_data="main_menu")]
            ])
            await message.answer("Вернитесь в главное меню:", reply_markup=keyboard)
            return

        amount = float(invoice["result"]["items"][0]["amount"])
        self.logger.info(f"Полученная сумма платежа: {amount}, tariff_id: {tariff_id}")
        user = self.repo.get_user(user_id)
        subscription_type = user.subscription_type if user and user.subscription_type else "regular"
        tariff_id = next((tid for tid, t in self.TARIFFS[subscription_type].items() if abs(t["price"] - amount) < 0.01), None)
        if not tariff_id:
            self.logger.error(f"Ошибка определения тарифа для суммы: {amount}")
            await message.answer("Ошибка определения тарифа. Свяжитесь с поддержкой.")
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            await message.answer("Вернитесь в главное меню:", reply_markup=keyboard)
            return

        current = datetime.now()
        if user and user.subscription_end and user.subscription_end > current:
            current = user.subscription_end

        new_end = current + timedelta(days=self.TARIFFS[subscription_type][tariff_id]["days"])
        user = User(
            user_id=user_id,
            subscription_end=new_end,
            exchange=user.exchange if user else None,
            api_key=user.api_key if user else None,
            username=username or (user.username if user else None),
            is_referral=user.is_referral if user else False,
            subscription_type=subscription_type
        )
        try:
            self.repo.save_user(user)
            self.repo.update_payment_status(payment.invoice_id, "paid")
        except Exception as e:
            self.logger.error(f"Ошибка обновления подписки: {e}")
            await message.answer("Ошибка при обновлении подписки.")
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            await message.answer("Вернитесь в главное меню:", reply_markup=keyboard)
            return

        await message.answer(
            f"✅ Оплата подтверждена! Ваша подписка активна до: <b>{new_end.strftime('%Y-%m-%d %H:%M:%S')}</b>",
            parse_mode="HTML"
        )
        profile_text = self.get_profile_text(user)
        keyboard = self.get_profile_keyboard(user)
        await bot.send_message(user_id, profile_text, parse_mode="HTML", reply_markup=keyboard)
        
        if not user.exchange:
            await self.request_exchange(user_id, message, bot)

    async def check_subscriptions(self, bot: Bot):
        while True:
            try:
                expired_users = self.repo.get_expired_users()
                for user in expired_users:
                    try:
                        await bot.send_message(user.user_id, "Ваша подписка истекла. Пожалуйста, продлите её.")
                    except TelegramForbiddenError:
                        self.logger.error(f"Бот заблокирован пользователем {user.user_id}")
                    except Exception as e:
                        self.logger.error(f"Ошибка отправки сообщения пользователю {user.user_id}: {e}")
                    self.repo.delete_user(user.user_id)
            except Exception as e:
                self.logger.error(f"Ошибка проверки подписок: {e}")
            await asyncio.sleep(3600)