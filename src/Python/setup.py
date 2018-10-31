#!/usr/bin/env python

# Let's keep everything tested with python 2 and python 3
from __future__ import absolute_import, division, print_function, unicode_literals

from setuptools import setup


if __name__ == "__main__":

    #package_data={'suchyta_utils':['suchyta_utils.mplstyle']},
    #scripts=['bin/.screenrc-nest_inner','bin/.screenrc-nest_outer','bin/screen-split','bin/screen-retach','bin/screen-detach','bin/catpdfs'],
    #scripts=binfiles,
    setup(
        name="kittie",
        version="0.1",
        description="WDM coupling framework",
        license = "GPL",
        packages=['kittie'],
        author="Eric Suchyta",
        author_email="eric.d.suchyta@gmail.com"
    )

