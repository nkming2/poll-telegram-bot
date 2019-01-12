from flask import Flask, request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import telepot
import urllib3
from app.config_loader import ConfigLoader
from app.log import Log
from app.message_handler import CallbackQueryHandler, MessageHandler
import app.model as model

flask_app = None

class PawApp():
	TELEGRAM_TOKEN = ConfigLoader.load("telegram_bot_token")

	def __init__(self):
		Log.i("Initializing PAW app")
		self._init_paw_telepot()
		self._bot = telepot.Bot(self.TELEGRAM_TOKEN)

	def run(self):
		url = ConfigLoader.load("paw_app")["url"]
		secret = ConfigLoader.load("paw_app")["webhook_secret"]

		app = Flask(__name__)
		def _webhook_view():
			return self._on_webhook()
		app.add_url_rule("/%s" % secret, view_func = _webhook_view,
				methods = ["POST"])

		global flask_app
		flask_app = app

		self._bot.setWebhook("%s/%s" % (url, secret), max_connections = 1)

	def _init_paw_telepot(self):
		# You can leave this bit out if you're using a paid PythonAnywhere
		# account
		proxy_url = "http://proxy.server:3128"
		telepot.api._pools = {
			"default": urllib3.ProxyManager(proxy_url = proxy_url, num_pools = 3,
					maxsize = 10, retries = False, timeout = 30),
		}
		telepot.api._onetime_pool_spec = (urllib3.ProxyManager,
				dict(proxy_url = proxy_url, num_pools = 1, maxsize = 1,
						retries = False, timeout = 30))
		# end of the stuff that's only needed for free accounts

	def _on_webhook(self):
		update = request.get_json()
		self._handle_update(update)
		return "OK"

	def _handle_update(self, update):
		if "update_id" in update:
			if not self._should_process_update(update["update_id"]):
				return

		if "message" in update:
			# message request
			MessageHandler(self._bot, update["message"],
					self._make_session_class()).handle()
		elif "callback_query" in update:
			# inline request
			CallbackQueryHandler(self._bot, update["callback_query"],
					self._make_session_class()).handle()

	def _should_process_update(self, update_id):
		import datetime
		now = datetime.datetime.utcnow()
		dt = datetime.timedelta(weeks = 1)
		from_time = now - dt
		with model.open_session(self._make_session_class()) as s:
			count = s.query(model.HandledUpdate) \
					.filter(model.HandledUpdate.update_id == update_id) \
					.filter(model.HandledUpdate.created_at >= from_time) \
					.count()
			if count == 0:
				# Add this update
				m = model.HandledUpdate(update_id = update_id)
				s.add(m)
			# Cleanup old ones
			s.query(model.HandledUpdate) \
					.filter(model.HandledUpdate.created_at < from_time) \
					.delete(synchronize_session = False)
			return (count == 0)

	def _make_session_class(self):
		sqlite_engine = create_engine("sqlite:///poll.db", echo = True)
		return sessionmaker(bind = sqlite_engine)
