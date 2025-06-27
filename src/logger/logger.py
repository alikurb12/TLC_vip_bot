import logging

class Logger:
    def __init__(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def info(self, msg, *args):
        self.logger.info(msg, *args)
    
    def error(self, msg, *args):
        self.logger.error(msg, *args)