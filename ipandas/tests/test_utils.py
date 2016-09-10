import pytest

from ipandas.utils import extract_keyword_args_from_arguments_string, KeywordMatch, _extract_argument_from_string, \
    ArgumentResult


def f(a, b, c=None):
    pass


def test_parses_argument_correctly():
    argument = '["a","b","c"]'
    assert _extract_argument_from_string(argument) == ArgumentResult(['a', 'b', 'c'], is_complete=True,
                                                                     is_collection=True, current_value=None)

    argument = '["a","b","c'
    assert _extract_argument_from_string(argument) == ArgumentResult(['a', 'b'], is_complete=False,
                                                                     is_collection=True, current_value="c")

    argument = '["a","b",["c'
    assert _extract_argument_from_string(argument) == ArgumentResult(['a', 'b'], is_complete=False,
                                                                     is_collection=True, current_value="c")
    argument = '["a","b",["c", "d"],["e'
    assert _extract_argument_from_string(argument) == ArgumentResult(['a', 'b', ["c", "d"]], is_complete=False,
                                                                     is_collection=True, current_value="e")
    argument = '["a","b",["c", "d"],'
    assert _extract_argument_from_string(argument) == ArgumentResult(['a', 'b', ["c", "d"]], is_complete=False,
                                                                     is_collection=True, current_value=None)
    argument = '["a","b",["c", 1],'
    assert _extract_argument_from_string(argument) == ArgumentResult(['a', 'b', ["c", 1]], is_complete=False,
                                                                     is_collection=True, current_value=None)
    argument = '["a","b",["c]", 1],'
    assert _extract_argument_from_string(argument) == ArgumentResult(['a', 'b', ["c", 1]], is_complete=False,
                                                                     is_collection=True, current_value=None)

@pytest.mark.xfail
def test_parses_correctly_with_dict():
    argument = '["a","b",{"k": "v'
    assert _extract_argument_from_string(argument) == ArgumentResult(['a', 'b'], is_complete=False,
                                                                     is_collection=True, current_value="v")


def test_extracts_params_correctly():
    arguments = extract_keyword_args_from_arguments_string('a="1", b=2, c=3', f)
    assert arguments == [KeywordMatch('a', '1'), KeywordMatch('b', 2), KeywordMatch('c', 3)]

    arguments = extract_keyword_args_from_arguments_string('"1", ["a","b","c"], ["a", "', f)
    assert arguments == [KeywordMatch('a', '1')]
