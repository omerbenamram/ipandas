import ast
import inspect
import re
from collections import namedtuple
from inspect import Signature
from typing import NamedTuple, List, Callable

import logbook

logger = logbook.Logger('IPandasCompleter')

kwargs_re = re.compile('''
                       (?P<identifier>\w+)=
                       (?P<kw>(?:'\w*'*|\"\w*\"*)         # Option 1 - Keyword is string
                       |(?P<num>[\d\.]+)                  # Option 2 - Keyword is number (capture it)
                       |(?:[\[{(]                         # Option 2 - Keyword is a list/dict
                       [{@\w:,\s\'\"]+                    # contents of list
                       [}\])]?$                           # Closing is optional - as it might not be provided
                       ))?                                # The whole group is optional
                       ''', re.VERBOSE | re.MULTILINE)
commas_not_preceded_by_brackets = re.compile(r'(?<=[\]})])\s*,', re.MULTILINE)
comma_followed_by_brackets = re.compile(r',(?=\s*[\[{(])\s*', re.MULTILINE)


class KeywordMatch(NamedTuple('KeywordMatch', [('keyword', str), ('is_complete', str)])):
    pass


class ArgumentResult(namedtuple('ArgumentResult',
                                ['argument', 'is_complete', 'is_collection', 'current_value'])):
    pass


def has_open_quotes(s):
    # We check " first, then ', so complex cases with nested quotes will get
    # the " to take precedence.
    if s.count('"') % 2:
        return '"'
    elif s.count("'") % 2:
        return "'"
    else:
        return False


# TODO: this doesn't consider brackets inside strings at all
def has_open_bracket(string):
    if string.count('[') == string.count(']'):
        return False
    return True


# TODO: this is not finished..
def has_open_dict(string):
    if string.count('{') == string.count('}'):
        return False
    else:
        comma_followed_by_brackets = re.compile(r',(?=\s*[\[{(])\s*', re.MULTILINE)


def _extract_argument_from_string(argument_string: str) -> ArgumentResult:
    argument_is_complete = False
    if not argument_string:
        argument_is_complete = True
        return ArgumentResult(None, argument_is_complete, is_collection=False, current_value=None)

    argument_string = argument_string.strip('"').strip("'").strip()
    first_char = argument_string[0]
    arguments = None
    if first_char == '[':
        argument_is_complete = not has_open_bracket(argument_string)
        if argument_is_complete:
            return ArgumentResult(ast.literal_eval(argument_string),
                                  is_complete=argument_is_complete,
                                  is_collection=True,
                                  current_value=None)
        open_quote = has_open_quotes(argument_string)
        last_in_collection = None
        if open_quote:
            last_in_collection = argument_string[argument_string.rfind(open_quote):].strip(open_quote)

        while has_open_quotes(argument_string):
            open_quote = has_open_quotes(argument_string)
            argument_string += open_quote

        while has_open_bracket(argument_string):
            argument_string += ']'

        # we don't return the last value as part of the collection
        if last_in_collection:
            ret = ast.literal_eval(argument_string)[:-1]
        else:
            ret = ast.literal_eval(argument_string)

        return ArgumentResult(ret,
                              is_complete=argument_is_complete,
                              is_collection=True,
                              current_value=last_in_collection)


def _extract_last_value_from_string_argument(argument_string: str) -> str:
    """
    Internal function for argument string cleanup.

    Parameters
    ----------
    argument_string
        A string representing an argument to a function.
        Can be a string containing a list/tuple/set.

    Returns
    -------
    last_argument - string
        A clean string (no brackets, quotation marks) of the last value in iterable argument or the argument.
    """

    # we can't have trailing spaces because we will not receive them from IPython
    # (since it always gives us string util tab)
    def _remove_unwanted_chars(string):
        if not string:
            return ''

        for i, char in enumerate(string):
            if char in r'\'\"[]()':
                continue
            else:
                return string[i:]
        return string

    if argument_string is None:
        return ''

    argument_string = argument_string.strip('"').strip("'").strip()

    # we accept string which represent a list/tuple/set argument
    if argument_string and argument_string[0] in ['[', '(']:
        # if only a bracket - there is no value
        if len(argument_string) == 1:
            return ''

        # we want the last value from the list
        return _remove_unwanted_chars(argument_string.split(',')[-1].strip())
    return _remove_unwanted_chars(argument_string)


def extract_keyword_args_from_arguments_string(arguments_string_until_current_value: str,
                                               function_object: Callable = None) -> List[KeywordMatch]:
    """
    This function gets a string representing the arguments we have so far,
    and returns a tuple of the current keyword and the current value being completed.

    Parameters
    ----------

    arguments_string_until_current_value: str
       Whats inside the parenthesis ()

    function_object: Callable, Optional
        the function object we are that will be used for introspection
        if not provided will skip introspection and fail

    Returns
    -------
     list of KeywordMatch
    """
    logger.debug('text to kwargs regex: {}'.format(arguments_string_until_current_value))
    kw_matches = list(kwargs_re.finditer(arguments_string_until_current_value))
    if kw_matches:
        logger.debug(kw_matches)
        matches = list()
        for match in kw_matches:
            d = match.groupdict()
            param, value = d['identifier'], d['kw']
            numerical_match = d.get('num')
            if numerical_match:
                value = coerce_to_number(value)
            matches.append((param, value))

    elif function_object:
        logger.debug('kwargs regex failed, inferring parameters from function signature')
        # extract keyword_name from signature
        sig = inspect.signature(function_object)  # type: Signature
        params = list(sig.parameters.values())
        # we need to cover all the following cases
        # field = ['a', 'b'], ['b', 'c', 'd', # bracket preceding comma
        # field = ['b', 'c', 'd'], 'a', # bracket preceding comma
        # field = 'a', ['b', 'c', 'd', # bracket following comma
        # field = ['a', ' # single list argument
        # field = 'a', 'b' # no list arguments, split by ,
        if commas_not_preceded_by_brackets.findall(arguments_string_until_current_value):
            arguments = commas_not_preceded_by_brackets.split(arguments_string_until_current_value)
        elif comma_followed_by_brackets.findall(arguments_string_until_current_value):
            arguments = comma_followed_by_brackets.split(arguments_string_until_current_value)
        elif any([x in arguments_string_until_current_value for x in '[{(']):
            arguments = [arguments_string_until_current_value]
        else:
            arguments = arguments_string_until_current_value.split(',')

        matches = zip(map(lambda p: p.name, params), arguments)

    else:
        return []

    keywords = list()
    for match in matches:
        logger.debug(match)
        # this will handle the case where the argument is list-like
        current_param, current_value = match
        if isinstance(current_value, str):
            current_value = _extract_last_value_from_string_argument(current_value)

        logger.debug('{}: {}'.format(current_param, current_value))
        keywords.append(KeywordMatch(current_param, current_value))

    return keywords


def coerce_to_number(s):
    try:
        s = int(s)
    except ValueError:
        try:
            s = float(s)
        except ValueError:
            pass
    return s
