# -*- encoding: utf-8 -*-
from __future__ import unicode_literals
from wikiciteparser.parser import parse_citation_template
from urllib import urlencode
import mwparserfromhell
import requests
import json
import codecs
import sys
from unidecode import unidecode
import re
from datetime import datetime
from copy import deepcopy
from difflib import HtmlDiff
import os
from arguments import template_arg_mappings, get_value

# App mount point, if the environment variable 'OABOT_DEV' is defined then
# mount the application on '/', otherwise mount it under '/oabot'
OABOT_APP_MOUNT_POINT = '/oabot'
if os.environ.get('OABOT_DEV', None) is not None:
    # Mount point is '/'
    OABOT_APP_MOUNT_POINT = ''

# the bot will not make any changes to these templates
excluded_templates = ['cite arxiv', 'cite web', 'cite news', 'cite book']

# Set the API key for the Zotero endpoint here.
# This Zotero endpoint is just a version of 
# https://github.com/zotero/translation-server
# protected by an API key (otherwise it would allow
# anyone use it to query any website, which is dangerous)
#
# Ask for an API key at  dev @ dissem . in
# 
ZOTERO_CACHE_API_KEY = open('zotero_cache_key.txt','r').read().strip()
if not ZOTERO_CACHE_API_KEY:
    raise ValueError('Please provide a Zotero cache API key '+
                    '(email dev @ dissem . in to get one.)')

rg_re = re.compile('(https?://www\.researchgate\.net/.*/publication/[0-9]*)_.*/links/[0-9a-f]*.pdf')

def get_oa_link(reference):
    """
    Given a citation template (as parsed by wikiciteparser),
    return a link to a full text for this citation (or None).
    """
    doi = reference.get('ID_list', {}).get('DOI')
    title = reference.get('Title')
    authors = reference.get('Authors', [])
    date = reference.get('Date')

    # CS1 represents unparsed authors as {'last':'First Last'}
    for i in range(len(authors)):
        if 'first' not in authors[i]:
            authors[i] = {'plain':authors[i].get('last','')}

    args = {
        'title':title,
        'authors':authors,
        'date':date,
        'doi':doi,
        }
    req = requests.post('http://dissem.in/api/query', json=args)


    resp = req.json()

    oa_url = None
    # Dissemin's full text detection is not always accurate, so
    # we manually go through each url for the paper and check
    # if it is free to read.
    oa_url = None
    candidate_urls = [
        record.get('splash_url') for record in
        resp.get('paper',{}).get('records',[])
    ]
    free_urls = filter(check_free_to_read, candidate_urls)
    if free_urls:
        return free_urls[0]

    # Try with DOAI if the dissemin API did not return a full text link
    oa_url = None
    if doi:
        r = requests.head('http://doai.io/'+doi)
        if 'location' in r.headers and not 'doi.org/10.' in r.headers['location']:
            oa_url = r.headers['location']

    if not oa_url:
        return
    
    # Only keep results from researchgate.net or academia.edu from DOAI
    if not (oa_url.startswith('https://www.researchgate.net') or 
        oa_url.startswith('https://www.academia.edu')):
        return

    # ResearchGate PDF links actually lead to HTML, so let's make them
    # point to the splash page directly
    rg_match = rg_re.match(oa_url)
    if rg_match:
        oa_url = rg_match.group(1)

    return oa_url

def check_free_to_read(url):
    """
    Checks (with Zotero translators) that a given URL is free to read
    """
    r = requests.post('http://doi-cache.dissem.in/zotero/query',
                data={
            'url':url,
            'key':ZOTERO_CACHE_API_KEY,
            })

    # Is a full text available there?
    items = None
    try:
        items = r.json()
    except ValueError:
        if r.status_code == 403:
            raise ValueError("Please provide a valid Zotero cache API key")
    if not items:
        return False

    for item in items:
        for attachment in item.get('attachments',[]):
            if attachment.get('mimeType') == 'application/pdf':
                return True
    return False

def add_oa_links_in_references(text):
    """
    Main function of the bot.
    
    :param text: the wikicode of the page to edit
    :returns: a tuple: the new wikicode, the list of changed templates,
            and edit statistics
    """
    wikicode = mwparserfromhell.parse(text)
    changed_templates = []

    stats = {
        # total number of templates processed (not counting excluded
        # ones)
        'nb_templates':0,
        # actual changes on the templates (including access-related changes)
        'changed':0,
	# Links actually added to the templates
        'links_added':0,
        # no change because one link was already marked with the open
        # lock
        'already_open':0,
        # no change because the |url= we tried to add was already present
        'url_present':0,
        }

    for template in wikicode.filter_templates():
        orig_template = deepcopy(template)
        reference = parse_citation_template(template)
        tpl_name = unicode(template.name).lower().strip()
        if reference and tpl_name not in excluded_templates:
            stats['nb_templates'] += 1

            # First check if there is already a link to a full text
            # in the citation.
            already_oa_param = None
            already_oa_value = None
            for argmap in template_arg_mappings:
                if argmap.present_and_free(template):
                    already_oa_param = argmap.name
                    already_oa_value = argmap.get(template)
            
            change = {}
        
            # If so, we just skip it - no need for more free links
            if already_oa_param:
                change['new_'+already_oa_param] = (already_oa_value,'#')
                stats['already_open'] += 1
		changed_templates.append((orig_template, change))
                continue

            # If the template is marked with |registration= or
            # |subscription= , let's assume that the editor tried to find
            # a better version themselves so it's not worth trying.
            if (get_value(template, 'subscription') or get_value(template,
'registration')) in ['yes','y','true']:
                stats['registration_subscription'] += 1
                continue

            # Otherwise, try to get a free link
            link = get_oa_link(reference)
            if not link:
                changed_templates.append((orig_template,None))
                continue

            # We found an OA link!

            # Try to match it with an argument
            argument_found = False
            for argmap in template_arg_mappings:
                # Did the link we have got match that argument place?
                match = argmap.extract(link)
                if not match:
                    continue

                argument_found = True

                # If this parameter is already present in the template:
                current_value = argmap.get(template)
                if current_value:
                    change['new_'+argmap.name] = (match,link)
                    if argmap.custom_access:
                        stats['changed'] += 1
                        template.add(argmap.custom_access, 'free')
		    else:
			stats['url_present'] += 1
                    	# don't change anything
                    break

                # If the parameter is not present yet, add it
                stats['changed'] += 1
		stats['links_added'] += 1
		if argmap.is_id:
                    val = '{{%s|%s}}' % (argmap.name,match)
                    template.add('id', val)
                    change['id'] = (val,link)
                else:
                    template.add(argmap.name, match)
                    change[argmap.name] = (match,link)
		    if argmap.custom_access:
			template.add(argmap.custom_access, 'free')
                break

            changed_templates.append((orig_template, change))
    
    return unicode(wikicode), changed_templates, stats


def get_text(page, max_hops=3):
    try:
        text = page.get(throttle=False)
        return text, page.title()
    except pywikibot.IsRedirectPage as e:
        if max_hops:
            return get_text(page.getRedirectTarget(), max_hops=max_hops-1)
        else:
            raise e

def get_page_over_api(page_name):
    r = requests.get('https://en.wikipedia.org/w/api.php', params={
        'action':'query',
        'titles':page_name,
        'prop':'revisions',
        'rvprop':'content',
        'format':'json',})
    js = r.json()
    page = js.get('query',{}).get('pages',{}).values()[0]
    pagid = page.get('pageid', -1)
    if pagid == -1:
        raise ValueError("Invalid page.")
    text = page.get('revisions',[{}])[0]['*']
    return text

def bot_is_allowed(text, user):
    """
    Taken from https://en.wikipedia.org/wiki/Template:Bots
    For bot exclusion compliance.
    """
    user = user.lower().strip()
    text = mwparserfromhell.parse(text)
    for tl in text.filter_templates():
        if tl.name in ('bots', 'nobots'):
            break
    else:
        return True
    for param in tl.params:
        bots = [x.lower().strip() for x in param.value.split(",")]
        if param.name == 'allow':
            if ''.join(bots) == 'none': return False
            for bot in bots:
                if bot in (user, 'all'):
                    return True
        elif param.name == 'deny':
            if ''.join(bots) == 'none': return True
            for bot in bots:
                if bot in (user, 'all'):
                    return False
    return False

def perform_edit(page):
    """
    Performs the edit on the given page
    """
    text = page.get()

    # Check if we can do the edit
    allowed = bot_is_allowed(text, 'OAbot')
    if not allowed:
	return

    new_wikicode, changed_templates, stats = add_oa_links_in_references(text)

    if new_wikicode == text:
        return changed_templates, stats

    page.text = new_wikicode
    edit_message = 'Added open access links in '
    if stats['changed'] == 1:
        edit_message += '1 citation.'
    else:
        edit_message += ('%d citations.' % stats['changed'])
    page.save(edit_message)
    return changed_templates, stats

##################
# HTML rendering #
##################

# This section defines the web interface demonstrating
# the potential edits of the bot.

def make_diff(old, new):
    """
    Render in HTML the diff between two texts
    """
    df = HtmlDiff()
    old_lines = old.splitlines(1)
    new_lines = new.splitlines(1)
    html = df.make_table(old_lines, new_lines, context=True)
    html = html.replace(' nowrap="nowrap"','')
    return html


def render_template(page_name, this_url='#'):

    with codecs.open('templates/skeleton.html','r', 'utf-8') as f:
        skeleton = f.read()

    try:
        #site = pywikibot.Site()
        #page = pywikibot.Page(site, page_name)
        #text, page_name = get_text(page)
        text = get_page_over_api(page_name)
    except ValueError as e:
        html = "<p><strong>Error:</strong> "+unicode(e)+"</p>"
        skeleton = skeleton.replace('OABOT_BODY_GOES_HERE', html)
        skeleton = skeleton.replace('OABOT_PAGE_NAME', '')
        skeleton = skeleton.replace('OABOT_APP_MOUNT_POINT',
OABOT_APP_MOUNT_POINT)
        return skeleton

    new_wikicode, changed_templates, stats = add_oa_links_in_references(text)
    with codecs.open('new_wikicode', 'w', 'utf-8') as f:
        f.write(new_wikicode)

    page_url = 'https://en.wikipedia.org/wiki/'+page_name #'https:'+page.permalink()

    html = '<h2>Results for page <a href="%s">OABOT_PAGE_NAME</a></h2>\n' % page_url
    html += '<p>Processed: %s (<a href="%s&refresh=true">refresh</a>)</p>\n' % (datetime.utcnow().isoformat(), this_url)
    html += '<p>This is only a simulation, no edit was performed.</p>'

    # Check for exclusion
    if not bot_is_allowed(text, 'OAbot'):
	html += '<p><strong>Note:</strong> The bot is <a href="https://en.wikipedia.org/wiki/Template:Bots">not allowed</a> to edit this page.</p>'

    # Print stats
    html += '<table class="edit-stats">'
    html += '<tr><td>Citations checked</td><td>%s</td></tr>\n' % stats['nb_templates']
    html += '<tr><td>* Citations changed</td><td>%s</td>\n' % stats['changed']
    html += '<tr><td>&nbsp;&nbsp;+ Citations with a new free link</td><td>%s</td></tr>\n' % stats['links_added']
    html += '<tr><td>&nbsp;&nbsp;+ No new free link, but new access icon</td><td>%s</td></tr>\n' % (stats['changed']-stats['links_added'])
    html += '<tr><td>* Citations left unchanged</td><td>%s</td>\n' % (stats['nb_templates']-stats['changed'])
    html += '<tr><td>&nbsp;&nbsp;+ Green lock already present</td><td>%s</td></tr>\n' % stats['already_open']
    html += '<tr><td>&nbsp;&nbsp;+ No room for a new |url=</td><td>%s</td></tr>\n' % stats['url_present']
    html += '<tr><td>&nbsp;&nbsp;+ No free version found</td><td>%s</td></tr>\n' % (stats['nb_templates']-stats['changed']-stats['url_present']-stats['already_open'])
    html += '</table>'

    # Render changes

    html += '<h3>Template details</h3>\n' # (%d)</h3>\n' % len(changed_templates)
    html += '<ol>\n'
    for template, change in changed_templates:
        html += '<li>'
        html += '<pre>'+unicode(template)+'</pre>\n'
        if not change:
            reference = parse_citation_template(template)
            title = unidecode(reference.get('Title'))
            gs_url = 'http://scholar.google.com/scholar?'+urlencode({'q':title})
            html += ('No OA version found. '+
             ('<a href="%s">Search in Google Scholar</a>' % gs_url) )
            continue
        html += '<ul>\n'
        for key, (val,link) in change.items():
            if key.startswith('new_'):
                key = key[4:]
                html += '<li>Already present: <span class="template_param">%s=' % key
            else:
                html += '<strong>Added:</strong>\n<li><span class="template_param">%s=' % key
            html += '<a href="%s">%s</a>' % (link,val)
            html += '</span></li>\n'
        html += '</ul>\n</li>\n'
    html += '</ol>\n'

    # Render diff
    html += '<h3>Wikicode diff</h3>\n'
    html += make_diff(text, new_wikicode)+'\n'

    skeleton = skeleton.replace('OABOT_APP_MOUNT_POINT', OABOT_APP_MOUNT_POINT)
    skeleton = skeleton.replace('OABOT_BODY_GOES_HERE', html)
    skeleton = skeleton.replace('OABOT_PAGE_NAME', page_name)

    return skeleton

if __name__ == '__main__':
    page_name = sys.argv[1]
    site = pywikibot.Site()
    page = pywikibot.Page(site, page_name)
    changed_templates, stats = perform_edit(page)
    print "Edit successfully performed"
