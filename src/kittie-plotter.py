#!/usr/bin/env python

from __future__ import absolute_import, division, print_function, unicode_literals
import yaml
import kittie
import adios2
import numpy as np
import argparse
import os
from mpi4py import MPI

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


class PlotHelper(object):

    def __init__(self, name, config):

        self.name = name
        for arg in ['filename', 'y']:
            if arg not in config:
                raise ValueError("{0}: {1} must be given to make a plot".format(self.name, arg))
            exec("self.{0} = config[arg]".format(arg))

        for name, val in [('engine', 'BPFile'), ('x', None)]:
            if name not in config:
                value = val
            else:
                value = config[name]
            if type(value) is str:
                value = "'{0}'".format(value)
            string = "self.{0} = {1}".format(name, value)
            exec(string)

        self.step = 0
        kittie.Group(self.name, engine=self.engine)
        self.helper = kittie.Coupler(groupname=self.name)


    def Plot(self, fs=20):
        print(self.name, self.step)

        variables = self.helper.io.AvailableVariables()
        shape = variables[self.y]['Shape']
        shape = shape.strip().split(',')
        for i in range(len(shape)):
            shape[i] = int(shape[i])
        starts = np.zeros(len(shape), dtype=np.int64)

        data = {'y': np.empty(tuple(shape), dtype=np.float64)}
        self.helper.GetSelection(data['y'], self.y, starts, shape)
        if self.x is not None:
            data['x'] = np.empty(tuple(shape), dtype=np.float64)
            self.helper.GetSelection(data['x'], self.x, starts, shape)
        self.helper.EndStep()

        matplotlib.rcParams['axes.unicode_minus'] = False
        gs = gridspec.GridSpec(1, 1)
        fig = plt.figure(figsize=(6,6))
        ax = fig.add_subplot(gs[0, 0])
        ax.plot(data['x'], data['y'])
        ax.set_title(self.name, fontsize=fs)
        ax.set_ylabel(self.y.replace('_', '-'), fontsize=fs)
        if self.x is not None:
            ax.set_xlabel(self.x.replace('_', '-'), fontsize=fs)
        else:
            ax.set_xlabel('index')

        fig.savefig(os.path.join("images", "{0}-{1}.png".format(self.name, self.step)), bbox_inches="tight")




if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    helpers = []
    comm = MPI.COMM_WORLD

    with open("kittie-plots.yaml", 'r') as ystream:
        config = yaml.load(ystream)

    if "mpmd" in config:
        rank = comm.Get_rank()
        comm = comm.Split(config["mpmd"], rank)
        del config["mpmd"]

    kittie.Initialize(comm=comm)
    for i, name in enumerate(config.keys()):
        helpers += [PlotHelper(name, config[name])]

    if not os.path.lexists("images"):
        os.makedirs("images")

    done = np.zeros(len(helpers), dtype=np.int)
    while True:

        if np.sum(done) == len(done):
            break

        for i in range(len(helpers)):

            if (done[i] == 1) or (not os.path.lexists(helpers[i].filename)):
                continue

            found = helpers[i].helper.BeginStep(filename=helpers[i].filename, groupname=helpers[i].helper.groupname, mode=adios2.Mode.Read, comm=comm, step=helpers[i].step, timeout=0.0)

            if found:
                helpers[i].Plot()
                helpers[i].step += 1
            else:
                fname = "{0}.done".format(helpers[i].filename)
                if os.path.lexists(fname):
                    done[i] = 1

