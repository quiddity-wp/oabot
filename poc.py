from wikiciteparser.parser import parse_citation_template
import pywikibot
import mwparserfromhell
import requests
import json
import sys

site = pywikibot.Site()

def references_in_page(page_name):
    page = pywikibot.Page(site, page_name)
    text = page.get()
    wikicode = mwparserfromhell.parse(text)

    return map(parse_citation_template, wikicode.filter_templates())

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



for ref in references_in_page(sys.argv[1]):
    if ref:
        print ref
        print get_oa_link(ref)
        print


