# -*- coding: utf-8 -*-
#
# This file is mostly taken from the Tool Labs Flask + OAuth WSGI tutorial
# https://wikitech.wikimedia.org/wiki/Help:Tool_Labs/My_first_Flask_OAuth_tool
#
# Copyright (C) 2017 Bryan Davis and contributors
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free
# Software Foundation, either version 3 of the License, or (at your
# option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# for
# more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.

import flask
import os
import yaml
import mwoauth
from settings import OABOT_APP_MOUNT_POINT
import requests
import json
from requests_oauthlib import OAuth1

app = flask.Flask(__name__)

__dir__ = os.path.dirname(__file__)
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'config.yaml'))))

@app.route('/')
def index():
    context = {
        'username' : flask.session.get('username', None),
        'OABOT_APP_MOUNT_POINT' : OABOT_APP_MOUNT_POINT,
    }
    return flask.render_template("index.html", **context)

authenticate = {}
usernames = { 'wikipedia': {} }

@app.route('/test-edit')
def test_edit():
    """
    Perform a test edit
    """
    global authenticate
    global usernames
    try:
	    access_token = flask.session.get('access_token', None)
	    username = flask.session.get('username', None)
	    if not access_token or not username:
		return flask.redirect(flask.url_for('login'))
	    authenticate = {}
	    authenticate['en.wikipedia.org'] = (
		app.config['CONSUMER_KEY'],
		app.config['CONSUMER_SECRET'],
		access_token['key'],
		access_token['secret'])
	    usernames['wikipedia']['en'] = username
	    
            edit_wiki_page('User:%s/sandbox' % username, 'just testing',
			summary='just testing')
	
    except Exception as e:
	with open('exception', 'w') as f:
		f.write(str(type(e))+' '+str(e))
    return flask.redirect(flask.url_for('index'))

def edit_wiki_page(page_name, content, summary=None):
    access_token = flask.session.get('access_token', None)
    auth = OAuth1(
		app.config['CONSUMER_KEY'],
		app.config['CONSUMER_SECRET'],
		access_token['key'],
		access_token['secret'])

    # Get token
    r = requests.get('https://en.wikipedia.org/w/api.php', params={
	'action':'query',
	'meta':'tokens',
        'format': 'json',
    }, auth=auth)
    r.raise_for_status()
    token = r.json()['query']['tokens']['csrftoken']
    
    r = requests.post('https://en.wikipedia.org/w/api.php', data={
	'action':'edit',
        'title': page_name,
	'text': content,
        'summary': summary,
        'format': 'json',
        'token': token,
    }, auth=auth)
    r.raise_for_status()
	

@app.route('/login')
def login():
    """Initiate an OAuth login.

    Call the MediaWiki server to get request secrets and then redirect
the
    user to the MediaWiki server to sign the request.
    """
    consumer_token = mwoauth.ConsumerToken(
        app.config['CONSUMER_KEY'], app.config['CONSUMER_SECRET'])
    try:
        redirect, request_token = mwoauth.initiate(
            app.config['OAUTH_MWURI'], consumer_token)
    except Exception:
        app.logger.exception('mwoauth.initiate failed')
        return flask.redirect(flask.url_for('index'))
    else:
        flask.session['request_token'] = dict(zip(
            request_token._fields, request_token))
        return flask.redirect(redirect)


@app.route('/oauth-callback')
def oauth_callback():
    """OAuth handshake callback."""
    if 'request_token' not in flask.session:
        flask.flash(u'OAuth callback failed. Are cookies disabled?')
        return flask.redirect(flask.url_for('index'))

    consumer_token = mwoauth.ConsumerToken(
        app.config['CONSUMER_KEY'], app.config['CONSUMER_SECRET'])

    try:
        access_token = mwoauth.complete(
            app.config['OAUTH_MWURI'],
            consumer_token,
            mwoauth.RequestToken(**flask.session['request_token']),
            flask.request.query_string)

        identity = mwoauth.identify(
            app.config['OAUTH_MWURI'], consumer_token, access_token)
    except Exception as e:
        app.logger.exception('OAuth authentication failed')

    else:
        flask.session['access_token'] = dict(zip(
            access_token._fields, access_token))
        flask.session['username'] = identity['username']

    return flask.redirect(flask.url_for('index'))


@app.route('/logout')
def logout():
    """Log the user out by clearing their session."""
    flask.session.clear()
    return flask.redirect(flask.url_for('index'))

if __name__ == "__main__":
    app.run(host='0.0.0.0')

