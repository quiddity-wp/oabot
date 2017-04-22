Wikipedia OAbot
===============

This tool looks for open access versions of references in Wikipedia articles.

It relies on the Dissemin API and the Zotero translation-server.

[Start editing citations](https://tools.wmflabs.org/oabot/)
-----------------------------------------------------

Usage:
* Install dependencies with `pip install -r requirements.txt`
* Run the script on a Wikipedia article, for instance [Reverse mathematics](http://en.wikipedia.org/wiki/Reverse_mathematics):
  `python main.py "Reverse mathematics"`
* This outputs an HTML summary of the proposed changes on the page.
* You can also run it as a web service with `python app.py` (or as a WSGI application)
