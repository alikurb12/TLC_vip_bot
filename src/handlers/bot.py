from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from services.bot_service import BotService
from logger.logger import Logger
from datetime import datetime
from models.user import User

class PaymentStates(StatesGroup):
    waiting_for_payment = State()
    waiting_for_exchange = State()
    waiting_for_api_key = State()
    waiting_for_subscription_type = State()

class Handler:
    def __init__(self, bot: Bot, bot_service: BotService, logger: Logger):
        self.bot = bot
        self.bot_service = bot_service
        self.logger = logger
        self.router = Router()
        self.dp = Dispatcher(storage=MemoryStorage())
        self.dp.include_router(self.router)
        self.register_handlers()

    def register_handlers(self):
        self.router.message(Command("start"))(self.handle_start)
        self.router.message(Command("help"))(self.handle_help)
        self.router.callback_query(F.data.startswith("tariff:"))(self.handle_tariff)
        self.router.callback_query(F.data.startswith("check_payment:"))(self.handle_check_payment)
        self.router.callback_query(F.data.startswith("exchange:"))(self.handle_exchange)
        self.router.message(PaymentStates.waiting_for_api_key)(self.handle_api_key)
        self.router.callback_query(F.data.startswith("subscription_type:"))(self.handle_subscription_type)
        self.router.callback_query(F.data == "support")(self.handle_support)
        self.router.callback_query(F.data == "extend_subscription")(self.handle_extend_subscription)
        self.router.callback_query(F.data == "main_menu")(self.handle_main_menu)

    async def start(self):
        await self.dp.start_polling(self.bot)

    async def handle_start(self, message: types.Message, state: FSMContext):
        user_id = message.from_user.id
        username = message.from_user.username
        self.logger.info(f"Обработка команды /start для user_id: {user_id}, username: {username}")
        try:
            self.logger.info(f"Получение пользователя из базы для user_id: {user_id}")
            user = self.bot_service.repo.get_user(user_id)
            self.logger.info(f"Пользователь найден: {user}")
            if user:
                self.logger.info(f"Обновление username для существующего пользователя: {username}")
                user.username = username
                self.bot_service.repo.save_user(user)
            else:
                self.logger.info(f"Создание нового пользователя с user_id: {user_id}, username: {username}")
                user = User(user_id=user_id, username=username)
                self.bot_service.repo.save_user(user)

            profile_text = self.bot_service.get_profile_text(user)
            keyboard = self.get_profile_keyboard(user)
            
            await message.answer(profile_text, parse_mode="HTML", reply_markup=keyboard)
            await state.clear()
        except Exception as e:
            self.logger.error(f"Ошибка обработки команды /start для {user_id}: {str(e)}")
            await message.answer("Ошибка при проверке статуса подписки.")

    async def handle_main_menu(self, callback_query: types.CallbackQuery, state: FSMContext):
        user_id = callback_query.from_user.id
        username = callback_query.from_user.username
        self.logger.info(f"Возврат в главное меню для user_id: {user_id}")
        try:
            user = self.bot_service.repo.get_user(user_id)
            if user:
                user.username = username
                self.bot_service.repo.save_user(user)
            else:
                user = User(user_id=user_id, username=username)
                self.bot_service.repo.save_user(user)

            profile_text = self.bot_service.get_profile_text(user)
            keyboard = self.get_profile_keyboard(user)
            await callback_query.message.edit_text(profile_text, parse_mode="HTML", reply_markup=keyboard)
            await state.clear()
            await callback_query.answer()
        except Exception as e:
            self.logger.error(f"Ошибка возврата в главное меню для {user_id}: {str(e)}")
            await callback_query.message.answer("Ошибка при возврате в главное меню.")

    async def handle_subscription_type(self, callback_query: types.CallbackQuery, state: FSMContext):
        user_id = callback_query.from_user.id
        username = callback_query.from_user.username
        subscription_type = callback_query.data.split(":")[1]
        is_referral = subscription_type == "referral"
        self.logger.info(f"Выбор типа подписки для user_id: {user_id}, subscription_type: {subscription_type}, is_referral: {is_referral}")
        try:
            user = self.bot_service.repo.get_user(user_id)
            if user:
                user.username = username
                user.subscription_type = subscription_type
                user.is_referral = is_referral
            else:
                user = User(user_id=user_id, username=username, subscription_type=subscription_type, is_referral=is_referral)
            self.bot_service.repo.save_user(user)
            keyboard = self.get_tariffs_keyboard(user)
            profile_text = self.bot_service.get_profile_text(user)
            await callback_query.message.edit_text(profile_text, parse_mode="HTML", reply_markup=keyboard)
            await callback_query.answer()
        except Exception as e:
            self.logger.error(f"Ошибка обработки типа подписки для {user_id}: {str(e)}")
            await callback_query.message.answer("Ошибка при выборе типа подписки.")

    async def handle_support(self, callback_query: types.CallbackQuery):
        await callback_query.message.delete()
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await callback_query.message.answer(
            "Если у вас возникли вопросы, обратитесь в техническую поддержку: <a href='https://t.me/TradersLiveCommunity'>@TradersLiveCommunity</a>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await callback_query.answer()

    async def handle_extend_subscription(self, callback_query: types.CallbackQuery, state: FSMContext):
        user_id = callback_query.from_user.id
        username = callback_query.from_user.username
        self.logger.info(f"Запрос продления подписки для user_id: {user_id}")
        try:
            user = self.bot_service.repo.get_user(user_id)
            if user:
                user.username = username
                self.bot_service.repo.save_user(user)
            else:
                user = User(user_id=user_id, username=username)
                self.bot_service.repo.save_user(user)

            if not user.subscription_type:
                keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                    [
                        types.InlineKeyboardButton(text="Обычная подписка", callback_data="subscription_type:regular"),
                        types.InlineKeyboardButton(text="Реферальная подписка", callback_data="subscription_type:referral")
                    ],
                    [
                        types.InlineKeyboardButton(text="📞 Поддержка", callback_data="support"),
                        types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
                    ]
                ])
                await callback_query.message.edit_text(
                    "Пожалуйста, выберите тип подписки:",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            else:
                keyboard = self.get_tariffs_keyboard(user)
                await callback_query.message.edit_text(
                    self.bot_service.get_profile_text(user),
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            await callback_query.answer()
        except Exception as e:
            self.logger.error(f"Ошибка обработки продления подписки для {user_id}: {e}")
            await callback_query.message.answer("Ошибка при продлении подписки.")

    async def handle_help(self, message: types.Message):
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(
            "Если у вас возникли вопросы, обратитесь в техническую поддержку: <a href='https://t.me/TradersLiveCommunity'>@TradersLiveCommunity</a>",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    async def handle_tariff(self, callback_query: types.CallbackQuery, state: FSMContext):
        tariff_id = callback_query.data.split(":")[1]
        user_id = callback_query.from_user.id
        username = callback_query.from_user.username
        self.logger.info(f"Обработка тарифа {tariff_id} для user_id: {user_id}")
        try:
            user = self.bot_service.repo.get_user(user_id)
            if user:
                user.username = username
                self.bot_service.repo.save_user(user)
            else:
                user = User(user_id=user_id, username=username)
                self.bot_service.repo.save_user(user)

            await self.bot_service.process_payment(user_id, tariff_id, callback_query.message, self.bot)
            await state.set_state(PaymentStates.waiting_for_payment)
            if not user.exchange:
                await self.bot_service.request_exchange(user_id, callback_query.message, self.bot)
            await callback_query.answer()
        except Exception as e:
            self.logger.error(f"Ошибка обработки тарифа {tariff_id} для user_id: {user_id}: {e}")
            await callback_query.message.answer("Ошибка при выборе тарифа.")

    async def handle_check_payment(self, callback_query: types.CallbackQuery, state: FSMContext):
        user_id = callback_query.from_user.id
        username = callback_query.from_user.username
        tariff_id = callback_query.data.split(":")[1] if ":" in callback_query.data else "test"
        self.logger.info(f"Проверка оплаты для user_id: {user_id}, tariff_id: {tariff_id}")
        try:
            user = self.bot_service.repo.get_user(user_id)
            if user:
                user.username = username
                self.bot_service.repo.save_user(user)
            else:
                user = User(user_id=user_id, username=username)
                self.bot_service.repo.save_user(user)

            await self.bot_service.check_payment(user_id, callback_query.message, self.bot, username, tariff_id)
            await state.clear()
            await callback_query.answer()
        except Exception as e:
            self.logger.error(f"Ошибка проверки платежа для user_id: {user_id}: {e}")
            await callback_query.message.answer("Ошибка при проверке платежа.")

    async def handle_exchange(self, callback_query: types.CallbackQuery, state: FSMContext):
        exchange = callback_query.data.split(":")[1]
        user_id = callback_query.from_user.id
        username = callback_query.from_user.username
        if exchange not in self.bot_service.SUPPORTED_EXCHANGES:
            await callback_query.message.answer("Пожалуйста, выберите биржу из предложенного списка.")
            await callback_query.answer()
            return
        try:
            user = self.bot_service.repo.get_user(user_id)
            if user:
                user.username = username
                self.bot_service.repo.save_user(user)
            else:
                user = User(user_id=user_id, username=username)
                self.bot_service.repo.save_user(user)

            await state.update_data(exchange=exchange)
            await self.bot_service.request_api_key(user_id, callback_query.message, self.bot)
            await state.set_state(PaymentStates.waiting_for_api_key)
            await callback_query.message.delete()
            await callback_query.answer()
        except Exception as e:
            self.logger.error(f"Ошибка обработки биржи для {user_id}: {e}")
            await callback_query.message.answer("Ошибка при выборе биржи.")

    async def handle_api_key(self, message: types.Message, state: FSMContext):
        api_key = message.text
        user_id = message.from_user.id
        username = message.from_user.username
        data = await state.get_data()
        exchange = data.get("exchange")
        try:
            await self.bot_service.save_exchange_and_api(user_id, exchange, api_key, username)
            await message.answer(
                f"✅ Биржа ({exchange}) и API-ключ успешно сохранены!",
                reply_markup=types.ReplyKeyboardRemove()
            )
            await state.clear()
            profile_text = self.bot_service.get_profile_text(self.bot_service.repo.get_user(user_id))
            keyboard = self.get_profile_keyboard(self.bot_service.repo.get_user(user_id))
            await message.answer(profile_text, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            self.logger.error(f"Ошибка сохранения API-ключа для {user_id}: {e}")
            await message.answer("Ошибка при сохранении API-ключа.")
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            await message.answer("Вернитесь в главное меню:", reply_markup=keyboard)

    def get_profile_keyboard(self, user: User) -> types.InlineKeyboardMarkup:
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📞 Поддержка", callback_data="support"),
                types.InlineKeyboardButton(text="💳 Продлить подписку", callback_data="extend_subscription")
            ]
        ])
        if user and user.subscription_type and not user.exchange:
            keyboard.inline_keyboard.append([
                types.InlineKeyboardButton(text=f"{exchange}", callback_data=f"exchange:{exchange}")
                for exchange in self.bot_service.SUPPORTED_EXCHANGES
            ])
        return keyboard

    def get_tariffs_keyboard(self, user: User) -> types.InlineKeyboardMarkup:
        subscription_type = user.subscription_type if user and user.subscription_type else "regular"
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=f"{tariff['name']} - {tariff['price']}$", callback_data=f"tariff:{tariff_id}")]
            for tariff_id, tariff in self.bot_service.TARIFFS[subscription_type].items()
        ])
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(text="📞 Поддержка", callback_data="support"),
            types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
        ])
        return keyboard