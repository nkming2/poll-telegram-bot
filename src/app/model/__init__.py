from contextlib import contextmanager
import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class HandledUpdate(Base):
	__tablename__ = "handled_update"
	_id = Column(Integer, primary_key = True)
	update_id = Column(Integer, index = True)
	created_at = Column(DateTime, nullable = False,
			default = datetime.datetime.utcnow)

class Poll(Base):
	__tablename__ = "poll"
	poll_id = Column(Integer, primary_key = True)
	title = Column(String, nullable = False)
	# If string starts with @, it's a public channel id and otherwise assume it
	# is a long value
	chat_id = Column(String, nullable = False)
	creator_user_id = Column(Integer, nullable = False)
	created_at = Column(DateTime, nullable = False,
			default = datetime.datetime.utcnow)
	closed_at = Column(DateTime)
	is_multiple_vote = Column(Boolean, nullable = False, default = False)

	choices = relationship("PollChoice", backref = "poll",
			cascade = "all, delete-orphan", passive_deletes = True)

class PollChoice(Base):
	__tablename__ = "poll_choice"
	poll_choice_id = Column(Integer, primary_key = True)
	poll_id = Column(Integer, ForeignKey(Poll.poll_id, ondelete = "CASCADE"),
			nullable = False)
	text = Column(String, nullable = False)

	votes = relationship("PollVote", backref = "choice",
			cascade = "all, delete-orphan", passive_deletes = True)

class PollVote(Base):
	__tablename__ = "poll_vote"
	poll_vote_id = Column(Integer, primary_key = True)
	poll_choice_id = Column(Integer, ForeignKey(PollChoice.poll_choice_id,
			ondelete = "CASCADE"), nullable = False)
	user_id = Column(Integer, nullable = False)
	user_name = Column(String, nullable = False)
	created_at = Column(DateTime, nullable = False,
			default = datetime.datetime.utcnow)

	UniqueConstraint(poll_choice_id, user_id)

@contextmanager
def open_session(Session):
	"""Provide a transactional scope around a series of operations."""
	session = Session()
	try:
		yield session
		session.commit()
	except:
		session.rollback()
		raise
	finally:
		session.close()
