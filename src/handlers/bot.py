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
        self.router.message(PaymentStates.waiting_for_exchange, F.text.in_(self.bot_service.SUPPORTED_EXCHANGES))(self.handle_exchange)
        self.router.message(PaymentStates.waiting_for_api_key)(self.handle_api_key)

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
            # Сохраняем username, если пользователь существует
            if user:
                self.logger.info(f"Обновление username для существующего пользователя: {username}")
                user.username = username
                self.bot_service.repo.save_user(user)
            else:
                self.logger.info(f"Создание нового пользователя с user_id: {user_id}, username: {username}")
                user = User(user_id=user_id, username=username)
                self.bot_service.repo.save_user(user)

            if user and user.subscription_end and user.subscription_end > datetime.now():
                text = f"✅ Ваша подписка активна до <b>{user.subscription_end.strftime('%Y-%m-%d %H:%M:%S')}</b>"
                self.logger.info(f"Подписка активна для user_id: {user_id}, конец подписки: {user.subscription_end}")
                if not user.exchange:
                    self.logger.info(f"Запрос биржи для user_id: {user_id}")
                    await self.bot_service.request_exchange(user_id, message, self.bot)
                    await state.set_state(PaymentStates.waiting_for_exchange)
                    return
                await message.answer(text, parse_mode="HTML")
            else:
                keyboard = self.get_tariffs_keyboard()
                text = "❗️ Ваша подписка истекла. Пожалуйста, продлите её:" if user else "👋 Добро пожаловать! Выберите тариф для подписки:"
                self.logger.info(f"Предложение тарифов для user_id: {user_id}")
                await message.answer(text, reply_markup=keyboard)
        except Exception as e:
            self.logger.error(f"Ошибка обработки команды /start для {user_id}: {str(e)}")
            await message.answer("Ошибка при проверке статуса подписки.")

    async def handle_help(self, message: types.Message):
        await message.answer(
            "Если у вас возникли вопросы, обратитесь в техническую поддержку: <a href='https://t.me/TradersLiveCommunity'>@TradersLiveCommunity</a>",
            parse_mode="HTML"
        )

    async def handle_tariff(self, callback_query: types.CallbackQuery, state: FSMContext):
        tariff_id = callback_query.data.split(":")[1]
        user_id = callback_query.from_user.id
        username = callback_query.from_user.username
        self.logger.info(f"Обработка тарифа {tariff_id} для user_id: {user_id}")
        try:
            # Сохраняем username перед обработкой платежа
            user = self.bot_service.repo.get_user(user_id)
            if user:
                user.username = username
                self.bot_service.repo.save_user(user)
            else:
                user = User(user_id=user_id, username=username)
                self.bot_service.repo.save_user(user)

            await self.bot_service.process_payment(user_id, tariff_id, callback_query.message, self.bot)
            await state.set_state(PaymentStates.waiting_for_payment)
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
            # Сохраняем username перед проверкой платежа
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

    async def handle_exchange(self, message: types.Message, state: FSMContext):
        exchange = message.text
        user_id = message.from_user.id
        username = message.from_user.username
        if exchange not in self.bot_service.SUPPORTED_EXCHANGES:
            await message.answer("Пожалуйста, выберите биржу из предложенного списка.")
            return
        try:
            # Сохраняем username перед сохранением биржи
            user = self.bot_service.repo.get_user(user_id)
            if user:
                user.username = username
                self.bot_service.repo.save_user(user)
            else:
                user = User(user_id=user_id, username=username)
                self.bot_service.repo.save_user(user)

            await state.update_data(exchange=exchange)
            await self.bot_service.request_api_key(user_id, message, self.bot)
            await state.set_state(PaymentStates.waiting_for_api_key)
        except Exception as e:
            self.logger.error(f"Ошибка обработки биржи для {user_id}: {e}")
            await message.answer("Ошибка при выборе биржи.")

    async def handle_api_key(self, message: types.Message, state: FSMContext):
        api_key = message.text
        user_id = message.from_user.id
        username = message.from_user.username
        data = await state.get_data()
        exchange = data.get("exchange")
        try:
            # Сохраняем username вместе с биржей и API
            await self.bot_service.save_exchange_and_api(user_id, exchange, api_key, username)
            await message.answer(
                f"✅ Биржа ({exchange}) и API-ключ успешно сохранены!",
                reply_markup=types.ReplyKeyboardRemove()
            )
            await state.clear()
        except Exception as e:
            self.logger.error(f"Ошибка сохранения API-ключа для {user_id}: {e}")
            await message.answer("Ошибка при сохранении API-ключа.")

    def get_tariffs_keyboard(self) -> types.InlineKeyboardMarkup:
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
        for tariff_id, tariff in self.bot_service.TARIFFS.items():
            keyboard.inline_keyboard.append([
                types.InlineKeyboardButton(
                    text=f"{tariff['name']} - {tariff['price']}$",
                    callback_data=f"tariff:{tariff_id}"
                )
            ])
        return keyboard