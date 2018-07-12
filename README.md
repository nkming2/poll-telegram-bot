# Yet Another Poll Bot for Telegram

## How to use
[@yapbbot](https://telegram.me/yapbbot)

## Run instruction
```
git clone https://gitlab.com/nkming2/poll-telegram-bot
cd poll-telegram-bot
pip install -e .
PYTHONPATH=src python3 src/app/__init__.py
```
You might want to do this in a venv env

After setting up these you'll have to fill in your API keys in config.json

### Hosting on pythonanywhere
One easy option to host the bot freely is on PAW. In your web console you should
set the source directory to src and modify the WSGI config file based on the
sample given in this repo (misc/pythonanywhere_com_wsgi.py)

## config.json
This file holds constants like API keys that should be kept outside of the repo.
config.json should be a text file of valid serialized JSON. The following fields
must be present:
- telegram_bot_token
  - Your telegram bot token. You need to obtain it via
  [@BotFather](https://telegram.me/BotFather) following the instructions outlined
  at https://core.telegram.org/bots
- paw_app
  - Useful only when you are hosting on PAW (See
  [Hosting on pythonanywhere](#hosting-on-pythonanywhere) for more details)
  - url
    - The URL of your web app
  - webhook_secret
    - Any string, must be valid URL character

## Dependency
- Python 3.6+
- Telepot (https://github.com/nickoala/telepot)
- SQLAlchemy
