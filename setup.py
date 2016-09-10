from setuptools import setup, find_packages

REQUIRES = ['logbook', 'pytest', 'pandas']


def main():
    setup(name='ipandas',
          packages=find_packages(),
          version='0.1',
          description='Autocompletion for pandas dataframes in IPython notebooks!',
          install_requires=REQUIRES,
          include_package_data=True,
          )


if __name__ == '__main__':
    main()