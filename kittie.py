#!/usr/bin/env python


# Let's keep everything tested with python 2 and python 3
from __future__ import absolute_import, division, print_function, unicode_literals


# Cheetah is from CODAR. It's the interface through which you use CODAR's Savanna, which composes workflows
import codar.cheetah as cheetah


# YAML is our simple input format for now
import yaml


# Other imports
import os
import shutil
import getpass
import subprocess
import argparse
import copy
import logging
import sys
import datetime


def KeepLinksCopy(inpath, outpath):
    if os.path.isdir(inpath):
        shutil.copytree(inpath, outpath, symlinks=True)
    else:
        shutil.copy(inpath, outpath, follow_symlinks=False)


class KittieJob(cheetah.Campaign):

    def LoggerSetup(self):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        time = datetime.datetime.now().strftime('%Y-%m-%d_%H.%M.%S')
        self.logfile = os.path.join(os.path.realpath("kittie-failure-logs"), "{0}.log".format(time))
        dirname = os.path.dirname(self.logfile)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        self.filehandler = logging.FileHandler(self.logfile)
        self.filehandler.setLevel(logging.INFO)
        self.filehandler.setFormatter(formatter)

        self.streamhandler = logging.StreamHandler()
        self.streamhandler.setLevel(logging.WARNING)
        self.streamhandler.setFormatter(formatter)

        self.logger.addHandler(self.filehandler)
        self.logger.addHandler(self.streamhandler)


    def KeywordSetup(self):

        filepath = os.path.realpath(__file__)
        dirname = os.path.dirname(filepath)
        keywordspath = os.path.join(dirname, "config", "keywords.yaml")

        with open(keywordspath, 'r') as ystream:
            config = yaml.load(ystream)

        self.keywords = {}
        for key in config.keys():
            self.keywords[key] = config[key]


    def SetIfNotFound(self, dictionary, keyword, value=None, level=logging.INFO):
        kw = self.keywords[keyword]
        if kw  not in dictionary.keys():
            msg = "{0} keyword not found in configuration file.".format(kw)

            if level == logging.ERROR:
                msg = "{0} It is required. Exiting".format(msg)
                self.logger.error(msg)
                sys.exit(1)
                #raise ValueError(msg)

            if level == logging.WARNING:
                output = self.logger.warn
            elif level == logging.INFO:
                output = self.logger.info

            msg = "{0} Setting it to {1}".format(msg, value)
            output(msg)
            dictionary[kw] = value


    def DefaultArgs(self):

        self.LoggerSetup()
        self.KeywordSetup()

        self.cheetahdir = '.cheetah'
        self.groupname = "kittie-run"
        self.cheetahsub = os.path.join(getpass.getuser(), self.groupname, 'run-{0:03d}'.format(0))

        allscopes = [self.keywords['copy'], self.keywords['copycontents'], self.keywords['link']]
        codescope = copy.copy(allscopes)
        codescope.append('args')


        self.SetIfNotFound(self.config, 'rundir', 'kittie-run')
        self.SetIfNotFound(self.config, 'jobname', 'kittie-job')
        self.SetIfNotFound(self.config, 'walltime', 1800, level=logging.WARNING)
        self.SetIfNotFound(self.config, 'machine', level=logging.ERROR)

        self.config[self.keywords['rundir']] = os.path.realpath(self.config[self.keywords['rundir']])
        self.codesetup = self.config['run']
        self.codenames = self.codesetup.keys()

        for name in allscopes:
            if name not in self.config.keys():
                self.config[name] = []

        for codename in self.codenames:
            for name in codescope:
                if name not in self.codesetup[codename].keys():
                    self.codesetup[codename][name] = []


    def init(self, yamlfile):

        # Read in the config file
        with open(yamlfile, 'r') as ystream:
            self.config = yaml.load(ystream)

        self.DefaultArgs()


        # Global Cheetah keywords
        self.output_dir = os.path.join(self.config['rundir'], self.cheetahdir)
        self.name = self.config['jobname']


        # These are my own things, not Cheetah things
        self.mainpath = os.path.realpath(os.path.join(self.output_dir, self.cheetahsub))
        self.machine = self.config['machine']['name']
        machinekeys = self.config['machine'].keys()
        sweepargs = []


        # Machine-based Cheetah options
        self.supported_machines = [self.machine]
        self.node_layout = {self.machine: []}
        self.scheduler_options = {self.machine: {}}
        if 'charge' in machinekeys:
            self.scheduler_options[self.machine]['project'] = self.config['machine']['charge']
        if 'queue' in machinekeys:
            self.scheduler_options[self.machine]['queue'] = self.config['machine']['queue']


        # Cheetah options that Setup the codes that will lanuch
        self.codes = []

        for codename in self.codenames:

            codedict = {}
            codedict['exe'] = self.codesetup[codename]['path']
            self.codes.append((codename, codedict))


            # Set the number of processes
            sweeparg = cheetah.parameters.ParamRunner(codename, "nprocs", [self.codesetup[codename]['processes']])
            self.node_layout[self.machine].append({codename: self.codesetup[codename]['processes-per-node']})
            sweepargs.append(sweeparg)

            # Set the command line arguments
            args = self.codesetup[codename]['args']
            for i, arg in enumerate(args):
                sweeparg = cheetah.parameters.ParamCmdLineArg(codename, "arg{0}".format(i), i, [arg])
                sweepargs.append(sweeparg)

        sweep = cheetah.parameters.Sweep(sweepargs, node_layout=self.node_layout)
        sweepgroup = cheetah.parameters.SweepGroup(self.groupname, walltime=self.config['walltime'], parameter_groups=[sweep], component_subdirs=True)
        self.sweeps = [sweepgroup]


    def _Copy(self, copydict, outdir):
        for name in copydict[self.keywords['link']]:
            newpath = os.path.join(outdir, os.path.basename(name))
            os.symlink(name, newpath)

        for name in copydict[self.keywords['copy']]:
            newpath = os.path.join(outdir, os.path.basename(name))
            KeepLinksCopy(name, newpath)

        for name in copydict[self.keywords['copycontents']]:
            if os.path.isdir(name):
                for subname in os.listdir(name):
                    subpath = os.path.join(name, subname)
                    newpath = os.path.join(outdir, os.path.basename(subname))
                    KeepLinksCopy(subpath, newpath)
            else:
                newpath = os.path.join(outdir, os.path.basename(name))
                shutil.copy(name, newpath, follow_symlinks=False)


    def Copy(self):

        self._Copy(self.config, self.mainpath)

        for codename in self.codenames:
            codepath = os.path.join(self.mainpath, codename)
            self._Copy(self.codesetup[codename], codepath)


    def DoCommands(self, path, dictionary):
        keyword = self.keywords['pre-sub-cmds']
        if keyword in dictionary.keys():
            os.chdir(path)
            for cmd in dictionary[keyword]:
                args = cmd.split()
                subprocess.call(args)


    def PreSubmitCommands(self):
        self.DoCommands(self.mainpath, self.config)
        for codename in self.config['run']:
            self.DoCommands(os.path.join(self.mainpath, codename), self.config['run'][codename])


    def Link(self):
        os.chdir(self.mainpath)
        mainlist = os.listdir(self.mainpath)
        for name in mainlist:
            if name.startswith('codar.cheetah.') or name.startswith('.codar.cheetah.') or  (name == "tau.conf"):
                continue
            linksrc = os.path.join(self.cheetahdir, self.cheetahsub, name)
            linkpath = os.path.join(self.config['rundir'], name)
            os.symlink(linksrc, linkpath)


    def __init__(self, yamlfile):
        self.init(yamlfile)
        super(KittieJob, self).__init__(self.machine, "")
        self.make_experiment_run_dir(self.output_dir)
        self.Copy()
        self.PreSubmitCommands()
        self.Link()

        outlog = os.path.join(self.config['rundir'], "kittie-setup-{0}".format(os.path.basename(self.logfile)) )
        shutil.move(self.logfile, outlog)
        checkdir = os.path.dirname(self.logfile)
        remaining = os.listdir(checkdir)
        if len(remaining) == 0:
            shutil.rmtree(checkdir)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("configfile", help="Path to Kittie configuration file", metavar="Config-file")
    args = parser.parse_args()

    kittiejob = KittieJob(args.configfile)

