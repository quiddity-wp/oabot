# -*- encoding: utf-8 -*-
from bottle import route, run, static_file, request, default_app
from poc import *
import os.path
import md5

@route('/')
def home():
    return static_file('home.html', root='templates/')

@route('/css/<fname>')
def css(fname):
    return static_file(fname, root='css/')

def cached(fun, force, *args):
    r = md5.md5()
    r.update(args[0])
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
    page_name = request.query.get('name')
    force = request.query.get('refresh') == 'true'
    tpl = cached(render_template, force, page_name, request.url)
    return tpl

if __name__ == '__main__':
	run(host='localhost', port=8000, debug=True)

app = application = default_app()
