# -*- encoding: utf-8 -*# -*- encoding: utf-8 -*--
from wikiciteparser.parser import parse_citation_template
#import pywikibot
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

# App mount point, if the environment variable 'OABOT_DEV' is defined then
# mount the application on '/', otherwise mount it under '/oabot'
OABOT_APP_MOUNT_POINT = '/oabot'
if os.environ.get('OABOT_DEV', None) is not None:
    # Mount point is '/'
    OABOT_APP_MOUNT_POINT = ''

# helper
def get_value(template, param):
    if template.has(param, ignore_empty=True):
	return unicode(template.get(param).value)

##############
# Edit logic #
##############

# This section defines the behaviour of the bot.

# See template_arg_mappings below for a list of examples of this class
class ArgumentMapping(object):
    def __init__(self, name, regex, is_id=False, alternate_names=[],
                    group_id=1, always_free=False, custom_access=False):
        """
        :param name: the parameter slot in which the identifier is stored (e.g. arxiv)
        :para is_id: if this parameter is true, we will actually store the identifier in |id={{name| … }} instead of |name.
        :par  regex: the regular expression extract on the URLs that trigger this mapping. The first parenthesis-enclosed group in these regular expressions should contain the id.
        :para alternate_names: alternate parameter slots to look out for - we will not add any identifier if one of them is non-empty.
        :para group_id: position of the identifier in the regex
        :para always_free: the parameter denotes links which are always free
        :para custom_access: name of the custom access parameter
                    associated to this one (if any). If "True", then it will be
                    name+'-access'
        """
        self.name = name
        self.regex = re.compile(regex)
        self.is_id = is_id
        self.alternate_names = alternate_names
        self.group_id = group_id
	self.always_free = always_free
        if type(custom_access) == bool and custom_access:
            custom_access = name+'-access'
        self.custom_access = custom_access

    def get(self, template):
        """
        Get the argument value in a particular template.
        If the parameter should be input as |id=, we return the full
        value of |id=. # TODO refine this
        """
        val = None
        if self.is_id:
            val = get_value(template, 'id')
        else:
            val = get_value(template, self.name)
        for aid in self.alternate_names:
            val = val or get_value(template, aid)
        return val

    def present(self, template):
        return self.get(template) != None

    def present_and_free(self, template):
        """
        When the argument is in the template, and it links to a full text
        according to the access icons
        """
        return (
                self.present(template) and
                    (self.always_free or
                    (self.custom_access and
                        get_value(template, self.custom_access)=='free')
                    )               
                )
        

    def extract(self, url):
        """
        Extract the parameter value from the URL, or None if it does not match
        """
        match = self.regex.match(url)
        if not match:
            return None
        return match.group(self.group_id)

template_arg_mappings = [
    ArgumentMapping(
        'biorxiv', r'https?://(dx\.)?doi\.org/10\.1101/([^ ]*)',
        group_id=2,
        always_free=True),
    ArgumentMapping(
        'doi',
        r'https?://(dx\.)?doi\.org/([^ ]*)',
        group_id=2,
        custom_access=True),
    ArgumentMapping(
        'hdl',
        r'https?://hdl\.handle\.net/([^ ]*)',
        custom_access=True),
    ArgumentMapping(
        'arxiv',
        r'https?://arxiv\.org/abs/(.*)',
        alternate_names=['eprint'],
        always_free=True),
    ArgumentMapping(
        'pmc',
        r'https?://www\.ncbi\.nlm\.nih\.gov/pmc/articles/PMC([^/]*)/?',
        always_free=True),
    ArgumentMapping(
        'citeseerx',
        r'https?://citeseerx\.ist\.psu\.edu/viewdoc/summary\?doi=(.*)',
        always_free=True),
    ArgumentMapping(
        'url',
        r'(.*)'),
    ]

# the bot will not make any changes to these templates
excluded_templates = ['cite arxiv', 'cite web']

def get_oa_link(reference):
    """
    Given a citation template (as parsed by wikiciteparser),
    return a link to a full text for this citation (or None).
    """
    doi = reference.get('ID_list', {}).get('DOI')
    title = reference.get('Title')
    authors = reference.get('Authors', [])
    date = reference.get('Date')

    req = requests.post('http://dissem.in/api/query', json={
        'title':title,
        'authors':authors,
        'date':date,
        'doi':doi,
        })

    resp = req.json()

    oa_url = resp.get('paper', {}).get('pdf_url')

    # Temporary hack - some PMC links from BASE don't provide a PMC id
    if oa_url == 'http://www.ncbi.nlm.nih.gov/pmc/articles/PMC':
	oa_url = None

    # Try with DOAI if the dissemin API did not return a full text link
    if oa_url is None and doi:
        r = requests.head('http://doai.io/'+doi)
        if 'location' in r.headers and not 'doi.org/10.' in r.headers['location']:
            oa_url = r.headers['location']

    return oa_url

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

    with open('templates/skeleton.html','r') as f:
        skeleton = f.read()

    try:
        #site = pywikibot.Site()
        #page = pywikibot.Page(site, page_name)
        #text, page_name = get_text(page)
        text = get_page_over_api(page_name)
    except (pywikibot.exceptions.Error, ValueError) as e:
        html = "<p><strong>Error:</strong> "+unicode(e)+"</p>"
        skeleton = skeleton.replace('OABOT_BODY_GOES_HERE', html)
        skeleton = skeleton.replace('OABOT_PAGE_NAME', '')
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
