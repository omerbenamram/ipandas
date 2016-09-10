import types

from IPython import InteractiveShell

from ipandas.ipandas import ipandas_completer

# global we use to restore ipython state if unloading our extension
original_merge_completions = None


def load_ipython_extension(ip: InteractiveShell) -> None:
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


def unload_ipython_extension(ip: InteractiveShell) -> None:
    """
    Unloads moose logic and restore original IPython state.
    :param ip: IPython session (this is supplied to us when calling the %load_ext magic)
    :return: None
    """
    ip.Completer.matchers.remove(ip.Completer.moose_matches)
    ip.Completer.merge_completions = original_merge_completions
