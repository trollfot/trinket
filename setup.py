from os import path
from setuptools import setup, find_packages


def read(filename):
    with open(path.join(path.dirname(__file__), filename)) as f:
        return f.read()


install_requires = [
    "autoroutes == 0.2.1",
    "biscuits == 0.2.1",
    "httptools == 0.0.13",
    "multifruits == 0.1.4",
    "curio == 0.9",
    "wsproto == 0.15.0"
    ]

tests_require = [
    "pytest == 5.3.2",
    ]

setup(name='trinket',
      version='0.1.5',
      description="Curio-based web framework",
      long_description="%s\n\n%s" % (
          read('README.rst'), read(path.join('docs', 'HISTORY.rst'))),
      keywords="Curio HTTP",
      author="",
      author_email="",
      license="BSD",
      packages=find_packages('src', exclude=['ez_setup']),
      package_dir={'': 'src'},
      include_package_data=True,
      zip_safe=False,
      install_requires=install_requires,
      extras_require={'test': tests_require},
      entry_points={
          'pytest11': ['trinket=trinket.testing'],
      }
      )
