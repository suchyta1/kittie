#!/usr/bin/env python

from __future__ import absolute_import, division, print_function, unicode_literals

import adios2
import argparse
import os
import sys
import numpy as np
import plot_util

# I'm going to require MPI with this, it's more or less required to do anything else real
from mpi4py import MPI

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.tri as tri
from matplotlib.ticker import FormatStrFormatter


def Plot(data, outdir, fs=20, xname="x", yname="y", cmap="bwr", minmax=False):

    for name in data.keys():
        if name in ['_StepPhysical', '_StepNumber', 'minmax']:
            continue

        print(name, data['_StepNumber'], data['_StepPhysical']); sys.stdout.flush()

        gs = gridspec.GridSpec(1, 1)
        fig = plt.figure(figsize=(7,6))
        ax = fig.add_subplot(gs[0, 0])

        kwargs = {}
        kwargs['cmap'] = plt.get_cmap(cmap)
        kwargs['origin'] = "lower"
        if minmax:
            opt = np.amax(np.fabs([data['minmax'][name]['min'], data['minmax'][name]['max']])) + 1e-20
            kwargs['vmin'] = -opt
            kwargs['vmax'] = opt

        ColorAxis = ax.imshow(data[name].squeeze(), **kwargs)
        ColorBar = fig.colorbar(ColorAxis, ax=ax, format="%+.2e")
        ColorBar.set_label(name, fontsize=fs)
        if minmax:
            ticks = np.linspace(-opt, opt, 7)
            ColorBar.set_ticks(ticks)

        ax.set_xlabel(xname, fontsize=fs)
        ax.set_ylabel(yname, fontsize=fs)
        ax.set_title("{1},  time = {0:.1e}".format(data['_StepPhysical'][0], name),  fontsize=fs)

        fig.savefig(os.path.join(outdir, "{0}_vs_{2}_{3}-{1}.svg".format(name.replace('/', '|'), data['_StepNumber'][0], xname, yname)), bbox_inches="tight")
        plt.close(fig)



def ParseArgs():
    # Args are maybe just better in the dictionary
    parser = argparse.ArgumentParser()
    parser.add_argument("gridvar", help="One grid variable to match to")
    parser.add_argument("-o", "--only",     help="Only plot the given y-values", type=str, default=[])
    parser.add_argument("-e", "--exclude",  help="Don't plot the given y-values", type=str, default=[])
    parser.add_argument("-c", "--colormap", help="Colormap to use", type=str, default="bwr")
    args = parser.parse_args()

    if len(args.only) > 0:
        args.only = args.only.split(',')
    if len(args.exclude) > 0:
        args.exclude = args.exclude.split(',')

    return args


if __name__ == "__main__":
    matplotlib.rcParams['axes.unicode_minus'] = False
    args = ParseArgs()
    comm = MPI.COMM_WORLD

    #@effis-init comm=comm
    adios = adios2.ADIOS(comm)
    plotter = plot_util.KittiePlotter(comm)
    plotter.ConnectToStepInfo(adios, group="plotter")
    plotter.GetMatchingSelections(adios, args.gridvar, exclude=args.exclude, only=args.only, xomit=False, allx=False)


    if plotter.Active:

        while plotter.NotDone:

            if plotter.DoPlot:
                plotter.GetPlotData()
                Plot(plotter.data, plotter.outdir, xname="x", yname="y", cmap=args.colormap, minmax=False)
                plotter.StepDone()

    #@effis-finalize

