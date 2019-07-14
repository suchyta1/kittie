import os
import yaml
import numpy as np

from mpi4py import MPI
import adios2

import sys
import time


def GetType(varid):
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


class KittiePlotter(object):
    
    def __init__(self, comm):
        self.comm = comm
        self.rank = self.comm.Get_rank()

        yamlfile = ".kittie-groups-" + os.environ["KITTIE_NUM"] + ".yaml"
        with open(yamlfile, 'r') as ystream:
            self.config = yaml.load(ystream)

        # Handle MPMD if needed
        if "mpmd" in self.config:
            self.comm = comm.Split(self.config["mpmd"], self.rank)
            self.rank = self.comm.Get_rank()
            del self.config['mpmd']


    def _GetMatching(self, exclude=[], only=[], xomit=False):
        vx = self.io.InquireVariable(self.DimInfo['xname'])
        shape = vx.Shape()
        if len(shape) == 0:
            raise ValueError("Using this with a scalar for the x-axis doesn't makes sense")
        self.DimInfo['xType'] = GetType(vx)

        variables = self.io.AvailableVariables()
        if len(only) == 0:
            only = variables.keys()
        if (self.DimInfo['xname'] not in only) and (not xomit):
            only += [self.DimInfo['xname']]

        size = self.comm.Get_size()
        self.DimInfo['UserMatches'] = []
        self.DimInfo['UserTypes'] = []
        index = 0
        for i in range(size):
            self.DimInfo['UserMatches'] += [[]]
            self.DimInfo['UserTypes'] += [[]]

        for name in only:
            if (name in exclude) or ((name == self.DimInfo['xname']) and xomit):
                continue

            varid = self.io.InquireVariable(name)
            TestShape = varid.Shape()
            if shape == TestShape:
                i = index % size
                self.DimInfo['UserMatches'][i] += [name]
                dtype = GetType(varid)
                self.DimInfo['UserTypes'][i] += [dtype]
                index += 1

        return shape


    def _xParse(self, xname):
        self.DimInfo['xname'] = xname
        if xname.endswith(']'):
            start = xname.find('[')
            self.DimInfo['xname'] = xname[:start]
            xdims = xname[start+1:-1]
            xdims = xdims.split(',')
            for i in range(len(xdims)):
                xdims[i] = xdims[i].strip()
        else:
            xdims = None
        return xdims


    def _GetSelections(self, xaxis, exclude=[], only=[], xomit=False):

        # Get the name and slice
        xsel = self._xParse(xaxis)

        # Get the full shape and other variables that match it
        xShape = self._GetMatching(exclude=exclude, only=only, xomit=False)

        # Get ADIOS selections
        counts = np.array(xShape, dtype=np.int64)
        starts = np.zeros(counts.shape[0], dtype=np.int64)
        if xsel is not None:
            for j, dim in enumerate(xShape):
                if (j >= len(xsel)) or (xsel[j] == ":"):
                    continue
                else:
                    if xsel[j].find(":") != -1:
                        start, stop = xsel[j].split(":")
                        starts[j] = int(start.strip())
                        counts[j] = int( stop.strip()) - start[j]
                    else:
                        starts[j] = int(xsel[j])
                        counts[j] = 1

        self.DimInfo['starts'] = list(starts)
        self.DimInfo['counts'] = list(counts)


    def _SetupArrays(self, allx):
        self.uMatches = self.DimInfo['UserMatches']
        self.uTypes = self.DimInfo['UserTypes']
        if allx:
            self.uMatches += [self.DimInfo['xname']]
            self.uTypes += [self.DimInfo['xType']]

        self.data = {}
        self.data['_StepPhysical'] = np.zeros(1, dtype=np.float64)
        self.data['_StepNumber'] = np.zeros(1, dtype=np.int64)
        for name, dtype in zip(self.uMatches, self.uTypes):
            self.data[name] = np.zeros(tuple(self.DimInfo['counts']), dtype=dtype)


    def ConnectToStepInfo(self, adios, group=None):
        if group is None:
            self.gname = list(self.config.keys())[0]
        else:
            self.gname = group

        if self.rank == 0:
            self.SteppingDone = False
            self.StepEngine = None
            self.code, self.group = self.config[self.gname]['reads'].strip().split('.', 1)

            StepGroup = "StepInfo"
            StepFile = self.config[self.gname]['stepfile']
            self.LastStepFile = StepFile + ".done"

            #@effis-begin StepGroup->StepGroup
            self.StepIO = adios.DeclareIO(StepGroup)
            self.StepIO.SetEngine("SST")
            self.StepIO.SetParameter("RendezvousReaderCount", "0")
            self.StepIO.SetParameter("QueueLimit", "1")
            self.StepIO.SetParameter("QueueFullPolicy", "Discard")
            if not(os.path.exists(self.LastStepFile)):
                self.StepEngine = self.StepIO.Open(StepFile, adios2.Mode.Read, MPI.COMM_SELF)
            else:
                self.SteppingDone = True
            #@effis-end

        self.LastFoundData = np.array([-1], dtype=np.int64)
        self.LastFoundSim  = np.array([-1], dtype=np.int64)
        self.SecondLastFoundSim  = np.array([-1], dtype=np.int64)

        if self.rank == 0:

            yamlfile = ".kittie-codenames-" + os.environ["KITTIE_NUM"] + ".yaml"
            with open(yamlfile, 'r') as ystream:
                codeconfig = yaml.load(ystream)
            appname = codeconfig['codename']

            #@effis-begin "done"->"done"
            self.DoneIO = adios.DeclareIO("done")
            self.vDone = self.DoneIO.DefineVariable("Step",  self.LastFoundSim,  [], [], [])
            name = "{0}-{1}-StepsDone.bp".format(appname, self.group)
            self.DoneEngine = self.DoneIO.Open(name, adios2.Mode.Write, MPI.COMM_SELF)
            #@effis-end


    @property
    def Active(self):
        if len(self.DimInfo['UserMatches']) > 0:
            return True
        else:
            return False


    def GetMatchingSelections(self, adios, xaxis, exclude=[], only=[], xomit=False, allx=True):
        self.DimInfo = {}
        for name in ["xname", "starts", "counts", "UserMatches", "UserTypes", "xType"]:
            self.DimInfo[name] = None

        #@effis-begin self.gname->self.gname
        self.io = adios.DeclareIO(self.gname)
        if self.rank == 0:
            self.engine = self.io.Open(self.gname, adios2.Mode.Read, MPI.COMM_SELF)
            self._GetSelections(xaxis, exclude=exclude, only=only, xomit=xomit)
            self.engine.Close()
            self.io.RemoveAllVariables()
            self.io.RemoveAllAttributes()
            if not os.path.exists('images'):
                os.makedirs('images')
        #@effis-end

        for name in ['xname', 'xType', 'starts', 'counts']:
            self.DimInfo[name] = self.comm.bcast(self.DimInfo[name], root=0)
        for name in ['UserMatches', 'UserTypes']:
            self.DimInfo[name] = self.comm.scatter(self.DimInfo[name], root=0)

        # Only do something on the processes where there's a plot
        color = 0
        if len(self.DimInfo['UserMatches']) > 0:
            color = 1
        self.ReadComm = self.comm.Split(color, self.rank)

        if self.Active:
            self._SetupArrays(allx)
            filename = None

            #@effis-begin self.io-->"plotter"
            self.engine = self.io.Open(filename, adios2.Mode.Read, self.ReadComm)
            #@effis-end


    def _CheckStepFile(self):
        NewStep = False
        if not self.SteppingDone:
            StepStatus = self.StepEngine.BeginStep(kittie.Kittie.ReadStepMode, 0.1)
            if StepStatus == adios2.StepStatus.EndOfStream:
                self.SteppingDone = True
            elif StepStatus == adios2.StepStatus.OK:
                NewStep = True
                self.SecondLastFoundSim[0] = self.LastFoundSim[0]
                varid = self.StepIO.InquireVariable("StepNumber")
                self.StepEngine.Get(varid, self.LastFoundSim)
                self.StepEngine.EndStep()
            elif StepStatus == adios2.StepStatus.NotReady:
                pass
            else:
                raise ValueError("Something weird happened reading the step information")
        return NewStep



    @property
    def NotDone(self):
        NewStep = False

        if (self.rank == 0) and (not self.SteppingDone):
            NewStep = self._CheckStepFile()

        #self.ReadComm.Barrier()
        #@effis-begin self.engine--->"plotter"
        ReadStatus = self.engine.BeginStep(kittie.Kittie.ReadStepMode, 1.0)
        #@effis-end

        self.DoPlot = True

        if ReadStatus == adios2.StepStatus.NotReady:
            if (self.rank == 0) and NewStep and (self.SecondLastFoundSim[0] > self.LastFoundData[0]):
                #@effis-begin self.DoneEngine--->"done"
                self.DoneEngine.BeginStep()
                self.DoneEngine.Put(self.vDone, self.SecondLastFoundSim)
                self.DoneEngine.EndStep()
                #@effis-end
            self.DoPlot = False

        elif ReadStatus != adios2.StepStatus.OK:
            if (self.rank == 0):
                while not os.path.exists(self.LastStepFile):
                    continue
                #time.sleep(1)
                with open(self.LastStepFile, 'r') as infile:
                    text = infile.read()
                last = int(text.strip())
                if NewStep or (last > self.LastFoundData[0]):
                    #@effis-begin self.DoneEngine--->"done"
                    self.DoneEngine.BeginStep()
                    self.DoneEngine.Put(self.vDone, np.array([last], dtype=np.int64))
                    self.DoneEngine.EndStep()
                    #@effis-end

            self.DoPlot = False
            return False

        return True


    def _ScheduleReads(self):
        self.data['minmax'] = {}
        for name in ['_StepPhysical', '_StepNumber']:
            varid = self.io.InquireVariable(name)
            self.engine.Get(varid, self.data[name])
        for name in self.uMatches:
            varid = self.io.InquireVariable(name)
            varid.SetSelection([self.DimInfo['starts'], self.DimInfo['counts']])
            self.engine.Get(varid, self.data[name])
            variables = self.io.AvailableVariables()
            self.data['minmax'][name] = {}
            self.data['minmax'][name]['min'] = float(variables[name]['Min'])
            self.data['minmax'][name]['max'] = float(variables[name]['Max'])


    def GetPlotData(self):

        self._ScheduleReads()

        #@effis-begin self.engine--->"plotter"
        self.engine.EndStep()
        #@effis-end

        #self.outdir = os.path.join("images", "{1}-{0}".format(self.data['_StepNumber'][0], self.config['plotter']['plots']))
        self.outdir = os.path.join("images", str(self.data['_StepNumber'][0]), self.config['plotter']['plots'])
        if self.rank == 0:
            if not os.path.exists(self.outdir):
                os.makedirs(self.outdir)

        self.ReadComm.Barrier()
        self.LastFoundData = self.data['_StepNumber']
        #LastFoundStep[0] = LastFoundData[0]


    def StepDone(self):
        self.ReadComm.Barrier()
        if self.rank == 0:
            #@effis-begin self.DoneEngine--->"done"
            self.DoneEngine.BeginStep()
            self.DoneEngine.Put(self.vDone, self.LastFoundData)
            self.DoneEngine.EndStep()
            #@effis-end


