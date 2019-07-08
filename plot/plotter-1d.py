#!/usr/bin/env python

from __future__ import absolute_import, division, print_function, unicode_literals

import adios2
import argparse
import os
import sys
import plot_util

# I'm going to require MPI with this, it's more or less required to do anything else real
from mpi4py import MPI

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


def Plot(data, xname, outdir, fs=20):

    for name in data.keys():
        if name in ['_StepPhysical', '_StepNumber', xname, 'minmax']:
            continue

        print(xname, name, data['_StepNumber'], data['_StepPhysical']); sys.stdout.flush()

        gs = gridspec.GridSpec(1, 1)
        fig = plt.figure(figsize=(7,6))
        ax = fig.add_subplot(gs[0, 0])

        ax.plot(data[xname], data[name])
        ax.set_xlabel(xname, fontsize=fs)
        ax.set_ylabel(name,  fontsize=fs)
        ax.set_title("{1},  time = {0:.1e}".format(data['_StepPhysical'][0], name),  fontsize=fs)

        fig.savefig(os.path.join(outdir, "{0}_vs_{1}-{2}.svg".format(name, xname, data['_StepNumber'][0])), bbox_inches="tight")
        plt.close(fig)


def ParseArgs():
    # Args are maybe just better in the dictionary
    parser = argparse.ArgumentParser()
    parser.add_argument("xaxis", help="What to use as x-axis for plotting")
    parser.add_argument("-o", "--only",     help="Only plot the given y-values", type=str, default=[])
    parser.add_argument("-e", "--exclude", help="Don't plot the given y-values", type=str, default=[])
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
    plotter.GetMatchingSelections(adios, args.xaxis, exclude=args.exclude, only=args.only, xomit=True)

    if plotter.Active:

        while plotter.NotDone:

            if plotter.DoPlot:
                plotter.GetPlotData()
                Plot(plotter.data, plotter.DimInfo['xname'], plotter.outdir)
                plotter.StepDone()

    #@effis-finalize

