# -*- coding: utf-8 -*-

from os import path
from setuptools import setup, find_packages


def read(filename):
    with open(path.join(path.dirname(__file__), filename)) as f:
        return f.read()


install_requires = [
    "autoroutes >= 0.2.0",
    "biscuits >= 0.1.1",
    "httptools >= 0.0.11",
    "multifruits >= 0.1.1",
    "curio >= 0.9",
    "wsproto >= 0.12.0",
    "pytest",
    "http-parser",
    ]

tests_require = [
    
    ]

setup(name='granite',
      version='0.1.dev0',
      description="Curio-based web framework",
      long_description="%s\n\n%s" % (
          read('README.md'), read(path.join('docs', 'HISTORY.txt'))),
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
      entry_points="",
      )
