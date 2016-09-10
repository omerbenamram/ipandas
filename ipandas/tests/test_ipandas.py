# noinspection PyUnresolvedReferences
from .fixtures import *


def test_completes_kw(completer_with_dataframe):
    c = completer_with_dataframe
    text, matches = c.complete('df.groupby(by="')
    assert set(matches) == {'Name', 'FavoriteFood'}

    text, matches = c.complete('df.groupby(')
    assert set(matches) == {'Name', 'FavoriteFood'}


def test_completes_simple_slicing(completer_with_dataframe):
    c = completer_with_dataframe
    text, matches = c.complete('df[[')
    assert set(matches) == {'Name', 'FavoriteFood'}

    # this should not complete anything
    text, matches = c.complete('df[["test"]].')
    assert not matches
