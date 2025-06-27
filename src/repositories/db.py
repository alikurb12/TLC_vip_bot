import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from src.models.user import User
from src.models.payments import Payment
from src.logger.logger import Logger

class Repository:
    def __init__(self, db_config : dict, logger: Logger):
        self.logger = logger
        try:
            self.conn = psycopg2.connect(**db_config, cursor_factory=RealDictCursor)
        except Exception as e:
            self.logger.error(f"Ошибка подключения к базе данных {e}")
            raise
        self.logger.info("Подключение к базе данных успешно установлено")
        self.cursor = self.conn.cursor()

    def get_user(self, user_id: int) -> User:
        self.logger.info(f"Получение пользователя с ID {user_id}")
        try:
            self.cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            result = self.cursor.fetchone()
            if result:
                return User(
                    user_id=result['user_id'],
                    subscription_end=result.get('subscription_end'),
                    exchange=result.get('exchange'),
                    api_key=result.get('api_key'),
                    username=result.get('username')
                )
            return None
        except Exception as e:
            self.logger.error(f"Ошибка при получении пользователя: {e}")
            raise
    
    def save_user(self, user: User):
        try:
            self.logger.info(f"Сохранение пользователя {user.user_id}")
            self.cursor.execute(
                """
                INSERT INTO users (user_id, subscription_end, exchange, api_key, username)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET subscription_end = EXCLUDED.subscription_end
                """,
                (user.user_id, user.subscription_end, user.exchange, user.api_key, user.username)
            )

            self.conn.commit()
            self.logger.info(f"Пользователь {user.user_id} успешно сохранен")
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении пользователя {user.user_id}: {e}")
            raise

    def delete_user(self, user_id: int):
        try:
            self.logger.info(f"Удаление пользователя с ID {user_id}")
            self.cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            self.conn.commit()
        except Exception as e:
            self.logger.error(f"Ошибка при удалении пользователя {user_id}: {e}")
            raise

    def get_expired_users(self) -> list[User]:
        self.logger.info("Получение списка просроченных пользователей")
        try:
            self.cursor.execute(
                "SELECT * FROM users WHERE subscription_end < %s",
                (datetime.now(),)
            )
            results = self.cursor.fetchall()
            return [User(
                user_id=result['user_id'],
                subscription_end=result.get('subscription_end'),
                exchange=result.get('exchange'),
                api_key=result.get('api_key'),
                username=result.get('username')
            ) for result in results]
        except Exception as e:
            self.logger.error(f"Ошибка при получении просроченных пользователей: {e}")
            raise
    
    def save_payment(self, payment: Payment):
        try:
            self.logger.info(f"Сохранение платежа для пользователя {payment.user_id} на сумму {payment.amount} {payment.currency}")
            self.cursor.execute(
                """
                INSERT INTO payments (invoice_id, user_id, amount, currency, status)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (payment.invoice_id, payment.user_id, payment.amount, payment.currency, payment.status)
            )
            self.conn.commit()
            self.logger.info(f"Платеж для пользователя {payment.user_id} успешно сохранен")
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении платежа для пользователя {payment.user_id}: {e}")
            raise

    def update_payment_status(self, invoice_id: int, status: str):
        try:
            self.logger.info(f"Обновление статуса платежа для инвойса {invoice_id} на {status}")
            self.cursor.execute(
                "UPDATE payments SET status = %s WHERE invoice_id = %s",
                (status, invoice_id)
            )
            self.conn.commit()
            self.logger.info(f"Статус платежа для инвойса {invoice_id} успешно обновлен")
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении статуса платежа для инвойса {invoice_id}: {e}")
            raise
    
    def get_payments_by_user(self, user_id: int) -> list[Payment]:
        self.logger.info(f"Получение платежей для пользователя с ID {user_id}")
        try:
            self.cursor.execute("SELECT * FROM payments WHERE user_id = %s", (user_id,))
            results = self.cursor.fetchall()
            return [Payment(
                invoice_id=result['invoice_id'],
                user_id=result['user_id'],
                amount=result['amount'],
                currency=result['currency'],
                status=result['status']
            ) for result in results]
        except Exception as e:
            self.logger.error(f"Ошибка при получении платежей для пользователя {user_id}: {e}")
            raise
    
    def get_latest_payment(self, user_id: int) -> Payment:
        self.logger.info(f"Получение последнего платежа для пользователя с ID {user_id}")
        try:
            self.cursor.execute(
                "SELECT * FROM payments WHERE user_id = %s ORDER BY invoice_id DESC LIMIT 1",
                (user_id,)
            )
            result = self.cursor.fetchone()
            if result:
                return Payment(
                    invoice_id=result['invoice_id'],
                    user_id=result['user_id'],
                    amount=result['amount'],
                    currency=result['currency'],
                    status=result['status']
                )
            return None
        except Exception as e:
            self.logger.error(f"Ошибка при получении последнего платежа для пользователя {user_id}: {e}")
            raise
    
    def __del__(self):
        self.cursor.close()
        self.conn.close()