from datetime import datetime
from typing import Optional

class User:
    def __init__(self, user_id: int, subscription_end: Optional[datetime] = None, exchange: Optional[str] = None,
                 api_key: Optional[str] = None, username: Optional[str] = None):
        self.user_id = user_id
        self.subscription_end = subscription_end
        self.exchange = exchange
        self.api_key = api_key
        self.username = username