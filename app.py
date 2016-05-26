# -*- encoding: utf-8 -*-
from bottle import route, run, static_file, request, default_app
from poc import *
from poc import OABOT_APP_MOUNT_POINT


@route('/')
def home():
    with open('templates/home.html','r') as f:
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
	run(host='localhost', port=8000, debug=True)

app = application = default_app()
