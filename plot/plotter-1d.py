#!/usr/bin/env python

from __future__ import absolute_import, division, print_function, unicode_literals

import yaml
import kittie
import adios2
import numpy as np
import argparse
import os
import re
import sys
import time

# I'm going to require MPI with this, it's more or less required to do anything else real
from mpi4py import MPI

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


def SplitOn(txt, splitkey):
    outarr = []
    for entry in txt.split(splitkey):
        entry = entry.strip()
        if entry == "":
            continue
        outarr += [entry]
    return outarr


def xParse(xname):
    if xname.endswith(']'):
        start = xname.find('[')
        xname = xname[:start]
        xdims = xname[start+1, -1]
        xdims = xdims.split(',')
        for i in range(xdims):
            xdims[i] = xdims[i].strip()
    else:
        xdims = None
    return xname, xdims


def GetType(varid, name):
    size = varid.Sizeof()
    kind = varid.Type()

    # I'm just handling the common ones for now
    if kind.find('int') != -1:
        if size == 8:
            UserType = np.int64
        elif size == 4:
            UserType = np.int32
        elif size == 2:
            UserType = np.int16
    elif kind.find('double') != -1:
        UserType = np.float64
    elif (kind.find('float') != -1) or (kind.find('single') != -1):
        UserType = np.float32

    return UserType




def GetMatching(io, xname, comm, exclude=[], only=[]):
    vx = io.InquireVariable(xname)
    shape = vx.Shape()
    if len(shape) == 0:
        raise ValueError("Using this with a scalar for the x-axis doesn't makes sense")
    xType = GetType(vx, xname)

    variables = io.AvailableVariables()
    if len(only) == 0:
        only = variables.keys()
    if xname not in only:
        only += [xname]

    size = comm.Get_size()
    UserMatches = []
    UserTypes = []
    index = 0
    for i in range(size):
        UserMatches += [[]]
        UserTypes += [[]]

    for name in only:
        if (name in exclude) or (name == xname):
            continue

        varid = io.InquireVariable(name)
        TestShape = varid.Shape()
        if shape == TestShape:
            i = index % size
            UserMatches[i] += [name]
            dtype = GetType(varid, name)
            UserTypes[i] += [dtype]
            index += 1

    return shape, UserMatches, UserTypes, xType


def GetSelections(io, xaxis, comm, exclude=[], only=[]):
    DimInfo = {}

    # Get the name and slice
    DimInfo['xname'], xsel = xParse(xaxis)

    # Get the full shape and other variables that match it
    xShape, DimInfo['UserMatches'], DimInfo['UserTypes'], DimInfo['xType'] = GetMatching(io, DimInfo['xname'], comm, exclude=exclude, only=only)

    # Get ADIOS selections
    counts = np.array(xShape, dtype=np.int64)
    starts = np.zeros(counts.shape[0], dtype=np.int64)
    if xsel is not None:
        for j, dim in enumerate(xShape):
            if (j >= len(xsel)) or (xsel[j] == ":"):
                continue
            else:
                if xsel.find(":") != -1:
                    start, stop = xsel.split(":")
                    starts[j] = int(start.strip())
                    counts[j] = int( stop.strip()) - start[j]
                else:
                    starts[j] = int(xsel[j])

    DimInfo['starts'] = list(starts)
    DimInfo['counts'] = list(counts)
    return DimInfo


def Plot(data, xname, outdir, fs=20):

    for name in data.keys():
        if name in ['_StepPhysical', '_StepNumber', xname]:
            continue

        print(xname, name, data['_StepNumber'], data['_StepPhysical']); sys.stdout.flush()

        gs = gridspec.GridSpec(1, 1)
        fig = plt.figure(figsize=(7,6))
        ax = fig.add_subplot(gs[0, 0])

        ax.plot(data[xname], data[name])
        ax.set_xlabel(xname, fontsize=fs)
        ax.set_ylabel(name,  fontsize=fs)
        ax.set_title("time = {0:.3e}".format(data['_StepPhysical'][0]),  fontsize=fs)

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


def FindDims(adios):
    filename = None
    #@effis-begin filename->"plotter"
    io = adios.DeclareIO(filename)
    engine = io.Open(filename, adios2.Mode.Read, MPI.COMM_SELF)
    DimInfo = GetSelections(io, args.xaxis, comm, exclude=args.exclude, only=args.only)
    engine.Close()
    io.RemoveAllVariables()
    io.RemoveAllAttributes()
    #@effis-end
    if not os.path.exists('images'):
        os.makedirs('images')
    return io, DimInfo


def OpenStepfile(adios, config):
    SteppingDone = False
    StepEngine = None

    gname = list(config.keys())[0]
    code, group = config[gname]['reads'].strip().split('.', 1)

    StepGroup = "StepInfo"
    StepFile = config[gname]['stepfile']
    readsfile = StepFile + ".done"

    #@effis-begin StepGroup->StepGroup
    StepIO = adios.DeclareIO(StepGroup)
    StepIO.SetEngine("SST")
    StepIO.SetParameter("RendezvousReaderCount", "0")
    StepIO.SetParameter("QueueLimit", "1")
    StepIO.SetParameter("QueueFullPolicy", "Discard")
    if not(os.path.exists(readsfile)):
        StepEngine = StepIO.Open(StepFile, adios2.Mode.Read, MPI.COMM_SELF)
    else:
        SteppingDone = True
    #@effis-end

    return StepEngine, StepIO, SteppingDone, readsfile, group


def SetupArrays(DinInfo):
    uMatches = DimInfo['UserMatches'] + [DimInfo['xname']]
    uTypes = DimInfo['UserTypes'] + [DimInfo['xType']]
    data = {}
    data['_StepPhysical'] = np.zeros(1, dtype=np.float64)
    data['_StepNumber'] = np.zeros(1, dtype=np.int64)
    for name, dtype in zip(uMatches, uTypes):
        data[name] = np.zeros(tuple(DimInfo['counts']), dtype=dtype)
    return data, uMatches


def ScheduleReads(io, engine, data, uMatches):
    for name in ['_StepPhysical', '_StepNumber']:
        varid = io.InquireVariable(name)
        engine.Get(varid, data[name])
    for name in uMatches:
        varid = io.InquireVariable(name)
        varid.SetSelection([DimInfo['starts'], DimInfo['counts']])
        engine.Get(varid, data[name])


def CheckStepFile(SteppingDone, LastFoundSim, SecondLastFoundSim, StepIO, StepEngine):
    NewStep = False
    if not SteppingDone:
        StepStatus = StepEngine.BeginStep(adios2.StepMode.Read, 0.0)
        if StepStatus == adios2.StepStatus.EndOfStream:
            SteppingDone = True
        elif StepStatus == adios2.StepStatus.OK:
            NewStep = True
            SecondLastFoundSim[0] = LastFoundSim[0]
            varid = StepIO.InquireVariable("StepNumber")
            StepEngine.Get(varid, LastFoundSim)
            StepEngine.EndStep()
        elif StepStatus == adios2.StepStatus.NotReady:
            pass
        else:
            raise ValueError("Something weird happened reading the step information")

    return SteppingDone, LastFoundSim, SecondLastFoundSim, NewStep


if __name__ == "__main__":
    matplotlib.rcParams['axes.unicode_minus'] = False
    args = ParseArgs()

    yamlfile = ".kittie-groups-" + os.environ["KITTIE_NUM"] + ".yaml"
    with open(yamlfile, 'r') as ystream:
        config = yaml.load(ystream)

    yamlfile = ".kittie-codenames-" + os.environ["KITTIE_NUM"] + ".yaml"
    with open(yamlfile, 'r') as ystream:
        codeconfig = yaml.load(ystream)
    appname = codeconfig['codename']

    # Handle MPMD if needed
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    if "mpmd" in config:
        comm = comm.Split(config["mpmd"], rank)
        rank = comm.Get_rank()
        del config['mpmd']


    #@effis-init comm=comm
    adios = adios2.ADIOS(comm)

    if rank == 0:
        StepEngine, StepIO, SteppingDone, readsfile, groupname = OpenStepfile(adios, config)


    filename = None
    DimInfo = {}
    for name in ["xname", "starts", "counts", "UserMatches", "UserTypes", "xType"]:
        DimInfo[name] = None

    # This is getting the variables to distribute to plot
    if rank == 0:
        io, DimInfo = FindDims(adios)
    for name in ['xname', 'xType', 'starts', 'counts']:
        DimInfo[name] = comm.bcast(DimInfo[name], root=0)
    for name in ['UserMatches', 'UserTypes']:
        DimInfo[name] = comm.scatter(DimInfo[name], root=0)


    # Only do something on the processes where there's a plot
    color = 0
    if len(DimInfo['UserMatches']) > 0:
        color = 1
    ReadComm = comm.Split(color, rank)


    if len(DimInfo['UserMatches']) > 0:
        data, uMatches = SetupArrays(DimInfo)
        LastFoundData = np.array([-1], dtype=np.int64)
        LastFoundSim  = np.array([-1], dtype=np.int64)
        SecondLastFoundSim  = np.array([-1], dtype=np.int64)


        if rank > 0:
            #@effis-begin filename->"plotter"
            io = adios.DeclareIO(filename)
            #@effis-end
        else:
            #@effis-begin "done"->"done"
            DoneIO = adios.DeclareIO("done")
            vDone = DoneIO.DefineVariable("Step",  LastFoundSim,  [], [], [])
            name = "{0}-{1}-StepsDone.bp".format(appname, groupname)
            DoneEngine = DoneIO.Open(name, adios2.Mode.Write, MPI.COMM_SELF)
            #@effis-end


        #@effis-begin io-->"plotter"
        engine = io.Open(filename, adios2.Mode.Read, ReadComm)
        #@effis-end


        while True:

            if (rank == 0) and (not SteppingDone):
                SteppingDone, LastFoundSim, SecondLastFoundSim, NewStep = CheckStepFile(SteppingDone, LastFoundSim, SecondLastFoundSim, StepIO, StepEngine)

            #@effis-begin engine--->"plotter"
            ReadStatus = engine.BeginStep(adios2.StepMode.Read, 1.0)
            #@effis-end

            if ReadStatus == adios2.StepStatus.NotReady:
                if (rank == 0) and NewStep and (SecondLastFoundSim[0] > LastFoundData[0]):
                    #@effis-begin DoneEngine--->"done"
                    DoneEngine.BeginStep()
                    DoneEngine.Put(vDone, SecondLastFoundSim)
                    DoneEngine.EndStep()
                    #@effis-end

            elif ReadStatus != adios2.StepStatus.OK:
                if (rank == 0):
                    while not os.path.exists(readsfile):
                        continue
                    time.sleep(1)
                    with open(readsfile, 'r') as infile:
                        text = infile.read()
                    last = int(text.strip())
                    if NewStep or (last > LastFoundData[0]):
                        #@effis-begin DoneEngine--->"done"
                        DoneEngine.BeginStep()
                        DoneEngine.Put(vDone, np.array([last], dtype=np.int64))
                        DoneEngine.EndStep()
                        #@effis-end
                break

            else:

                ScheduleReads(io, engine, data, uMatches)
                #@effis-begin engine--->"plotter"
                engine.EndStep()
                #@effis-end

                outdir = os.path.join("images", "{1}-{0}".format(data['_StepNumber'][0], config['plotter']['plots']))
                if rank == 0:
                    if not os.path.exists(outdir):
                        os.makedirs(outdir)

                ReadComm.Barrier()
                LastFoundData = data['_StepNumber']
                #LastFoundStep[0] = LastFoundData[0]
                Plot(data, DimInfo['xname'], outdir)
                ReadComm.Barrier()

                if (rank == 0):
                    #@effis-begin DoneEngine--->"done"
                    DoneEngine.BeginStep()
                    DoneEngine.Put(vDone, LastFoundData)
                    DoneEngine.EndStep()
                    #@effis-end

    #@effis-finalize
