#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""OAbot web interface

Usage:
  app.py [-p PORT| --port PORT]
  app.py (-h | --help)
  app.py --version

Options:
  -p, --port PORT   Mount the application on port PORT [default: 8000].
  --version         Show version.
  -h --help         Show this screen.

"""
__version__ = '0.0.1'

from bottle import route, run, static_file, request, default_app
from docopt import docopt
from poc import *
from poc import OABOT_APP_MOUNT_POINT


@route('/')
def home():
    with open('templates/home.html', 'r') as f:
        homepage = f.read()

    homepage = homepage.replace('OABOT_APP_MOUNT_POINT', OABOT_APP_MOUNT_POINT)

    return homepage


@route('/css/<fname>')
def css(fname):
    return static_file(fname, root='css/')


@route('/process')
def process():
    page_name = request.query.get('name')
    tpl = render_template(page_name)
    return tpl


if __name__ == '__main__':
    arguments = docopt(__doc__, version=__version__)

    port = arguments['--port']

    run(host='localhost', port=port, debug=True)

app = application = default_app()
