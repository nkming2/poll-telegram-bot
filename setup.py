import os
from setuptools import setup, find_packages

requires = [
	"telepot",
	"Flask",
	"SQLAlchemy",
	"pytz",
]

setup(name = "poll-telegram-bot",
		version = "1",
		description = "Poll Bot for Telegram",
		url = "https://gitlab.com/nkming2/poll-telegram-bot",
		author = "Ming",
		license = "Apache",
		classifiers = [
			"License :: OSI Approved :: Apache Software License",
			"Programming Language :: Python :: 3",
			"Topic :: Communications :: Chat",
		],
		keywords = "poll telegram chat bot",
		packages = find_packages(),
		install_requires = requires)
