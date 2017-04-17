# -*- encoding: utf-8 -*-
from __future__ import unicode_literals
from wikiciteparser.parser import parse_citation_template
from urllib import urlencode
import mwparserfromhell
import requests
import json
import codecs
import sys
import urllib
from unidecode import unidecode
import re
from datetime import datetime
from copy import deepcopy
from difflib import HtmlDiff
import os
from arguments import template_arg_mappings, get_value
from ranking import sort_links
from settings import *
from ondiskcache import OnDiskCache
from classifier import AcademicPaperFilter
import md5

urls_cache = OnDiskCache('urls_cache.pkl')
paper_filter = AcademicPaperFilter()

rg_re = re.compile('(https?://www\.researchgate\.net/)(.*)(publication/[0-9]*)_.*/links/[0-9a-f]*.pdf')


class TemplateEdit(object):
    """
    This represents a proposed change (possibly empty)
    on a citation template
    """
    def __init__(self, tpl):
	"""
	:param tpl: a mwparserfromhell template: the original template
		that we want to change
	"""
	self.template = tpl
	self.orig_string = unicode(self.template)
	r = md5.md5()
	r.update(self.orig_string.encode('utf-8'))
	self.orig_hash = r.hexdigest()
	self.classification = None
        self.conflicting_value = ''
	self.proposed_change = ''
        self.proposed_link = None

    def propose_change(self):
	"""
	Fetches open urls for that template and proposes a change
	"""
        reference = parse_citation_template(self.template)
        tpl_name = unicode(self.template.name).lower().strip()
        if not reference or tpl_name in excluded_templates:
	    self.classification = 'ignored'
            return
	
        sys.stdout.write('.')
        sys.stdout.flush()

        # First check if there is already a link to a full text
        # in the citation.
        already_oa_param = None
        already_oa_value = None
        for argmap in template_arg_mappings:
            if argmap.present_and_free(self.template):
                already_oa_param = argmap.name
                already_oa_value = argmap.get(self.template)

        change = {}

        # If so, we just skip it - no need for more free links
        if already_oa_param:
            self.classification = 'already_open'
            self.conflicting_value = already_oa_value
            return

        # If the template is marked with |registration= or
        # |subscription= , let's assume that the editor tried to find
        # a better version themselves so it's not worth trying.
        if ((get_value(self.template, 'subscription')
            or get_value(self.template, 'registration')) in
            ['yes','y','true']):
            self.classification = 'registration_subscription'
            return

        # Otherwise, try to get a free link
        link = get_oa_link(reference)
        if not link:
            self.classification = 'not_found'
            return

        # We found an OA link!
        self.proposed_link = link

        # Try to match it with an argument
        argument_found = False
        for argmap in template_arg_mappings:
            # Did the link we have got match that argument place?
            match = argmap.extract(link)
            if not match:
                continue

            argument_found = True

            # If this parameter is already present in the template:
            current_value = argmap.get(self.template)
            if current_value:
                change['new_'+argmap.name] = (match,link)

                #if argmap.custom_access:
                #    stats['changed'] += 1
                #    template.add(argmap.custom_access, 'free')
                #else:

                self.classification = 'already_present'
                # don't change anything
                break

            # If the parameter is not present yet, add it
            self.classification = 'link_added'

            if argmap.is_id:
                self.proposed_change = 'id={{%s|%s}}' % (argmap.name,match)
            else:
                self.proposed_change = '%s=%s' % (argmap.name,match)
            break
    
    def update_template(self, change):
        """
        Given a change of the form "param=value", add it to the template
        """
        bits = change.split('=')
        if len(bits) != 2:
            raise ValueError('invalid change')
        param = bits[0].lower().strip()
        value = bits[1].strip()
        self.template.add(param, value)

def remove_diacritics(s):
    return unidecode(s) if type(s) == unicode else s

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
    req = requests.post('http://old.dissem.in/api/query',
                        json=args,
                        headers={'User-Agent':OABOT_USER_AGENT})

    resp = req.json()

    oa_url = None

    # Dissemin's full text detection is not always accurate, so
    # we manually go through each url for the paper and check
    # if it is free to read.
    paper_object = resp.get('paper', {})
    dissemin_pdf_url = paper_object.get('pdf_url')
    print('dissemin_pdf_url')
    print(dissemin_pdf_url)
    return dissemin_pdf_url

    oa_url = None
    candidate_urls = sort_links([
        record.get('splash_url') for record in
        paper_object.get('records',[])
    ])
    for url in sort_links(candidate_urls):
        is_free = check_free_to_read(url)
        if not is_free and url == dissemin_pdf_url:
            # Dissemin thinks that there is a PDF somewhere,
            # but Zotero fails to confirm it: skip, this
            # looks dangerous.
            return
        if is_free:
            # If we found a free URL, we are happy!
	    return url

    # At this point Zotero failed to fetch a full text for all our urls.
    # If Dissemin thinks there is a full text somewhere anyway,
    # skip this citation, because we might do something wrong.
    # For instance, we do not want to add a preprint while the DOI
    # is free to read (but we failed to detect that with Zotero).
    if resp.get('paper',{}).get('pdf_url'):
        return


def add_oa_links_in_references(text):
    """
    Main function of the bot.

    :param text: the wikicode of the page to edit
    :returns: a tuple: the new wikicode, the list of changed templates,
            and edit statistics
    """
    wikicode = mwparserfromhell.parse(text)

    for index, template in enumerate(wikicode.filter_templates()):
        edit = TemplateEdit(template)
        edit.index = index
        edit.propose_change()
        yield edit


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
        'format':'json',},
        headers={'User-Agent':OABOT_USER_AGENT})
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
    return True

def perform_edit(page):
    """
    Performs the edit on the given page
    """
    text = page.get()
    oldid = page.latest_revision_id

    # Check if we can do the edit
    allowed = bot_is_allowed(text, 'OAbot')
    if not allowed:
        print "Not allowed"
	return

    new_wikicode, changed_templates, stats = add_oa_links_in_references(text)

    if new_wikicode == text:
        print "No changes"
        return changed_templates, stats

    page.text = new_wikicode

    # Generate new edit message
    edit_message = 'Added '
    if stats['links_added']:
        edit_message += ('%d free to read link' %
                            stats['links_added'])
        if stats['links_added'] > 1:
            edit_message += 's'

    icons_added = stats['changed'] - stats['links_added']
    if icons_added > 0:
        if stats['links_added']:
            edit_message += ' and '
        edit_message += ('%d access icon' % icons_added)
        if icons_added > 1:
            edit_message += 's'

    edit_message += ' in citations. [[User talk:OAbot|Feedback]]'

    print edit_message

    # Perform the edit
    page.save(edit_message)

    # Get our new revision id
    page.get(force=True)
    revid = page.latest_revision_id
    diffurl = ("https://en.wikipedia.org/w/index.php?diff=%d&oldid=%d"
                %
                (revid, oldid))

    # Generate HTML summary of the changes
    html = render_change(
                text,
                new_wikicode,
                changed_templates,
                stats,
                page.title(),
                '<a href="%s">Edit performed</a>.' %
                diffurl)
    html = render_html_template(html, page.title())

    html_fname = 'edits/%s_%d_%s.html' % (datetime.utcnow().isoformat(),
        oldid,
        urllib.quote(remove_diacritics(page.title(underscore=True))))

    with codecs.open(html_fname, 'w', 'utf-8') as f:
        f.write(html)

    return changed_templates, stats

##################
# HTML rendering #
##################


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



