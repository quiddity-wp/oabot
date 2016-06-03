Wikipedia OAbot
===============

This scripts looks for open access versions of references in Wikipedia articles.
If no URL is provided in the citation template, it adds one that points to an open access repository where the reference is available (if we can find one). In the special cases of arXiv or PubMedCentral, it uses the appropriate citation parameters. See the examples below.

[Try the demo here](https://tools.wmflabs.org/oabot/)
-----------------------------------------------------

Usage:
* Install dependencies with `pip install -r requirements.txt`
* [Install pywikibot](https://www.mediawiki.org/wiki/Manual:Pywikibot/Installation) (unfortunately it's not in pip)
* Run the script on a Wikipedia article, for instance [Reverse mathematics](http://en.wikipedia.org/wiki/Reverse_mathematics):
  `python poc.py "Reverse mathematics"`
* This outputs an HTML summary of the proposed changes on the page.
* You can also run it as a web service with `python app.py` (or as a WSGI application)

For instance, here is what you get for the following pages (this takes some time to load as it yiels many API calls):
* [Alan Turing](https://tools.wmflabs.org/oabot/process?name=Alan+Turing)
* [Reverse mathematics](https://tools.wmflabs.org/oabot/process?name=Reverse+mathematics)
* [Pregroup grammar](https://tools.wmflabs.org/oabot/process?name=Pregroup+grammar)
* [Distributional semantics](https://tools.wmflabs.org/oabot/process?name=Distributional+semantics)
* [Deep learning](https://tools.wmflabs.org/oabot/process?name=Deep+learning)
