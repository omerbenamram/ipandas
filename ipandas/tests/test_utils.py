from ipandas.utils import extract_keyword_args_from_arguments_string, KeywordMatch, _extract_argument_from_string


def f(a, b, c=None):
    pass


def test_parses_argument_correctly():
    argument = '["a","b","c"]'
    assert _extract_argument_from_string(argument) == (['a', 'b', 'c'], True)


def test_extracts_params_correctly():
    arguments = extract_keyword_args_from_arguments_string('a="1", b=2, c=3', f)
    assert arguments == [KeywordMatch('a', '1'), KeywordMatch('b', 2), KeywordMatch('c', 3)]

    arguments = extract_keyword_args_from_arguments_string('a="1", b=["a","b","c"], c=["a", "', f)
    assert arguments == [KeywordMatch('a', '1')]
