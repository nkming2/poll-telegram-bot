from datetime import datetime
import pytz
from sqlalchemy.orm import contains_eager
import telepot
from telepot.exception import TelegramError
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton
from app.lazy import Lazy
from app.log import Log
import app.model as model

def _query_active_polls(session, chat_id):
	return session.query(model.Poll) \
			.filter(model.Poll.chat_id == chat_id) \
			.filter(model.Poll.closed_at == None) \
			.outerjoin(model.Poll.choices) \
			.options(contains_eager(model.Poll.choices)) \
			.outerjoin(model.PollChoice.votes) \
			.options(contains_eager(model.Poll.choices,
					model.PollChoice.votes)) \
			.order_by(model.Poll.poll_id, model.PollChoice.poll_choice_id) \
			.all()

def _repr_poll(poll_m, is_sort_by_votes = False):
	text = f"{poll_m.title}\n"
	# [0] = choice number, [1] = choice model
	choices = [(i + 1, c_m) for i, c_m in enumerate(poll_m.choices)]
	if is_sort_by_votes:
		choices = sorted(choices, key = lambda c: (len(c[1].votes), -c[0]),
				reverse = True)
	choice_texts = []
	for c in choices:
		c_text = f"{c[0]}. {c[1].text} ({len(c[1].votes)})"
		vote_texts = []
		for v_m in c[1].votes:
			vote_texts += [f"[{v_m.user_name}](tg://user?id={v_m.user_id})"]
		if vote_texts:
			c_text += "\n  " + ", ".join(vote_texts)
		choice_texts += [c_text]
	text += "\n\n".join(choice_texts)
	return text

def _make_poll_inline_keyboard(is_creator):
	keyboard = [[
		InlineKeyboardButton(text = "Vote", callback_data = "/vote"),
	]]
	keyboard += [[
		InlineKeyboardButton(text = "Edit", callback_data = "/edit-poll"),
	]]
	if is_creator:
		keyboard[1] += [
			InlineKeyboardButton(text = "Close poll",
					callback_data = "/close-poll"),
		]
	return keyboard

_RESPONSE_NEW_POLL = "To create a new poll, reply to this message with the poll title and choices\n\nExample:\nWhat to eat tonight?\nBurger\nPasta"
_RESPONSE_NEW_CHOICE = "To add a new choice, reply to this message with the choice in one line"

class _ResponseException(Exception):
	def __init__(self, response, e = None):
		self._response = response
		self._e = e

	@property
	def response(self):
		return self._response

	def __str__(self):
		return str(self._e) if self._e is not None else self._response

	def __repr__(self):
		return repr(self._e) if self._e is not None else self._response

## Bot logic when it's called in a private chat
class MessageHandler:
	RESPONSE_EXCEPTION = "Unknown error"
	RESPONSE_POLL_SANS_POLL = "Hi, there's no ongoing poll, would you like to start one?"
	RESPONSE_NEWPOLL_PERSISTED_F = "Created new poll *%s*. You can use /poll to check out the current poll"
	RESPONSE_NEW_CHOICE_PERSISTED_F = "Added new choice *%s*"
	RESPONSE_ERROR_NEWPOLL_FORMAT = "Invalid input format"
	RESPONSE_ERROR_MISSING_CHOICES = "Missing poll choices"
	RESPONSE_ERROR_POLL_EXIST = "There can only be one active poll per chat, see /poll"
	RESPONSE_ERROR_NEW_CHOICE_FORMAT = "Invalid input format"

	def __init__(self, bot, msg, Session):
		self._bot = bot
		self._msg = msg
		self._Session = Session

	def handle(self):
		try:
			self._do_handle()
		except _ResponseException as e:
			Log.e("Failed while handle", e)
			self._bot.sendMessage(self._glance["chat_id"], e.response)
		except Exception as e:
			Log.e("Failed while handle", e)
			self._bot.sendMessage(self._glance["chat_id"],
					self.RESPONSE_EXCEPTION)

	def _do_handle(self):
		Log.v(self._msg)
		if self._glance["content_type"] == "text":
			if self._msg["text"].startswith("/"):
				self._handle_cmd(self._msg["text"])
			else:
				self._handle_text(self._msg["text"])
		# Ignore non-text content (like new memeber msg)

	def _handle_cmd(self, text):
		if text == "/start" or text == "/poll":
			self._handle_poll_cmd()

	def _handle_poll_cmd(self):
		with model.open_session(self._Session) as s:
			poll_ms = _query_active_polls(s, self._glance["chat_id"])
			if not poll_ms:
				# No active poll
				self._handle_poll_cmd_sans_poll()
				return

			poll_m = poll_ms[0]
			text = _repr_poll(poll_m)
			keyboard = _make_poll_inline_keyboard(
					poll_m.creator_user_id == self._user["id"])
		self._bot.sendMessage(self._glance["chat_id"], text,
				parse_mode = "Markdown",
				reply_markup = InlineKeyboardMarkup(inline_keyboard = keyboard))

	def _handle_poll_cmd_sans_poll(self):
		self._bot.sendMessage(self._glance["chat_id"],
				self.RESPONSE_POLL_SANS_POLL,
				reply_markup = InlineKeyboardMarkup(inline_keyboard = [[
					InlineKeyboardButton(text = "Create new poll",
							callback_data = "/new-poll"),
				]]))

	def _handle_text(self, text):
		if "reply_to_message" in self._msg:
			# Replying us
			reply_text = self._msg["reply_to_message"]["text"]
			if reply_text == _RESPONSE_NEW_POLL:
				# User responded us with the poll details
				self._handle_new_poll_response(text)
			elif reply_text == _RESPONSE_NEW_CHOICE:
				# User responded us with the new choice
				self._handle_new_choice_response(text)

	def _handle_new_poll_response(self, text):
		try:
			lines = text.strip().split("\n")
			title = lines[0]
			choices = lines[1:]
		except Exception:
			# Wrong format
			raise _ResponseException(self.RESPONSE_ERROR_NEWPOLL_FORMAT)

		if not choices:
			# No poll choices!
			raise _ResponseException(self.RESPONSE_ERROR_MISSING_CHOICES)

		try:
			with model.open_session(self._Session) as s:
				if self._has_active_polls(s):
					raise _ResponseException(self.RESPONSE_ERROR_POLL_EXIST)

				self._persist_new_poll(s, title, choices);
			self._bot.sendMessage(self._glance["chat_id"],
					self.RESPONSE_NEWPOLL_PERSISTED_F % title,
					parse_mode = "Markdown")
		except Exception:
			Log.i(f"Failed persisting new poll \"{title}\": {choices}")
			raise

	def _handle_new_choice_response(self, text):
		try:
			choice = text.strip().split("\n")[0]
			assert choice
		except Exception:
			# Wrong format
			raise _ResponseException(self.RESPONSE_ERROR_NEW_CHOICE_FORMAT)

		with model.open_session(self._Session) as s:
			poll_ms = _query_active_polls(s, self._glance["chat_id"])
			if not poll_ms:
				raise _ResponseException(self.RESPONSE_ERROR_POLL_NOT_EXIST)

			poll_m = poll_ms[0]
			choice_m = model.PollChoice(text = choice, poll = poll_m)
			s.add(choice_m)
		self._bot.sendMessage(self._glance["chat_id"],
				self.RESPONSE_NEW_CHOICE_PERSISTED_F % choice,
				parse_mode = "Markdown")

	def _persist_new_poll(self, session, title, choices):
		poll_m = model.Poll(title = title, chat_id = self._glance["chat_id"],
				creator_user_id = self._user["id"])
		choices_m = []
		for c in choices:
			choices_m += [model.PollChoice(text = c, poll = poll_m)]
		session.add(poll_m)

	def _has_active_polls(self, session):
		return session.query(model.Poll) \
				.filter(model.Poll.chat_id == self._glance["chat_id"]) \
				.filter(model.Poll.closed_at == None) \
				.count()

	@property
	def _user(self):
		return self._msg["from"]

	@Lazy
	def _glance(self):
		content_type, chat_type, chat_id = telepot.glance(self._msg)
		return {
			"content_type": content_type,
			"chat_type": chat_type,
			"chat_id": chat_id,
		}

class CallbackQueryHandler:
	RESPONSE_EXCEPTION = "Unknown error"
	RESPONSE_VOTE = "Pick your choice"
	RESPONSE_EDIT_POLL = "What do you want to modify?"
	RESPONSE_RM_CHOICE = "Pick a choice to be removed with its associated votes. You *cannot* undo this action"
	RESPONSE_RM_CHOICE_PERSISTED_F = "Removed choice *%s*"
	RESPONSE_ALLOW_MULTI_VOTE = "Allow multiple votes per person? You *cannot* undo this action"
	RESPONSE_ALLOW_MULTI_VOTE_PERSISTED = "Multiple votes allowed"
	RESPONSE_CLOSE_POLL = "Close the poll? You *cannot* undo this action"
	RESPONSE_CANCEL_OP = "Cancelled"
	RESPONSE_ERROR_POLL_EXIST = "There can only be one active poll per chat, see /poll"
	RESPONSE_ERROR_POLL_NOT_EXIST = "No active poll in this chat. Enter /start"
	RESPONSE_ERROR_MULTIPLE_VOTE = "You have voted already"
	RESPONSE_ERROR_NOT_CREATOR = "Only the poll creator can do that"
	RESPONSE_ERROR_RM_LAST_CHOICE = "Can't remove the last choice"

	def __init__(self, bot, msg, Session):
		self._bot = bot
		self._msg = msg
		self._Session = Session

	def handle(self):
		try:
			self._do_handle()
		except _ResponseException as e:
			Log.e("Failed while handle", e)
			self._send_message(e.response)
		except Exception as e:
			Log.e("Failed while handle", e)
			self._send_message(self.RESPONSE_EXCEPTION)
		finally:
			# After the user presses a callback button, Telegram clients will
			# display a progress bar until you call answerCallbackQuery. It is,
			# therefore, necessary to react by calling answerCallbackQuery even
			# if no notification to the user is needed
			self._bot.answerCallbackQuery(self._glance["query_id"])

	def _do_handle(self):
		if self._msg["data"].startswith("/"):
			self._handle_cmd(self._glance["query_data"])

	def _handle_cmd(self, text):
		if text == "/new-poll":
			self._handle_new_poll_cmd()
		elif text == "/close-poll":
			self._handle_close_poll_cmd()
		elif text == "/do-close_poll":
			self._handle_do_close_poll_cmd()
		elif text == "/edit-poll":
			self._handle_edit_poll_cmd()
		elif text == "/new-choice":
			self._handle_new_choice_cmd()
		elif text == "/rm-choice":
			self._handle_rm_choice_cmd()
		elif text.startswith("/do-rm-choice-"):
			self._handle_do_rm_choice_cmd(text)
		elif text == "/allow-multi-vote":
			self._handle_allow_multi_vote_cmd()
		elif text == "/do-allow-multi-vote":
			self._handle_do_allow_multi_vote_cmd()
		elif text == "/vote":
			self._handle_vote_cmd()
		elif text.startswith("/do-vote-"):
			self._handle_do_vote_cmd(text)
		elif text == "/cancel-op":
			self._handle_cancel_op_cmd()

	def _handle_new_poll_cmd(self):
		with model.open_session(self._Session) as s:
			poll_ms = _query_active_polls(s, self._chat_id)
			if poll_ms:
				raise _ResponseException(self.RESPONSE_ERROR_POLL_EXIST)
		self._edit_message_text(_RESPONSE_NEW_POLL)

	def _handle_close_poll_cmd(self):
		keyboard = [[
			InlineKeyboardButton(text = "Yes",
					callback_data = "/do-close_poll"),
			InlineKeyboardButton(text = "No",
					callback_data = "/cancel-op"),
		]]
		self._edit_message_text(self.RESPONSE_CLOSE_POLL,
				parse_mode = "Markdown",
				reply_markup = InlineKeyboardMarkup(inline_keyboard = keyboard))

	def _handle_do_close_poll_cmd(self):
		with model.open_session(self._Session) as s:
			poll_ms = _query_active_polls(s, self._chat_id)
			if not poll_ms:
				raise _ResponseException(self.RESPONSE_ERROR_POLL_NOT_EXIST)

			poll_m = poll_ms[0]
			if poll_m.creator_user_id != self._user["id"]:
				raise _ResponseException(self.RESPONSE_ERROR_NOT_CREATOR)
			text = "Result:\n" + _repr_poll(poll_m, is_sort_by_votes = True)
			poll_m.closed_at = datetime.now(pytz.utc)
		self._edit_message_text(text, parse_mode = "Markdown")

	def _handle_edit_poll_cmd(self):
		with model.open_session(self._Session) as s:
			poll_ms = _query_active_polls(s, self._chat_id)
			if not poll_ms:
				raise _ResponseException(self.RESPONSE_ERROR_POLL_NOT_EXIST)

			poll_m = poll_ms[0]
			keyboard = [[
				InlineKeyboardButton(text = "Add a choice",
						callback_data = "/new-choice"),
			]]
			if poll_m.creator_user_id == self._user["id"]:
				if len(poll_m.choices) > 1:
					keyboard[0] += [
						InlineKeyboardButton(text = "Remove a choice",
								callback_data = "/rm-choice"),
					]
				if not poll_m.is_multiple_vote:
					keyboard += [[
						InlineKeyboardButton(text = "Allow multiple votes",
								callback_data = "/allow-multi-vote"),
					]]
		self._edit_message_text(self.RESPONSE_EDIT_POLL,
				reply_markup = InlineKeyboardMarkup(inline_keyboard = keyboard))

	def _handle_new_choice_cmd(self):
		self._send_message(_RESPONSE_NEW_CHOICE)

	def _handle_rm_choice_cmd(self):
		with model.open_session(self._Session) as s:
			poll_ms = _query_active_polls(s, self._chat_id)
			if not poll_ms:
				raise _ResponseException(self.RESPONSE_ERROR_POLL_NOT_EXIST)

			poll_m = poll_ms[0]
			if poll_m.creator_user_id != self._user["id"]:
				raise _ResponseException(self.RESPONSE_ERROR_NOT_CREATOR)
			btns = [InlineKeyboardButton(text = c_m.text,
							callback_data = f"/do-rm-choice-{c_m.poll_choice_id}")
					for c_m in poll_m.choices]
			keyboard = [btns[i:i + 2] for i in range(0, len(btns), 2)]
			keyboard += [[InlineKeyboardButton(text = "Cancel",
					callback_data = "/cancel-op")]]
		self._edit_message_text(self.RESPONSE_RM_CHOICE, parse_mode = "Markdown",
				reply_markup = InlineKeyboardMarkup(inline_keyboard = keyboard))

	def _handle_do_rm_choice_cmd(self, text):
		# /do-rm-choice-{choice_id}
		try:
			choice_id = int(text[14:])
		except Exception:
			Log.e(f"Failed while parsing choice id: {text}")
			raise

		with model.open_session(self._Session) as s:
			poll_ms = _query_active_polls(s, self._chat_id)
			if not poll_ms:
				raise _ResponseException(self.RESPONSE_ERROR_POLL_NOT_EXIST)

			poll_m = poll_ms[0]
			if poll_m.creator_user_id != self._user["id"]:
				raise _ResponseException(self.RESPONSE_ERROR_NOT_CREATOR)
			if len(poll_m.choices) == 1:
				raise _ResponseException(self.RESPONSE_ERROR_RM_LAST_CHOICE)
			choice_m = next(filter(lambda c_m: c_m.poll_choice_id == choice_id,
					poll_m.choices))
			choice = choice_m.text
			s.delete(choice_m)

		self._edit_message_text(self.RESPONSE_RM_CHOICE_PERSISTED_F % choice,
				parse_mode = "Markdown")

	def _handle_allow_multi_vote_cmd(self):
		keyboard = [[
			InlineKeyboardButton(text = "Yes",
					callback_data = "/do-allow-multi-vote"),
			InlineKeyboardButton(text = "No",
					callback_data = "/cancel-op"),
		]]
		self._edit_message_text(self.RESPONSE_ALLOW_MULTI_VOTE,
				parse_mode = "Markdown",
				reply_markup = InlineKeyboardMarkup(inline_keyboard = keyboard))

	def _handle_do_allow_multi_vote_cmd(self):
		with model.open_session(self._Session) as s:
			poll_ms = _query_active_polls(s, self._chat_id)
			if not poll_ms:
				raise _ResponseException(self.RESPONSE_ERROR_POLL_NOT_EXIST)

			poll_m = poll_ms[0]
			if poll_m.creator_user_id != self._user["id"]:
				raise _ResponseException(self.RESPONSE_ERROR_NOT_CREATOR)
			poll_m.is_multiple_vote = True
		self._edit_message_text(self.RESPONSE_ALLOW_MULTI_VOTE_PERSISTED)

	def _handle_vote_cmd(self):
		with model.open_session(self._Session) as s:
			poll_ms = _query_active_polls(s, self._chat_id)
			if not poll_ms:
				raise _ResponseException(self.RESPONSE_ERROR_POLL_NOT_EXIST)

			poll_m = poll_ms[0]
			btns = [InlineKeyboardButton(text = c_m.text,
							callback_data = f"/do-vote-{c_m.poll_choice_id}")
					for c_m in poll_m.choices]
			keyboard = [btns[i:i + 2] for i in range(0, len(btns), 2)]
		self._edit_message_text(self.RESPONSE_VOTE,
				reply_markup = InlineKeyboardMarkup(inline_keyboard = keyboard))

	def _handle_do_vote_cmd(self, text):
		# /do-vote-{choice_id}
		try:
			vote = int(text[9:])
		except Exception:
			Log.e(f"Failed while parsing choice id: {text}")
			raise

		with model.open_session(self._Session) as s:
			poll_ms = _query_active_polls(s, self._chat_id)
			if not poll_ms:
				raise _ResponseException(self.RESPONSE_ERROR_POLL_NOT_EXIST)

			poll_m = poll_ms[0]
			user_id = self._user["id"]
			for c_m in poll_m.choices:
				if c_m.poll_choice_id == vote:
					choice_m = c_m
					break
			# We don't need a fallback val for choice_m -- it'll raise when we
			# access it anyway

			if not poll_m.is_multiple_vote:
				# Make sure user hasn't voted yet
				for c_m in poll_m.choices:
					if any(user_id == v_m.user_id for v_m in c_m.votes):
						raise _ResponseException(
								self.RESPONSE_ERROR_MULTIPLE_VOTE)
			else:
				# Make sure user hasn't voted for this choice yet
				if any(user_id == v_m.user_id for v_m in choice_m.votes):
					raise _ResponseException(self.RESPONSE_ERROR_MULTIPLE_VOTE)

			vote_m = model.PollVote(user_id = user_id,
					user_name = self._user["first_name"],
					choice = choice_m)
			s.add(vote_m)

			text = _repr_poll(poll_m)
			keyboard = _make_poll_inline_keyboard(
					poll_m.creator_user_id == self._user["id"])
		self._edit_message_text(text, parse_mode = "Markdown",
				reply_markup = InlineKeyboardMarkup(inline_keyboard = keyboard))

	def _handle_cancel_op_cmd(self):
		if not self._bot.deleteMessage((self._chat_id,
				self._msg["message"]["message_id"])):
			# Can fail if the message is too old
			self._edit_message_text(self.RESPONSE_CANCEL_OP)

	def _send_message(self, *args, **kwargs):
		if "message" not in self._msg:
			# Can't send a msg without this
			return
		self._bot.sendMessage(self._chat_id, *args, **kwargs)

	def _edit_message_text(self, *args, **kwargs):
		try:
			self._bot.editMessageText(
					(self._chat_id, self._msg["message"]["message_id"]),
					*args, **kwargs)
		except TelegramError as e:
			if e.error_code == 400 \
					and e.description == "Bad Request: message is not modified":
				# Clicked button twice?
				Log.d("Failed while editMessageText", e)

	@property
	def _user(self):
		return self._msg["from"]

	@property
	def _chat_id(self):
		return self._msg["message"]["chat"]["id"]

	@Lazy
	def _glance(self):
		query_id, from_id, query_data = telepot.glance(self._msg,
				flavor = "callback_query")
		return {
			"query_id": query_id,
			"from_id": from_id,
			"query_data": query_data,
		}
