import re
from typing import List, Union, Callable

import logbook
from IPython import get_ipython
from IPython.core.completer import IPCompleter
from IPython.terminal.interactiveshell import InteractiveShell
from pandas import DataFrame

from ipandas.utils import extract_keyword_args_from_arguments_string

logger = logbook.Logger('IPandasCompleter')

slice_re = re.compile(r'(?P<dataframe>\w+)\[\[[\'\"\w]*\]?\]?$', re.MULTILINE)
# matches s._stats(field_name="a", by="
function_re = re.compile(r'(?P<object>\w+)\.(?P<function>\w+)\((?P<kwargs>.*)$', re.MULTILINE)
# matches field_name="a", by=" and extracts groups
dict_keys_re = re.compile(r'(?P<key>(\'\w*\'*|\"\w*\"*)):(?P<value>(\'\w*\'*|\"\w*\"*)|(\[[@\w,\s\'\"]+]?))?$',
                          re.MULTILINE)

period_followed_by_open_paren = re.compile(r'\.(?=\S+\()', re.MULTILINE)

dict_re = re.compile('{(.+)', re.DOTALL)


def complete_columns(frame: DataFrame, method_name=None, current_value=None, **kwargs) -> List[str]:
    available_columns = list(frame.columns)
    if not current_value:
        return available_columns
    return list(filter(lambda x: x.startswith(current_value), available_columns))


def complete_slice(frame: DataFrame, method_name: str = None, text=None, current_value: str = None, **kwargs) -> List[str]:
    matches = list(re.finditer(r'(\w+)', text))
    # skip match only df
    if matches and len(matches) > 1:
        current_value = matches[-1].groups()[0]
    return complete_columns(frame=frame, method_name=None, current_value=current_value)


def complete_keyword(frame: DataFrame, session: InteractiveShell,
                     frame_object_name: str, text: str, **kwargs) -> List[str]:
    function_name, function_object = get_current_function(session, frame_object_name, text)
    logger.debug('init text: {}'.format(text))
    # find index of last open (
    idx_last_open_paren = text.rfind('(')
    # text begins at idx + 1
    arguments_string = text[idx_last_open_paren + 1:]

    keyword_matches = extract_keyword_args_from_arguments_string(arguments_string, function_object=function_object)

    keyword_to_complete, current_value = keyword_matches[-1]
    logger.debug('Final keyword_name {}, keyword_value {}'.format(keyword_to_complete, current_value))
    completer = get_completer_for_keyword(keyword_name=keyword_to_complete, function_name=function_name)
    if not completer:
        return []
    return completer(frame=frame, method_name=function_name, current_value=current_value)


MATCHERS = {
    function_re: complete_keyword,
    slice_re: complete_slice
}

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
        # 3 df = df.groupby(param_1='...', param_2={'arg1': 'test',
        # 4                                         'arg2': '....'}
        # trying to complete anything on line 4, we will get only the forth line and not the entire on the cell content
        # so we can steal the entire cell content from the notebook API
        try:
            cursor_position = self.shell.parent_header['content']['cursor_pos']
            text_until_cursor = self.shell.parent_header['content']['code'][:cursor_position]
        except AttributeError:
            # if we are running in a shell, always hook to default API
            text_until_cursor = self.text_until_cursor

    for matcher, callback in MATCHERS.items():
        text_match = matcher.search(text_until_cursor)
        if text_match:
            frame_object_name, *_ = text_match.groups()
            dataframe_object = ip._ofind(frame_object_name).get('obj')
            if not isinstance(dataframe_object, DataFrame):
                return []
            return callback(frame=dataframe_object, session=ip, text=text_until_cursor,
                            frame_object_name=frame_object_name)
    return []


def get_completer_for_keyword(keyword_name, function_name) -> Union[Callable[..., List[str]], None]:
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


def get_current_function(ip: InteractiveShell, query_object_name, text_until_cursor):
    function_names = period_followed_by_open_paren.split(text_until_cursor)
    function_name = function_names[-1].split('(')[0]
    # then we find function object (ex. search._stats)
    function_object = ip._ofind('{}.{}'.format(query_object_name, function_name)).get('obj')
    return function_name, function_object
