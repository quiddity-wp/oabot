Wikipedia OABOT proof of concept
================================

This scripts looks for OA versions of references in Wikipedia articles.

Usage:
* Install dependencies with `pip install -r requirements.txt`
* [Install pywikibot](https://www.mediawiki.org/wiki/Manual:Pywikibot/Installation) (unfortunately it's not in pip)
* Run the script on a Wikipedia article, for instance [Reverse mathematics](http://en.wikipedia.org/wiki/Reverse_mathematics):
  `python poc.py "Reverse mathematics"`

Here is what you get:

    {u'Title': u'Comparing DNR and WWKL', u'ID_list': {u'DOI': u'10.2178/jsl/1102022212'}, u'Periodical': u'Journal of Symbolic Logic', u'Authors': [{u'last': u'Ambos-Spies, K.'}], u'Date': u'2004', u'Pages': u'1089'}
    http://arxiv.org/abs/1408.2281

    {u'Chapter': u'Some systems of second order arithmetic and their use', u'PublisherName': u'Canad. Math. Congress, Montreal, Que.', u'Title': u'Proceedings of the International Congress of Mathematicians (Vancouver, B. C., 1974), Vol. 1', u'ID_list': {u'MR': u'0429508'}, u'Authors': [{u'last': u'Friedman', u'first': u'Harvey'}], u'Date': u'1975', u'Pages': u'235-242'}
    None

    {u'PublisherName': u'Association for Symbolic Logic', u'Title': u'Meeting of the Association for Symbolic Logic: Systems of second order arithmetic with restricted induction,  I, II', u'ID_list': {u'DOI': u'10.2307/2272259'}, u'Periodical': u'The Journal of Symbolic Logic', u'Authors': [{u'last': u'Friedman', u'first': u'Harvey'}, {u'last': u'Martin', u'first': u'D. A.'}, {u'last': u'Soare', u'first': u'R. I.'}, {u'last': u'Tait', u'first': u'W. W.'}], u'Date': u'1976', u'Pages': u'557-559'}
    None

    {u'PublisherName': u'Cambridge University Press', u'ID_list': {u'ISBN': u'978-0-521-88439-6', u'MR': u'2517689'}, u'URL': u'http://www.math.psu.edu/simpson/sosoa/', u'Series': u'Perspectives in Logic', u'Title': u'Subsystems of second order arithmetic', u'Edition': u'2nd', u'Authors': [{u'last': u'Simpson', u'first': u'Stephen G.'}], u'Date': u'2009'}
    None

    {u'Title': u'Ordered groups: a case study in reverse mathematics', u'ID_list': {u'DOI': u'10.2307/421140', u'ISSN': u'1079-8986', u'MR': u'1681895', u'JSTOR': u'421140'}, u'Periodical': u'The Bulletin of Symbolic Logic', u'Authors': [{u'last': u'Solomon', u'first': u'Reed'}], u'Date': u'1999', u'Pages': u'45-58'}
    http://citeseerx.ist.psu.edu/viewdoc/summary?doi=10.1.1.364.9553

    

For each reference, the script outputs:
* a parsed version of the reference, as a python dict
* an URL (or None), where Dissemin thinks a full text is available for this reference.
