# This file contains the WSGI configuration required to serve up your
# web application at http://<your-username>.pythonanywhere.com/
# It works by setting the variable 'application' to a WSGI handler of some
# description.
#
# +++++++++++ FLASK +++++++++++
# Flask works like any other WSGI-compatible framework, we just need
# to import the application.  Often Flask apps are called "app" so we
# may need to rename it during the import:

import sys

# The "/home/<your-username>" below specifies your home
# directory -- the rest should be the directory you uploaded your Flask
# code to underneath the home directory.  So if you just ran
# "git clone git@github.com/myusername/myproject.git"
# ...or uploaded files to the directory "myproject", then you should
# specify "/home/<your-username>/myproject"
path = '/home/<your-username>/app/src'
if path not in sys.path:
    sys.path.append(path)

from app.paw_app import PawApp
PawApp().run()

# import flask app but need to call it "application" for WSGI to work
from app.paw_app import flask_app as application
