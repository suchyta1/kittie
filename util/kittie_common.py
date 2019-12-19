#!/usr/bin/env python

# Let's keep everything tested with python 2 and python 3
from __future__ import absolute_import, division, print_function, unicode_literals

import os


def Namelist(*args):
    groups = []
    for arg in args:
        groups += ["&{0}{2}{1}{2}/\n".format(arg[0], arg[1], '\n\n')]
    outstr = "\n".join(groups)
    return outstr


def NMLFile(name, mainpath, outstr, codename=None, appname=None, launchmode=None):
    if launchmode == "default":
        outdir = os.path.join(mainpath, codename)
    else:
        outdir = mainpath

    if appname is None:
        outname = os.path.join(outdir, ".{0}.nml".format(name))
    else:
        outname = os.path.join(outdir, ".{0}-{1}.nml".format(name, appname))
    with open(outname, 'w') as out:
        out.write(outstr)

