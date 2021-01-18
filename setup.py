#!/usr/bin/env python
from os import path as op
from setuptools import setup


def _read(fname):
    return open(op.join(op.dirname(__file__), fname)).read()


setup(
    install_requires=[
        line for line in _read('requirements.txt').split('\n')
        if line and not line.startswith('#')
    ],
)
