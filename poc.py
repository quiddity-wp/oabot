# -*- encoding: utf-8 -*# -*- encoding: utf-8 -*--
from wikiciteparser.parser import parse_citation_template
import pywikibot
import mwparserfromhell
import requests
import json
import codecs
import sys
import re
from datetime import datetime
from copy import deepcopy
from difflib import HtmlDiff


# See template_arg_mappings below for a list of examples of this class
class ArgumentMapping(object):
    def __init__(self, name, regex, is_id=False, alternate_names=[]):
        """
        :param name: the parameter slot in which the identifier is stored (e.g. arxiv)
        :para is_id: if this parameter is true, we will actually store the identifier in |id={{name| … }} instead of |name.
        :par  regex: the regular expression extract on the URLs that trigger this mapping. The first parenthesis-enclosed group in these regular expressions should contain the id.
        :para alternate_names: alternate parameter slots to look out for - we will not add any identifier if one of them is non-empty.
        """
        self.name = name
        self.regex = re.compile(regex)
        self.is_id = is_id
        self.alternate_names = alternate_names

    def present(self, template):
        """
        Is this argument already present in the template?
        """
        # Check if the parameter is non-empty (or any alternate places)
        non_empty = (not self.is_id and template.has(self.name, ignore_empty=True))
        non_empty = non_empty or (self.is_id and template.has('id', ignore_empty=True))
        non_empty = non_empty or any([template.has(aid, ignore_empty=True) for aid in self.alternate_names])
        return non_empty

    def extract(self, url):
        """
        Extract the parameter value from the URL, or None if it does not match
        """
        match = self.regex.match(url)
        if not match:
            return None
        return match.group(1)

template_arg_mappings = [
    ArgumentMapping('doi', r'https?://dx\.doi\.org/([^ ]*)'),
    ArgumentMapping('hdl', r'https?://hdl\.handle\.net/([^ ]*)'),
    ArgumentMapping('arxiv', r'https?://arxiv\.org/abs/(.*)', alternate_names=['eprint']),
    ArgumentMapping('pmc', r'https?://www\.ncbi\.nlm\.nih\.gov/pmc/articles/PMC([^/]*)/?'),
    ArgumentMapping('citeseerx', r'https?://citeseerx\.ist\.psu\.edu/viewdoc/summary\?doi=(.*)', is_id=True),
    ArgumentMapping('url', r'(.*)'),
    ]

def get_oa_link(reference):
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

    # Try with DOAI if the dissemin API did not return a full text link
    if oa_url is None and doi:
        r = requests.head('http://doai.io/'+doi)
        if 'location' in r.headers and not 'doi.org/10.' in r.headers['location']:
            oa_url = r.headers['location']

    return oa_url

def add_oa_links_in_references(text):
    wikicode = mwparserfromhell.parse(text)
    changed_templates = []

    stats = {
        'nb_templates':0, # total number of templates processed
        'oa_found':0, # hits from the API
        'changed':0, # actual changes on the templates
        'already_present':0, # no change because already present
        }

    for template in wikicode.filter_templates():
        orig_template = deepcopy(template)
        reference = parse_citation_template(template)
        if reference:
            stats['nb_templates'] += 1
            link = get_oa_link(reference)
            if not link:
                changed_templates.append((orig_template,None))
                continue

            # We found an OA link!
            stats['oa_found'] += 1

            change = {}

            argument_found = False
            for argmap in template_arg_mappings:
                # Did the link we have got match that argument place?
                match = argmap.extract(link)
                if not match:
                    continue

                argument_found = True

                # If this parameter is already present in the template,
                # don't change anything
                non_empty = argmap.present(template)           
                if non_empty:
                    change['new_'+argmap.name] = (match,link)
                    stats['already_present'] += 1
                    break

                # If the parameter is not present yet, add it
                stats['changed'] += 1
                if not argmap.is_id:
                    template.add(argmap.name, match)
                    change[argmap.name] = (match,link)
                else:
                    val = '{{%s|%s}}' % (argmap.name,match)
                    template.add('id', val)
                    change['id'] = (val,link)
                break

            changed_templates.append((orig_template, change))
    
    return unicode(wikicode), changed_templates, stats

def make_diff(old, new):
    df = HtmlDiff()
    old_lines = old.splitlines(1)
    new_lines = new.splitlines(1)
    html = df.make_table(old_lines, new_lines, context=True)
    html = html.replace(' nowrap="nowrap"','')
    return html

def get_text(page, max_hops=3):
    try:
        text = page.get(throttle=False)
        return text, page.title()
    except pywikibot.IsRedirectPage as e:
        if max_hops:
            return get_text(page.getRedirectTarget())
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

def render_template(page_name, this_url='#'):
    site = pywikibot.Site()

    with open('templates/skeleton.html','r') as f:
        skeleton = f.read()

    try:
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

    # Print stats
    html += '<p>Citation templates found: %s</p>\n' % stats['nb_templates']
    html += '<p>Hits from the APIs: %s</p>\n' % stats['oa_found']
    html += '<p>Templates changed: %s</p>\n' % stats['changed']
    html += '<p>Templates not changed because the parameter was already present: %s</p>\n' % stats['already_present']

    # Render changes

    html += '<h3>Template details</h3>\n' # (%d)</h3>\n' % len(changed_templates)
    html += '<ol>\n'
    for template, change in changed_templates:
        html += '<li>'
        html += '<pre>'+unicode(template)+'</pre>\n'
        if not change:

            html += '<strong>No OA version found.</strong>'
            continue
        html += '<strong>Added:</strong>\n<ul>\n'
        for key, (val,link) in change.items():
            if key.startswith('new_'):
                key = key[4:]
                html += '<li>Already present: <span class="template_param">%s=' % key
            else:
                html += '<li><span class="template_param">%s=' % key
            html += '<a href="%s">%s</a>' % (link,val)
            html += '</span></li>\n'
        html += '</ul>\n</li>\n'
    html += '</ol>\n'

    # Render diff
    html += '<h3>Wikicode diff</h3>\n'
    html += make_diff(text, new_wikicode)+'\n'

    skeleton = skeleton.replace('OABOT_BODY_GOES_HERE', html)
    skeleton = skeleton.replace('OABOT_PAGE_NAME', page_name)

    return skeleton

if __name__ == '__main__':
    page_name = sys.argv[1]
    print render_template(page_name).encode('utf-8')



