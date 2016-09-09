import inspect
import re
import types
import typing
from inspect import Signature, Parameter
from typing import List, Callable, Union

import logbook
from IPython import get_ipython
from IPython.core.completer import IPCompleter
from IPython.terminal.interactiveshell import InteractiveShell
from pandas import DataFrame

logger = logbook.Logger('IPandasCompleter')

# global we use to restore ipython state if unloading our extension
original_merge_completions = None

slice_re = re.compile(r'(?P<dataframe>\w+)\[\[[\'\"\w]*\]?\]?$', re.MULTILINE)
# matches s._stats(field_name="a", by="
function_re = re.compile(r'(?P<object>\w+)\.(?P<function>\w+)\((?P<kwargs>.*)$', re.MULTILINE)
# matches field_name="a", by=" and extracts groups
kwargs_re = re.compile('''
                       (?P<identifier>\w+)=
                       (?P<kw>(\'\w*\'*|\"\w*\"*) # Option 1 - Keyword is a simple token
                       |([\[{(]                   # Option 2 - Keyword is a list/dict
                       [{@\w:,\s\'\"]+
                       [}\])]?                    # Closing is optional
                       ))?$                       # The whole group is optional
                       ''', re.VERBOSE | re.MULTILINE)
dict_keys_re = re.compile(r'(?P<key>(\'\w*\'*|\"\w*\"*)):(?P<value>(\'\w*\'*|\"\w*\"*)|(\[[@\w,\s\'\"]+]?))?$',
                          re.MULTILINE)
commas_not_preceded_by_brackets = re.compile(r'(?<=[\]})])\s*,', re.MULTILINE)
comma_followed_by_brackets = re.compile(r',(?=\s*[\[{(])\s*', re.MULTILINE)

period_followed_by_open_paren = re.compile(r'\.(?=\S+\()', re.MULTILINE)

dict_re = re.compile('{(.+)', re.DOTALL)


class KeywordMatch(typing.NamedTuple('KeywordMatch', [('current_keyword', str), ('current_value', str)])):
    pass


def complete_columns(frame: DataFrame, method_name=None, current_value=None) -> List[str]:
    available_columns = list(frame.columns)
    if not current_value:
        return available_columns
    return list(filter(lambda x: x.startswith(current_value), available_columns))


# {'keyword':
#    {'function_name' (* = default): function}
# }
KEYWORDS_TO_COMPLETION_FUNCTION = {
    'by': {
        'groupby': complete_columns
    },
    'subset': {
        'drop_duplicates': complete_columns
    }
}


def complete_slice(frame: DataFrame, method_name: str = None, current_value: str = None) -> List[str]:
    return complete_columns(frame=frame, method_name=None)


# We are not going to use IPython regular completer hook (ip.set_hook('complete_command')) since
# it only accepts a string key or regex for command completion.
# we are going to instead insert a custom matcher, inspect the query object
# and offer completions based on internal state.
# noinspection PyProtectedMember
def ipandas_completer(self: IPCompleter, event) -> List[str]:
    """
    Main completer for moose queries. Handles bucket and field completion for query object.
    Currently only completes keyword args
    :param self: IPython completer state
    :param event: This is dispatched to the InteractiveSession and to hooks, we do not use this.
    :return: list of matches
    """
    # we will need InteractiveShell instance to fetch query object from python namespace
    ip = get_ipython()
    text_until_cursor = self.text_until_cursor
    if text_until_cursor.startswith('  '):
        # 1 If we are running on notebook, text_until_cursor hook will fail for multiline inputs
        # 2 for example, if we have the text:
        # 3 s = s.where(by='...', parameters_mapping={'arg1': 'test',
        # 4                                           'arg2': '....'}
        # trying to complete anything on line 4, we will get only the forth line and not the entire on the cell content
        # so we can steal the entire cell content from the notebook API
        try:
            cursor_position = self.shell.parent_header['content']['cursor_pos']
            text_until_cursor = self.shell.parent_header['content']['code'][:cursor_position]
        except AttributeError:
            # if we are running in a shell, always hook to default API
            text_until_cursor = self.text_until_cursor

    # we first need to find our object name from event line
    function_string_match = function_re.search(text_until_cursor)
    slice_re_match = slice_re.search(text_until_cursor)

    if function_string_match:
        # we are not using some of these capturing groups anymore..
        query_object_name, *_ = function_string_match.groups()
        dataframe_object = ip._ofind(query_object_name).get('obj')
        if not isinstance(dataframe_object, DataFrame):
            return []
        logger.debug('Completing Keyword')
        return complete_keyword(dataframe_object, ip, query_object_name, text_until_cursor)

    elif slice_re_match:
        query_object_name, *_ = slice_re_match.groups()
        dataframe_object = ip._ofind(query_object_name).get('obj')
        if not isinstance(dataframe_object, DataFrame):
            return []
        logger.debug('Completing Slicing')
        return complete_slice(frame=dataframe_object)


def complete_keyword(frame: DataFrame, ip: InteractiveShell,
                     frame_object_name: str, text_until_cursor: str) -> List[str]:
    function_name, function_object = get_current_function(ip, frame_object_name, text_until_cursor)
    logger.debug('init text: {}'.format(text_until_cursor))
    # find index of last open (
    idx_last_open_paren = text_until_cursor.rfind('(')
    # text begins at idx + 1
    arguments_string = text_until_cursor[idx_last_open_paren + 1:]

    # regex failed, infer information from function signature
    if not kw_matches:
        # this function will NOT handle a string with keyword args!
        keyword_to_complete, current_value = infer_current_keyword_from_arguments_string(arguments_string,
                                                                                         function_object)
    # Extract from regex.
    else:
        current_value, keyword_to_complete = extract_keyword_args_from_arguments_string(kw_matches)

    keyword_name, keyword_value = keyword_to_complete
    logger.debug('Final keyword_name {}, keyword_value {}'.format(keyword_name, keyword_value))
    completer = get_completer_for_keyword(keyword_name=keyword_name, function_name=function_name)
    return completer(frame=frame, method_name=function_name, current_value=current_value)


def extract_keyword_args_from_arguments_string(arguments_string: str) -> Union[KeywordMatch, None]:
    kw_matches = list(kwargs_re.finditer(arguments_string))
    if not kw_matches:
        return None

    logger.debug('text to kwargs regex: {}'.format(arguments_string))
    kw_dict = kw_matches[-1].groupdict()
    current_param, current_value = kw_dict['identifier'], kw_dict['kw']
    logger.debug('kwargs regex matched: {}'.format((current_param, current_value)))
    current_value = _extract_last_value_from_string_argument(current_value)
    keyword_to_complete = (current_param, current_value)
    logger.debug('text after cleanup: {}'.format(keyword_to_complete))
    return KeywordMatch(keyword_to_complete, current_value)


def get_completer_for_keyword(keyword_name, function_name):
    completion_func_or_dict = KEYWORDS_TO_COMPLETION_FUNCTION.get(keyword_name)
    # We can have a mapping from method name to func, with default being *
    if isinstance(completion_func_or_dict, dict):
        func = completion_func_or_dict.get(function_name)
        if not func:
            func = completion_func_or_dict.get('*')
    elif completion_func_or_dict is None:
        return []
    else:
        func = completion_func_or_dict
    return func


def infer_current_keyword_from_arguments_string(arguments_string_until_current_value: str,
                                                function_object: Callable) -> KeywordMatch:
    """
    This function gets a string representing the arguments we have so far,
    and returns a tuple of the current keyword and the current value being completed.

    :param arguments_string_until_current_value: Whats inside the parenthesis ()
    :param function_object: the function object we are that will be used for introspection
    :return:
    """
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

    # Fix "off by 1" between zero based len and 1 based position.
    param_position = len(arguments) - 1
    current_param = params[param_position]  # type: Parameter
    # If we have a partial list as current value. ignore everything until last comma.
    current_value = _extract_last_value_from_string_argument(arguments[-1])
    logger.debug('Inferred Param: {}, Inferred Value: {}'.format(current_param.name, current_value))
    keyword_to_complete = (current_param.name, current_value)
    return KeywordMatch(keyword_to_complete, current_value)


def get_current_function(ip: InteractiveShell, query_object_name, text_until_cursor):
    function_names = period_followed_by_open_paren.split(text_until_cursor)
    function_name = function_names[-1].split('(')[0]
    # then we find function object (ex. search._stats)
    function_object = ip._ofind('{}.{}'.format(query_object_name, function_name)).get('obj')
    return function_name, function_object


def _extract_last_value_from_string_argument(argument_string: str):
    """
    Internal function for argument string cleanup.
    :param argument_string: A string representing an argument to a function. can be a list/tuple/set or a simple string.
    :return: A clean string (no brackets, quotation marks) of the last value in list argument or simple the argument itself.
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


def load_ipython_extension(ip: InteractiveShell):
    """
    Creates a method for our matcher and loads it into IPythons completer.
    :param ip: IPython session (this is supplied to us when calling the %load_ext magic)
    :return: None
    """
    global original_merge_completions
    print('IPandas IPython Extension is loaded')

    # create a custom matcher object
    # types.MethodType will add it as a method to the CURRENT ipython completer object!
    ip.Completer.ipandas_matcher = types.MethodType(ipandas_completer, ip.Completer)
    # insert it into ipython matchers list
    ip.Completer.matchers.insert(0, ip.Completer.ipandas_matcher)

    # don't accept matches from IPythons other matchers when our matcher can offer completion
    # save original value as global for restoration later
    original_merge_completions = ip.Completer.merge_completions
    ip.Completer.merge_completions = False


def unload_ipython_extension(ip: InteractiveShell):
    """
    Unloads moose logic and restore original IPython state.
    :param ip: IPython session (this is supplied to us when calling the %load_ext magic)
    :return: None
    """
    ip.Completer.matchers.remove(ip.Completer.moose_matches)
    ip.Completer.merge_completions = original_merge_completions
