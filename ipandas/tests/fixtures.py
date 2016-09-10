import pytest
from IPython import get_ipython, InteractiveShell
from IPython.testing.globalipapp import start_ipython

import ipandas


@pytest.fixture
def ipython_with_ipandas_ext(capsys):
    # this is required for IPython to work properly
    with capsys.disabled():
        start_ipython()
    ip = get_ipython()
    ipandas.load_ipython_extension(ip)
    return ip


@pytest.fixture
def completer_with_dataframe(ipython_with_ipandas_ext: InteractiveShell):
    ip = ipython_with_ipandas_ext
    ip.ex('import pandas as pd')
    ip.ex("""df = pd.DataFrame([
          ('Omer', 'Sushi'),
          ('Ohad', 'Pizza'),
          ('Ofir', 'Hamburger')
    ], columns = ['Name', 'FavoriteFood'])
    """)
    return ip.Completer
