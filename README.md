Wikipedia OABOT proof of concept
================================

This scripts looks for open access versions of references in Wikipedia articles.
If no URL is provided in the citation template, it adds one that points to an open access repository where the reference is available (if we can find one). In the special cases of arXiv or PubMedCentral, it uses the appropriate citation parameters. See the examples below.

Usage:
* Install dependencies with `pip install -r requirements.txt`
* [Install pywikibot](https://www.mediawiki.org/wiki/Manual:Pywikibot/Installation) (unfortunately it's not in pip)
* Run the script on a Wikipedia article, for instance [Reverse mathematics](http://en.wikipedia.org/wiki/Reverse_mathematics):
  `python poc.py "Reverse mathematics"`
* This outputs an HTML summary of the proposed changes on the page.

For instance, here is what you get for the following pages:
* [Alan Turing](http://pintoch.ulminfo.fr/4baafa76fa/turing.html)
* [Reverse mathematics](http://pintoch.ulminfo.fr/4baafa76fa/reverse.html)
* [Pregroup grammar](http://pintoch.ulminfo.fr/4baafa76fa/pregroup.html)
* [Distributional semantics](http://pintoch.ulminfo.fr/4baafa76fa/distr.html)
* [Deep learning](http://pintoch.ulminfo.fr/4baafa76fa/deep.html)
