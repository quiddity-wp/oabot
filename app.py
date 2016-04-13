# -*- encoding: utf-8 -*-
from bottle import route, run, static_file, request
from poc import *

@route('/')
def home():
    return static_file('home.html', root='templates/')

@route('/css/<fname>')
def css(fname):
    return static_file(fname, root='css/')

@route('/process')
def process():
    page_name = request.query.get('name')
    tpl = render_template(page_name)
    return tpl

run(host='localhost', port=8000, debug=True)

