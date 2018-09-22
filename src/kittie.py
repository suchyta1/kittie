#!/usr/bin/env python


# Let's keep everything tested with python 2 and python 3
from __future__ import absolute_import, division, print_function, unicode_literals


# Cheetah is from CODAR. It's the interface through which you use CODAR's Savanna, which composes workflows
import codar.cheetah as cheetah


# Other imports
import argparse
import copy
import datetime
import getpass
import logging
import re
import os
import shutil
import subprocess
import sys
import yaml


def KeepLinksCopy(inpath, outpath):
    if os.path.isdir(inpath):
        shutil.copytree(inpath, outpath, symlinks=True)
    else:
        shutil.copy(inpath, outpath, follow_symlinks=False)


class KittieJob(cheetah.Campaign):


    def _KeywordSetup(self):
        """
        The keywords.yaml file defines the keyword setup. Change the file change the names
        """

        filepath = os.path.realpath(__file__)
        dirname = os.path.dirname(os.path.dirname(filepath))
        keywordspath = os.path.join(dirname, "config", "keywords.yaml")

        with open(keywordspath, 'r') as ystream:
            config = yaml.load(ystream)

        self.keywords = {}
        for key in config.keys():
            self.keywords[key] = config[key]


    def _SetIfNotFound(self, dictionary, keyword, value=None, level=logging.INFO):
        """
        Method to set a config variable to some default value if it doesn't appear in the user's input config file.
        We may want to log too, warn, or possible abort trying to set something up if it's not given.
        """

        kw = self.keywords[keyword]
        if kw  not in dictionary.keys():
            msg = "{0} keyword not found in configuration file.".format(kw)

            if level == logging.ERROR:
                msg = "{0} It is required. Exiting".format(msg)
                self.logger.error(msg)
                sys.exit(1)
                #raise ValueError(msg)

            elif level == logging.WARNING:
                output = self.logger.warn
            elif level == logging.INFO:
                output = self.logger.info

            msg = "{0} Setting it to {1}".format(msg, value)
            output(msg)
            dictionary[kw] = value


    def _BlankInit(self, names, dictionary, value):
        """
        Helper for empty iterables
        """

        for name in names:
            if name not in dictionary.keys():
                dictionary[name] = value


    def _DefaultArgs(self):
        """
        There are a reasonable number of config params. It's a good idea to have some automated defaulting going on.
        """

        # Kittie allows the user to set their own names for the fields in the config file if she wants.
        self._KeywordSetup()

        # Some things that'll be given to Cheetah
        self.cheetahdir = '.cheetah'
        self.groupname = "kittie-run"
        self.cheetahsub = os.path.join(getpass.getuser(), self.groupname, 'run-{0:03d}'.format(0))

        # Allow certain sets of keywords generally in different parts of the config file
        allscopes_list = [self.keywords['copy'], self.keywords['copycontents'], self.keywords['link']]
        codescope_list = copy.copy(allscopes_list)
        codescope_list.append('args')
        allscopes_dict = [self.keywords['file-edit']]

        # Do something (possible warn or exit) if certain things aren't found
        self._SetIfNotFound(self.config, 'rundir', 'kittie-run')
        self._SetIfNotFound(self.config, 'jobname', 'kittie-job')
        self._SetIfNotFound(self.config, 'walltime', 1800, level=logging.WARNING)

        self._SetIfNotFound(self.config, 'machine', level=logging.ERROR)
        self._SetIfNotFound(self.config['machine'], 'name', level=logging.ERROR)
        self._SetIfNotFound(self.config['machine'], 'job_setup', value=None, level=logging.INFO)
        self._SetIfNotFound(self.config['machine'], 'submit_setup', value=None, level=logging.INFO)
        self._SetIfNotFound(self.config['machine'], 'runner_extra', value="", level=logging.INFO)

        self.config[self.keywords['rundir']] = os.path.realpath(self.config[self.keywords['rundir']])

        # Default blank iterables
        self._BlankInit(allscopes_dict, self.config, {})
        self._BlankInit(allscopes_list, self.config, [])

        self.codesetup = self.config['run']
        self.codenames = self.codesetup.keys()
        for codename in self.codenames:
            self._BlankInit(allscopes_dict, self.codesetup[codename], {})
            self._BlankInit(codescope_list, self.codesetup[codename], [])


    """
    def _AlternateMakeReplacements(self):
        if searchstr is None:
            searchstr = yaml.dump(self.config, default_flow_style=False)
            main = True
        else:
            main = False


        pattern = '(?<!\$)\$\{(.*)\}'
        search = re.compile(pattern)
        results = search.findall(searchstr)


        for match in results:
            origmatch = match

            # This assumes that lists always end the entries. That's probably OK, at least for now
            mpattern = "(.*)\[(\d*)\]$"
            msearch = re.compile(mpattern)
            index = []

            while True:
                subresults = msearch.findall(match)
                if len(subresults) == 0:
                    break

                # This wan't fully working yet
                # I discontinued the [] instead of . dictionary indexing b/c it became hard to read

                v = subresults[0][1]
                if v[0] in ('-', '+'):
                    check = v[1:]
                else:
                    check = v

                if check.isdigit():
                    v = int(v)
                else:
                    v = self._MakeReplacements(v)

                index.insert(0, v)
                match = subresults[0][0]


            print(index)
            print(match, origmatch)
            value = self.config[match]
            for i in index:
                value = value[i]


            match = self._MakeReplacements(match)
            keys = match.split(".")
            value = self.config

            for key in keys:
                value = value[key]
            for i in index:
                value = value[i]

            subpattern = "\$\{" + origmatch.replace(".", "\.").replace('[', '\[').replace(']', '\]').replace('$', '\$') + "\}"
            subsearch = re.compile(subpattern)
            searchstr = subsearch.sub(str(value), searchstr, count=1)

        if main:
            searchstr = searchstr.replace('$${', '${')
            self.config = yaml.load(searchstr)
        else:
            return searchstr
    """


    def _MakeReplacements(self, searchstr=None):
        """
        Look for ${} things to be replaced in the user's input config file, and replace them with the values defined elsewhere in the file.
        """

        # The alternate method wan't fully working yet
        # I discontinued the [] instead of . dictionary indexing b/c it became hard to read
        #_self.AlternateReplacementChecking()


        # Did we call the function the first time, or are we doing it recursively?
        if searchstr is None:
            searchstr = yaml.dump(self.config, default_flow_style=False)
            main = True
        else:
            main = False


        pattern = '(?<!\$)\$\{(.*)\}'
        search = re.compile(pattern)
        results = search.findall(searchstr)


        for match in results:
            origmatch = match

            # This assumes that lists always end the entries. That's probably OK, at least for now
            mpattern = "(.*)\[(\d*)\]$"
            msearch = re.compile(mpattern)
            index = []

            # Iteratively looks for lists ending the objects
            while True:
                subresults = msearch.findall(match)
                if len(subresults) == 0:
                    break

                index.insert(0, int(subresults[0][1]))
                match = subresults[0][0]

            # The name location itself by be defined in terms of other things, so call the method on that too to resolve it
            match = self._MakeReplacements(match)
            keys = match.split(".")
            value = self.config

            # Set the located value in our config text that weve been looking through to replace to the old value
            for key in keys:
                value = value[key]
            for i in index:
                value = value[i]
            subpattern = "\$\{" + origmatch.replace(".", "\.").replace('[', '\[').replace(']', '\]').replace('$', '\$') + "\}"
            subsearch = re.compile(subpattern)
            searchstr = subsearch.sub(str(value), searchstr, count=1)

        # Propogate the changes back into the config dictionary
        if main:
            searchstr = searchstr.replace('$${', '${')
            self.config = yaml.load(searchstr)
        else:
            return searchstr


    def _Copy(self, copydict, outdir):
        """
        Save files into the job area
        """

        # Do the user's requested links and copies
        for name in copydict[self.keywords['link']]:
            newpath = os.path.join(outdir, os.path.basename(name))
            os.symlink(name, newpath)

        for name in copydict[self.keywords['copycontents']]:
            if os.path.isdir(name):
                for subname in os.listdir(name):
                    subpath = os.path.join(name, subname)
                    newpath = os.path.join(outdir, os.path.basename(subname))
                    KeepLinksCopy(subpath, newpath)
            else:
                newpath = os.path.join(outdir, os.path.basename(name))
                shutil.copy(name, newpath, follow_symlinks=False)

        for name in copydict[self.keywords['copy']]:
            if type(name) == list:
                newpath = os.path.join(outdir, os.path.basename(name[1]))
                KeepLinksCopy(name[0], newpath)
            else:
                newpath = os.path.join(outdir, os.path.basename(name))
                KeepLinksCopy(name, newpath)


        # Do the user's requested file editing
        edits = copydict[self.keywords['file-edit']]
        for filename in edits.keys():
            filepath = os.path.join(outdir, filename)
            if not os.path.exists(filepath):
                self.logger.warn("{0} does not exist. Ignorning request to edit the file.".format(filepath))
                continue
            with open(filepath) as instream:
                txt = instream.read()

            # Handle search and replacement as Python regular expressions
            replacements = edits[filename]
            for replacement in replacements:
                search = re.compile(replacement[0], re.MULTILINE)
                txt = search.sub(replacement[1], txt)

            # Save a backup file of what the old file looked like
            bdir = os.path.join(os.path.dirname(filepath), ".bak")
            if not os.path.exists(bdir):
                os.makedirs(bdir)

            # Writ the updated file
            shutil.copy(filepath, os.path.join(bdir, os.path.basename(filepath)))
            with open(filepath, 'w') as outstream:
                outstream.write(txt)


    def _DoCommands(self, path, dictionary):
        keyword = self.keywords['pre-sub-cmds']
        if keyword in dictionary.keys():
            os.chdir(path)
            for cmd in dictionary[keyword]:
                args = cmd.split()
                subprocess.call(args)


    ###################################################################################################################################################
    ### Below here are the methods that the __init__() directly calls. The distinction isn't super important, but useful for categorizing thef file
    ###################################################################################################################################################

    def LoggerSetup(self):
        """
        Kittie automatially keeps track of a logfile (named by the current system time).
        If there is an error while this script is running, it will save the log to kittie-failure-logs/
        In the case there the script completes, it copies the log into the user's output directory
        Anything warning level or more severe will print to the screen too.
        I may make the different verbosities configurable.
        """

        # Python's loggers belong to a namespace
        self.logger = logging.getLogger(__name__)

        # Make sure the top level part of the logger handles all messages. Different handlers can set different verbosities
        self.logger.setLevel(logging.DEBUG)

        # Set the output formatting style
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        time = datetime.datetime.now().strftime('%Y-%m-%d_%H.%M.%S')

        # Where to write the log file
        self.logfile = os.path.join(os.path.realpath("kittie-failure-logs"), "{0}.log".format(time))
        dirname = os.path.dirname(self.logfile)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        # File handler
        self.filehandler = logging.FileHandler(self.logfile)
        self.filehandler.setLevel(logging.INFO)
        self.filehandler.setFormatter(formatter)

        # Stream = console (terminal) output
        self.streamhandler = logging.StreamHandler()
        self.streamhandler.setLevel(logging.WARNING)
        self.streamhandler.setFormatter(formatter)

        self.logger.addHandler(self.filehandler)
        self.logger.addHandler(self.streamhandler)


    def init(self, yamlfile):
        """
        init() is what does the Cheetah-related setup.
        It doesn't require the user to write a Cheetah class file. It reads the Kittie config file, and then figures out how to subclass Cheetah.
        """

        # Read in the config file
        with open(yamlfile, 'r') as ystream:
            self.config = yaml.load(ystream)

        # Make value replacements -- this when the user does things like processes-per-node: ${run.xgc.processes}
        self._MakeReplacements()


        # Set defaults if they're not found in the config file
        self._DefaultArgs()


        # Global Cheetah keywords
        self.output_dir = os.path.join(self.config['rundir'], self.cheetahdir)
        self.name = self.config['jobname']


        # These are my own things, not Cheetah things per se, but are convenient to work with the Cheetah output
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

        # A sweep encompasses is a set of parameters that can vary. In my case nothing is varying, and the only sweep paramter is a single number of processes
        sweep = cheetah.parameters.Sweep(sweepargs, node_layout=self.node_layout)

        # A sweepgroup runs a sweep by submiting a single job. There could be more than one sweepgroup, given by the sweeps list attribute, which would submit mutliple inpedent jobs.
        sweepgroup = cheetah.parameters.SweepGroup(self.groupname, walltime=self.config['walltime'], parameter_groups=[sweep], component_subdirs=True)
        self.sweeps = [sweepgroup]


        if self.config['machine']['job_setup'] is not None:
            self.app_config_scripts = {self.machine: os.path.realpath(self.config['machine']['job_setup'])}

        if self.config['machine']['submit_setup'] is not None:
            self.run_dir_setup_script = os.path.realpath(self.config['machine']['submit_setup'])


    def Copy(self):
        """
        Copy() handles what the user asked to copy and/or symbolically link.
        It also makes the file edits the user user asks for and then copyies them into the output area.
        """

        self._Copy(self.config, self.mainpath)

        for codename in self.codenames:
            codepath = os.path.join(self.mainpath, codename)
            self._Copy(self.codesetup[codename], codepath)



    def PreSubmitCommands(self):
        """
        PreSubmitCommands issues the commands that user asks for in the config file.
        These happend while this Kittie job setup is happening -- not during the actual compute job.
        One might do things like make directories.
        """
        self._DoCommands(self.mainpath, self.config)
        for codename in self.config['run']:
            self._DoCommands(os.path.join(self.mainpath, codename), self.config['run'][codename])


    def Link(self):
        """
        Link() takes care of presenting the user with correct Cheetah directory and files according to where the user wanted the output.
        It doesn't present the user with everything there b/c an "orindary" user likely won't understand what it is all is and could get confused.
        Everything from cheetash is still there, just grouped into the .cheetah directory.
        Link() uses symbolic links but it has nothing to do with the `link` keyword in the Kittie config file.
        """

        os.chdir(self.mainpath)
        mainlist = os.listdir(self.mainpath)
        for name in mainlist:
            if name.startswith('codar.cheetah.') or name.startswith('.codar.cheetah.') or  (name == "tau.conf"):
                continue
            linksrc = os.path.join(self.cheetahdir, self.cheetahsub, name)
            linkpath = os.path.join(self.config['rundir'], name)
            os.symlink(linksrc, linkpath)


    def MoveLog(self):
        """
        If we get here, we've successfully built a cheetah job. Move the Kittie log into the output directory
        """

        outlog = os.path.join(self.config['rundir'], "kittie-setup-{0}".format(os.path.basename(self.logfile)) )
        shutil.move(self.logfile, outlog)
        checkdir = os.path.dirname(self.logfile)
        remaining = os.listdir(checkdir)
        if len(remaining) == 0:
            shutil.rmtree(checkdir)




    def __init__(self, yamlfile):
        self.LoggerSetup()
        self.init(yamlfile)
        super(KittieJob, self).__init__(self.machine, "")
        self.make_experiment_run_dir(self.output_dir, runner_extra=self.config['machine']['runner_extra'])
        self.Copy()
        self.PreSubmitCommands()
        self.Link()
        self.MoveLog()


if __name__ == "__main__":
    """
    main() doesn't do much itself. Just parses the commnand line args and initialized a Kittie object
    """

    # I'll probably need more args eventually, but probably not many -- maybe and --overwrite
    parser = argparse.ArgumentParser()
    parser.add_argument("configfile", help="Path to Kittie configuration file", metavar="Config-file")
    args = parser.parse_args()

    kittiejob = KittieJob(args.configfile)

