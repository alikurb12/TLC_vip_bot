import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, types
from aiogram.exceptions import TelegramForbiddenError
from aiogram.enums import ChatMemberStatus
from src.models.user import User
from src.models.payments import Payment
from src.repositories.db import Repository
from src.services.crypto_service import CryptoService
from src.logger.logger import Logger

class BotService:
    TARIFFS = {
        "test" : {"days" : 1, "price" : 5, "name" : "Тестовый (1 день)"},
        "1month" : {"days" : 30, "price" : 70, "name" : "1 месяц"},
        "3months" : {"days" : 90, "price" : 180, "name" : "3 месяца (Выгода 50$)"},
        "6months" : {"days" : 180, "price" : 320, "name" : "6 месяцев (Выгода 100$)"},
        "12 months" : {"days" : 365, "price" : 600, "name" : "12 месяцев (Выгода 200$)"}
    }

    SUPPORTED_EXCHANGES = ["Binance", "Bybit", "OKX", "BingX"]
    def __init__(self, repo: Repository, crypto_service: CryptoService, group_id: int, logger: Logger):
        self.repo = repo
        self.crypto_service = crypto_service
        self.group_id = group_id
        self.logger = logger
    
    async def is_bot_in_group(self, bot: Bot) -> bool:
        try:
            member = await bot.get_chat_member(chat_id=self.group_id, user_id=bot.id)
            return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]
        except TelegramForbiddenError:
            self.logger.error("Бот не добавлен в группу или не имеет доступа")
            return False
        except Exception as e:
            self.logger.error(f"Ошибка при проверке статуса бота в группе: {e}")
            return False
    
    async def request_exchange(self, user_id: int, message: types.Message, bot: Bot):
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for exchange in self.SUPPORTED_EXCHANGES:
            keyboard.add(types.KeyboardButton(exchange))
        await bot.send_message(
            chat_id=user_id,
            text="Выберите биржу для получения торговых сигналов:",
            reply_markup=keyboard
        )
        self.logger.info(f"Пользователь {user_id} запрашивает биржу для торговых сигналов")
    
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
        user.username = username
        try:
            self.repo.save_user(user)
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении биржи для {user_id}: {e}")
            raise
        self.logger.info(f"Биржа и API-ключ успешно сохранены для пользователя {user_id}")

    async def process_payment(self, user_id: int, tariff_id: str, message: types.Message, bot: Bot):
        tariff = self.TARIFFS.get(tariff_id)
        if not tariff:
            await message.answer("Неверный Тариф. Пожалуйста, выберите один из доступных тарифов.")
            return
        
        invoice = self.crypto_service.create_invoice(user_id, tariff["price"], tariff["name"])
        if not invoice or not invoice.get("ok") or "result" not in invoice:
            self.logger.error("Ошибка создания инвойса")
            await message.answer("Ошибка при создании платежа. Пожалуйста, попробуйте позже.")
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
            self.logger.error(f"Ошибка при сохранении платежа для пользователя {user_id}: {e}")
            await message.answer("Ошибка при сохранении платежа. Пожалуйста, попробуйте позже.")
            return
        self.logger.info(f"Платеж для пользователя {user_id} успешно сохранен с инвойсом {invoice_id}")
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Проверить оплату", callback_data="check_payment")],
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

    async def check_payment(self, user_id: int, message: types.Message, bot: Bot, username: str = None):
        payment = self.repo.get_latest_payment(user_id)
        if not payment:
            await message.answer("У вас нет активных платежей. Пожалуйста, создайте новый платеж.")
            return

        invoice = self.crypto_service.check_invoice(payment.invoice_id)
        if not invoice or not invoice.get("ok:") or not invoice["result"]["items"]:
            self.logger.error(f"Ошибка при проверке инвойса {payment.invoice_id} для пользователя {user_id}")
            await message.answer("Ошибка при проверке статуса платежа. Пожалуйста, попробуйте позже.")
            return

        if invoice["result"]["items"][0]["status"] != "paid":
            await message.answer("Ваш платеж еще не подтвержден. Пожалуйста, подождите.")
            return
        
        amount = float(invoice["result"]["items"][0]["amount"])
        tariff_id = next((tid for tid, t in self.TARIFFS.items() if abs(t["price"] - amount) < 0.01), None)
        if not tariff_id:
            self.logger.error(f"Ошибка определения тарифа для суммы {amount} для пользователя {user_id}")
            await message.answer("Ошибка при определении тарифа. Пожалуйста, свяжитесь с поддержкой.")
            return
        
        user = self.repo.get_user(user_id)
        current = datetime.now()
        if user and user.description_end and user.description_end > current:
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
            self.logger.error(f"Ошибка при сохранении пользователя {user_id} после оплаты: {e}")
            await message.answer("Ошибка при обновлении вашего статуса. Пожалуйста, попробуйте позже.")
            return
        self.logger.info(f"Пользователь {user_id} успешно оплатил тариф {tariff_id} до {new_end}")

        try:
            invite_link = await bot.export_chat_invite_link(
                chat_id=self.group_id,
                expire_date = datetime.now() + timedelta(days=1),
                member_limit = 1,
                creates_join_request = False
            )
            await message.answer(
                f"✅ Оплата подтверждена! Ваша подписка до: <b>{new_end.strftime('%Y-%m-%d %H:%M:%S')}</b>\n"
                f"🔗 <b>Ссылка для входа в группу:</b> <a href='{invite_link.invite_link}'>нажмите сюда</a>",
                parse_mode="HTML"
            )
            if not user or not user.exchange:
                await self.request_exchange(user_id, message, bot)
        except Exception as e:
            self.logger.error(f"Ошибка при отправке ссылки на группу пользователю {user_id}: {e}")
            await message.answer("Ошибка при отправке ссылки на группу. Пожалуйста, свяжитесь с поддержкой. @TradersLiveCommunity")
            return
        
    async def check_subscriptions(self, bot: Bot):
        while True:
            try:
                expired_users = self.repo.get_expired_users()
                for user_id in expired_users:
                    try:
                        member = await bot.get_chat_member(chat_id=self.group_id, user_id=user_id)
                        if member.status not in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
                            await bot.ban_chat_member(chat_id=self.group_id, user_id=user_id)
                        self.repo.delete_user(user_id)
                        try:
                            await bot.send_message(user_id, "Ваша подписка истекла. Пожалуйста, продлите её.")
                        except TelegramForbiddenError:
                            self.logger.error(f"Бот заблокирован пользователем {user_id}")
                        except Exception as e:
                            self.logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
                    except TelegramForbiddenError:
                        self.logger.info(f"Пользователь {user_id} заблокировал бота, удаляем из базы")
                        self.repo.delete_user(user_id)
                    except Exception as e:
                        self.logger.error(f"Ошибка обработки истекшей подписки для {user_id}: {e}")
            except Exception as e:
                self.logger.error(f"Ошибка проверки подписок: {e}")
            await asyncio.sleep(3600)