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

template_arg_mappings = {
    'doi': re.compile(r'https?://dx\.doi\.org/([^ ]*)'),
    'arxiv': re.compile(r'https?://arxiv\.org/abs/(.*)'),
    'pmc': re.compile(r'https?://www\.ncbi\.nlm\.nih\.gov/pmc/articles/PMC([^/]*)/?'),
    }

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
    return resp.get('paper', {}).get('pdf_url')

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
                continue

            doi_prefix = 'http://dx.doi.org/'
            arxiv_prefix = 'http://arxiv.org/abs/'
            change = {}

            argument_found = False
            for arg, regex in template_arg_mappings.items():
                match = regex.match(link)
                if not match:
                    continue
                argument_found = True
                if not template.has(arg, ignore_empty=True):
                    template.add(arg, match.group(1))
                    change[arg] = (match.group(1),link)
                    break

            if not argument_found and not template.has('url', ignore_empty=True):
                template.add('url', link)
                change['url'] = (link,link)

            if change:
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
        text = page.get()
        return text, page.title()
    except pywikibot.IsRedirectPage as e:
        if max_hops:
            return get_text(page.getRedirectTarget())
        else:
            raise e

def render_template(page_name):
    site = pywikibot.Site()

    with open('templates/skeleton.html','r') as f:
        skeleton = f.read()

    try:
        page = pywikibot.Page(site, page_name)
        text, page_name = get_text(page)
    except (pywikibot.exceptions.Error, ValueError) as e:
        html = "<p><strong>Error:</strong> "+unicode(e)+"</p>"
        skeleton = skeleton.replace('OABOT_BODY_GOES_HERE', html)
        skeleton = skeleton.replace('OABOT_PAGE_NAME', '')
        return skeleton

    new_wikicode, changed_templates, nb_templates = add_oa_links_in_references(text)
    with codecs.open('new_wikicode', 'w', 'utf-8') as f:
        f.write(new_wikicode)

    page_url = 'https:'+page.permalink()
    page_revision = page.latest_revision_id
    page_rev_url = 'https:'+page.permalink(page_revision)

    html = '<h2>Results for page <a href="%s">OABOT_PAGE_NAME</a></h2>\n' % page_url
    html += '<p>Revision: <a href="%s">#%d</a></p>\n' % (page_rev_url,page_revision)
    html += '<p>Processed: %s</p>\n' % (datetime.utcnow().isoformat())
    html += '<p>Citation templates found: %d</p>\n' % nb_templates

    if not changed_templates:
        html += '<p><strong>No changes were made for this page.</strong></p>\n'
    else:
        # Render changes
        html += '<h3>Templates changed (%d)</h3>\n' % len(changed_templates)
        html += '<ol>\n'
        for template, change in changed_templates:
            html += '<li>'
            html += '<pre>'+unicode(template)+'</pre>\n'
            html += '<strong>Added:</strong>\n<ul>\n'
            for key, (val,link) in change.items():
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


