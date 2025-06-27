class Payment:
    def __init__(self, invoice_id : int, user_id : int, amount : float, currency : str, status : str):
        self.invoice_id = invoice_id
        self.user_id = user_id
        self.amount = amount
        self.currency = currency
        self.status = status