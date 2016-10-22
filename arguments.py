# -*- encoding: utf-8 -*-

from __future__ import unicode_literals
import re

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
        if custom_access and type(custom_access) == bool:
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


