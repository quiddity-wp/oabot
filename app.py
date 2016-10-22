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
from main import *
import os.path
import md5
from main import OABOT_APP_MOUNT_POINT

@route('/')
def home():
    with open('templates/home.html', 'r') as f:
        homepage = f.read()

    homepage = homepage.replace('OABOT_APP_MOUNT_POINT', OABOT_APP_MOUNT_POINT)

    return homepage


@route('/css/<fname>')
def css(fname):
    return static_file(fname, root='css/')

def cached(fun, force, *args):
    r = md5.md5()
    r.update(args[0].encode('utf-8'))
    h = r.hexdigest()
    cache_fname = 'cache/%s.html' % h
    if not force and os.path.isfile(cache_fname):
	with codecs.open(cache_fname, 'r', 'utf-8') as f:
	    val = f.read()
	return val
    else:
	with codecs.open(cache_fname, 'w', 'utf-8') as f:
	    value = fun(*args)
	    f.write(value)
	return value
    
@route('/process')
def process():
    page_name = request.query.get('name').decode('utf-8')
    force = request.query.get('refresh') == 'true'
    tpl = cached(render_template, force, page_name, request.url)
    return tpl


if __name__ == '__main__':
    arguments = docopt(__doc__, version=__version__)

    port = arguments['--port']

    run(host='localhost', port=port, debug=True)

app = application = default_app()
