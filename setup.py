# -*- coding: utf-8 -*-

from os import path
from setuptools import setup, find_packages


def read(filename):
    with open(path.join(path.dirname(__file__), filename)) as f:
        return f.read()


install_requires = read('requirements.txt').split('\n')

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
