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

# How to use this dict:
# - keys are triples
#    - the first part (string) indicates the name of the identifier
#    - the second part (bool) indicates whether it is
#       * a template argument (as in {{cite journal|doi=10.1007/test}})
#       * a template in the id= argument (as in {{cite journal|id={{citeseerx|10.1.1.104.7535}})
#    - the third part (list) is a list of alternate places where this
#      parameter can be found - the bot should not add the parameter if any of these
#      alternate places are non-empty
# - the values are the regular expressions on the URLs that trigger these mappings
#   The first parenthesis-enclosed group in these regular expressions should contain the id

class ArgumentMapping(object):
    def __init__(self, name, regex, is_id=False, alternate_names=[]):
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
    nb_templates = 0

    for template in wikicode.filter_templates():
        orig_template = deepcopy(template)
        reference = parse_citation_template(template)
        if reference:
            nb_templates += 1
            link = get_oa_link(reference)
            if not link:
                changed_templates.append((orig_template,None))
                continue

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
                    break

                # If the parameter is not present yet, add it
                if not argmap.is_id:
                    template.add(argmap.name, match)
                    change[argmap.name] = (match,link)
                else:
                    val = '{{%s|%s}}' % (argmap.name,match)
                    template.add('id', val)
                    change['id'] = (val,link)
                break

            changed_templates.append((orig_template, change))
    
    return unicode(wikicode), changed_templates, nb_templates

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

    new_wikicode, changed_templates, nb_templates = add_oa_links_in_references(text)
    with codecs.open('new_wikicode', 'w', 'utf-8') as f:
        f.write(new_wikicode)

    page_url = 'https://en.wikipedia.org/wiki/'+page_name #'https:'+page.permalink()

    html = '<h2>Results for page <a href="%s">OABOT_PAGE_NAME</a></h2>\n' % page_url
    html += '<p>Processed: %s (<a href="%s&refresh=true">refresh</a>)</p>\n' % (datetime.utcnow().isoformat(), this_url)
    html += '<p>Citation templates found: %d</p>\n' % nb_templates

#    if not changed_templates:
#        html += '<p><strong>No changes were made for this page.</strong></p>\n'
#    else:

   # Render changes

    html += '<h3>Templates changed</h3>\n' # (%d)</h3>\n' % len(changed_templates)
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



