from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import telepot
from app.config_loader import ConfigLoader
from app.log import Log
from app.message_handler import CallbackQueryHandler, MessageHandler

class StandaloneApp:
	TELEGRAM_TOKEN = ConfigLoader.load("telegram_bot_token")

	def __init__(self):
		Log.i("Initializing standalone app")
		self._bot = telepot.Bot(self.TELEGRAM_TOKEN)

	def run(self):
		import time
		self._start()
		Log.i("Running...")
		while True:
			time.sleep(10)

	def _start(self):
		Log.i("Starting app")
		def _listener(msg):
			self._on_message(msg)
		def _callback_query_listener(msg):
			self._on_callback_query(msg)
		self._bot.setWebhook("")
		self._bot.message_loop({
			"chat": _listener,
			"callback_query": _callback_query_listener,
		})

	def _on_message(self, msg):
		MessageHandler(self._bot, msg, self._make_session_class()).handle()

	def _on_callback_query(self, msg):
		CallbackQueryHandler(self._bot, msg, self._make_session_class()).handle()

	def _make_session_class(self):
		sqlite_engine = create_engine("sqlite:///poll.db", echo = True)
		return sessionmaker(bind = sqlite_engine)
