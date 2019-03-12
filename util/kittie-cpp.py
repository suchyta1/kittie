#!/usr/bin/env python

from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import os
import re
import copy
import subprocess

import kittie_common


class KittieParser(object):

    @property
    def InitStr(self):
        comment = {self.knowntypes['python']: '#', self.knowntypes['fortran']: '!'}
        return "{0}@kittie".format(comment[self.filetype])

    @property
    def FunctionKey(self):
        func = {self.knowntypes['python']: '', self.knowntypes['fortran']: 'call'}
        return func[self.filetype]

    @property
    def DeclareCommand(self):
        command = {self.knowntypes['python']: '', self.knowntypes['fortran']: 'adios2_declare_io'}
        return command[self.filetype]

    @property
    def OpenCommand(self):
        command = {self.knowntypes['python']: '', self.knowntypes['fortran']: 'adios2_open'}
        return command[self.filetype]

    @property
    def CloseCommand(self):
        command = {self.knowntypes['python']: '', self.knowntypes['fortran']: 'adios2_close'}
        return command[self.filetype]

    @property
    def DefineCommand(self):
        command = {self.knowntypes['python']: '', self.knowntypes['fortran']: 'adios2_define_variable'}
        return command[self.filetype]

    @property
    def BeginStepCommand(self):
        command = {self.knowntypes['python']: '', self.knowntypes['fortran']: 'adios2_begin_step'}
        return command[self.filetype]

    @property
    def EndStepCommand(self):
        command = {self.knowntypes['python']: '', self.knowntypes['fortran']: 'adios2_end_step'}
        return command[self.filetype]

    @property
    def InquireCommand(self):
        command = {self.knowntypes['python']: '', self.knowntypes['fortran']: 'adios2_inquire_variable'}
        return command[self.filetype]

    @property
    def GetCommand(self):
        command = {self.knowntypes['python']: '', self.knowntypes['fortran']: 'adios2_get'}
        return command[self.filetype]

    @property
    def PutCommand(self):
        command = {self.knowntypes['python']: '', self.knowntypes['fortran']: 'adios2_put'}
        return command[self.filetype]


    def DetectFiletype(self):
        self.filetype = None
        self.knowntypes = {'python': 'python', 'fortran': 'fortran'}
        tests = [
            ('.py',  self.knowntypes['python']),
            ('.F90', self.knowntypes['fortran']),
            ('.f90', self.knowntypes['fortran'])
        ]

        for test in tests:
            if self.filename.endswith(test[0]):
                self.filetype = test[1]
                break

        if self.filetype is None:
            raise ValueError("Recognized filetype was not detected for {0}".format(filename))


    def __init__(self, filename, outfilename):
        self.AddStep = False
        self.filename = os.path.realpath(filename)
        self.outfilename = os.path.realpath(outfilename)
        self.DetectFiletype()

        self.keydict = {}
        self.keywords = ["step", "dir", "timefile", "group", "filename", "ierr", "varname", "varid"]
        for key in self.keywords:
            self.keydict[key] = None


    def _EscapeSearch(self, text, shift):
        exp1 = "\s*"
        exp1 = "[ \t\r\f\v]*"
        search1 = re.compile(exp1)
        exp2 = "\\\\\n"
        search2 = re.compile(exp2)

        while True:

            result = search1.match(text)
            if result is None:
                break
            end = result.end()
            text = text[end:]
            shift += end

            result = search2.match(text)
            if result is None:
                break
            end = result.end()
            text = text[end:]
            shift += end

        return text, shift


    def ParseCommand(self, command, text):
        open_index = None
        end_index = None
        found = False

        startexpr = "{0}".format(self.FunctionKey)
        search = re.compile(startexpr)
        results = list(search.finditer(text))

        for i, result in enumerate(results):
            shift = 0

            if result is not None:
                open_index = result.start()
                end_index = result.end()
                newstr = text[end_index:]
                shift += result.end() - result.start()
                newstr, shift = self._EscapeSearch(newstr, shift)

                startexp = "{0}".format(command)
                search = re.compile(startexp)
                result = search.match(newstr)
                if result is not None:
                    newstr = newstr[result.end():]
                    shift += result.end()

            if result is not None:
                newstr, shift = self._EscapeSearch(newstr, shift)
                startexp = "\("
                search = re.compile(startexp)
                result = search.match(newstr)
                if result is None:
                    raise ValueError("Error in {0} function open".format(command))

                expr = "^\(.*\)"
                search = re.compile(expr)
                result = search.match(newstr.replace("\\\n", ""))
                if result is None:
                    raise ValueError("Error in {0} function close".format(command))
                expr = "\\\\\n"
                search = re.compile(expr)
                nresult = search.findall(newstr)
                num = len(nresult)
                shift += result.end() + num * 2
                end_index = open_index + shift
                found = True
                break

        if found:
            return (open_index, end_index)
        else:
            return (None, None)


    def FindMarkups(self, text):
        expr = "({0})(.*)$".format(self.InitStr)
        comp = re.compile(expr, re.MULTILINE)
        matches = list(comp.finditer(text))
        return matches


    def FindKeyVals(self, text, keydict=None):
        if keydict is None:
            keydict = copy.copy(self.keydict)
        kvs = text.split(",")
        for kv in kvs:
            k = kv.strip()
            key, value = k.split("=")
            if (key == "step") and (value == "None"):
                self.AddStep = True
                continue
            if key in self.keywords:
                keydict[key] = value

        if keydict["group"] is None:
            raise ValueError("All KITTIE markups most denote which group they're associated to")

        return keydict


    def FindCode(self, matches, i, text):
        startpos = matches[i].end()
        for j in range(i + 1, len(matches)):
            nextmatch = matches[j]
            if nextmatch.group(2).strip() == "":
                endpos = nextmatch.start()
                break
        between = text[startpos:endpos]
        return between, startpos, endpos


    def GetIndentation(self, between):
        nonwhite = "\S"
        search = re.compile(nonwhite)
        result = search.search(between)

        if result is not None:
            reverse = between[:result.start()][::-1]
            newline = "\n"
            search = re.compile(newline)
            result = search.search(reverse)
            if result is not None:
                indentation = reverse[:result.start()][::-1]
        return indentation


    def OptionAdd(self, name, keydict, commanddict, argstr):
        if keydict[name] is not None:
            argstr = "{0}, {1}={2}".format(argstr, name, keydict[name])
        elif name in commanddict:
            argstr = "{0}, {1}={2}".format(argstr, name, commanddict[name])
        return argstr


    def GetArgList(self, text):
        bss = text.strip()
        argstart = bss.find('(') + 1
        astr = bss[argstart:-1]

        alist = []
        opened = 0
        start = 0
        for i in range(len(astr)):
            if astr[i] == '(':
                opened += 1
            elif astr[i] == ')':
                opened -= 1
            elif (astr[i] == ',') and (opened == 0):
                alist += [astr[start:i].strip()]
                start = i + 1
            elif i == len(astr) - 1:
                alist += [astr[start:].strip()]
        return alist

    def GetAdiosArgs(self, text, commanddict, names):
        alist = self.GetArgList(text)
        for i, name in enumerate(names):
            commanddict[name] = alist[i]
        return commanddict

    def CommandKeyAdd(self, names, keydict, commanddict):
        for key in names:
            if (key in keydict) and (keydict[key] is not None):
                commanddict[key] = keydict[key]
        return commanddict


    def CommonNoOptions(self, commanddict, keydict, command, text, args, newargs, kittie_command, result=None):
        start, stop = self.ParseCommand(command, text)
        if start is not None:
            commanddict = self.GetAdiosArgs(text[start:stop], commanddict, args)
            commanddict = self.CommandKeyAdd(newargs, keydict, commanddict)
            if self.filetype == self.knowntypes['fortran']:
                if result is None:
                    txt = "call {0}(".format(kittie_command)
                else:
                    txt = "{0} = {1}(".format(commanddict[result], kittie_command)
                for key in newargs:
                    txt = "{0}{1}, ".format(txt, commanddict[key])
                txt = "{0})".format(txt.rstrip(', '))
            text = '{0}{1}{2}'.format(text[:start], txt, text[stop:])
        return text, commanddict, start


    def ReplaceOpen(self, between, commanddict, keydict):
        start, stop = self.ParseCommand(self.OpenCommand, between)
        if start is not None:
            commanddict = self.GetAdiosArgs(between[start:stop], commanddict, ['engine', 'io', 'filename', 'open_mode', 'comm', 'ierr'])
            txt = '{0}{1}'.format(self.InitStr[0], between[start:stop])

            if self.AddStep:
                if commanddict['open_mode'] == "adios2_mode_read":
                    keydict["step"] = 0

                argstr = "common_helper, {0}, {1}, {2}, {3}".format(commanddict['filename'], commanddict['group'], commanddict['open_mode'], commanddict['comm'])
                for name in ["step", "ierr", "dir", "timefile"]:
                    argstr = self.OptionAdd(name, keydict, commanddict, argstr)
                txt = "call kittie_couple_start({0})".format(argstr)
                between = '{0}{1}{2}'.format(between[:start], txt, between[stop:])
            else:
                between = '{0}{1}{2}'.format(between[:start], "", between[stop:])

        return between, commanddict, start


    def ReplaceClose(self, between, commanddict, keydict):
        start, stop = self.ParseCommand(self.CloseCommand, between)
        if start is not None:
            commanddict = self.GetAdiosArgs(between[start:stop], commanddict, ['engine', 'ierr'])
            if self.AddStep:
                between, commanddict, start = self.CommonNoOptions(commanddict, keydict, self.CloseCommand, between, ['engine', 'ierr'], ['helper', 'ierr'], "kittie_couple_end_step")
            else:
                between = '{0}{1}{2}'.format(between[:start], "", between[stop:])

        return between, commanddict, start


    def ReplaceDefineVariable(self, between, commanddict, keydict, start=-1):
        start, stop = self.ParseCommand(self.DefineCommand, between)
        if start is not None:
            if self.filetype == self.knowntypes['fortran']:
                try:
                    names = ['varid', 'io', 'varname', 'dtype', 'ndims', 'global_dims', 'global_offsets', 'local_dims', 'constant_dims', 'ierr']
                    commanddict = self.GetAdiosArgs(between[start:stop], commanddict, names)
                    knames = ['group', 'varname', 'dtype', 'ndims', 'global_dims', 'global_offsets', 'local_dims', 'ierr', 'constant_dims']
                except:
                    names = ['varid', 'io', 'varname', 'dtype', 'ierr']
                    commanddict = self.GetAdiosArgs(between[start:stop], commanddict, names)
                    knames = ['group', 'varname', 'dtype', 'ierr']

                commanddict['io'] = "common_helper%io"
                commanddict = self.CommandKeyAdd(['ierr'], keydict, commanddict)

                txt = "call kittie_define_variable("
                for key in knames:
                    txt = "{0}{1}, ".format(txt, commanddict[key])
                txt = "{0})".format(txt.rstrip(', '))
                between = '{0}{1}{2}'.format(between[:start], txt, between[stop:])
        return between, commanddict, start


    def ReplaceDeclareIO(self, between, commanddict, keydict):
        if self.filetype == self.knowntypes['fortran']:
            #between, commanddict, start = self.CommonNoOptions(commanddict, keydict, self.DeclareCommand, between, ['io', 'adios', 'group', 'ierr'], ['group', 'ierr'], "kittie_declare_io")
            between, commanddict, start = self.CommonNoOptions(commanddict, keydict, self.DeclareCommand, between, ['io', 'adios', 'group', 'ierr'], ['group', 'ierr'], "KittieDeclareIO", result='io')
        return between, commanddict, start

    def ReplaceEndStep(self, between, commanddict, keydict):
        if self.filetype == self.knowntypes['fortran']:
            between, commanddict, start = self.CommonNoOptions(commanddict, keydict, self.EndStepCommand, between, ['engine', 'ierr'], ['helper', 'ierr'], "kittie_couple_end_step")
        return between, commanddict, start


    def ReplaceBeginStep(self, between, commanddict, keydict):
        start, stop = self.ParseCommand(self.BeginStepCommand, between)
        if start is not None:
            try:
                commanddict = self.GetAdiosArgs(between[start:stop], commanddict, ['engine', 'step_mode', 'timeout', 'status', 'ierr'])
            except:
                commanddict = self.GetAdiosArgs(between[start:stop], commanddict, ['engine', 'step_mode', 'ierr'])
            if self.filetype == self.knowntypes['fortran']:
                argstr = "common_helper, {0}, {1}, {2}, {3}".format(commanddict['filename'], keydict['group'], commanddict['open_mode'], commanddict['comm'])
                for name in ["step", "ierr", "dir", "timefile"]:
                    argstr = self.OptionAdd(name, keydict, commanddict, argstr)
                txt = "call kittie_couple_start({0})".format(argstr)
            between = '{0}{1}{2}'.format(between[:start], txt, between[stop:])
        return between, commanddict, start


    def ReplaceInquire(self, between, commanddict, keydict):
        start, stop = self.ParseCommand(self.InquireCommand, between)
        if start is not None:
            commanddict = self.GetAdiosArgs(between[start:stop], commanddict, ['varid', 'io', 'varname', 'ierr'])
            if self.filetype == self.knowntypes['fortran']:
                txt = "call @{3}({0}, common_helper%io, {1}, {2})".format(commanddict['varid'], commanddict['varname'], commanddict['ierr'], self.InquireCommand)
            between = '{0}{1}{2}'.format(between[:start], txt, between[stop:])
        return between, commanddict, start

    def ReplaceGet(self, between, commanddict, keydict):
        start, stop = self.ParseCommand(self.GetCommand, between)
        if start is not None:
            try:
                commanddict = self.GetAdiosArgs(between[start:stop], commanddict, ['engine', 'varid', 'data', 'get_mode', 'ierr'])
            except:
                commanddict = self.GetAdiosArgs(between[start:stop], commanddict, ['engine', 'varid', 'data', 'ierr'])
                commanddict['get_mode'] = "adios2_mode_deferred"

            if self.filetype == self.knowntypes['fortran']:
                txt = "call @{4}(common_helper%engine, {0}, {1}, {2}, {3})".format(commanddict['varid'], commanddict['data'], commanddict['get_mode'], commanddict['ierr'], self.GetCommand)
            between = '{0}{1}{2}'.format(between[:start], txt, between[stop:])
        return between, commanddict, start

    def ReplacePut(self, between, commanddict, keydict):
        start, stop = self.ParseCommand(self.PutCommand, between)
        if start is not None:
            commanddict = self.GetAdiosArgs(between[start:stop], commanddict, ['engine', 'varname', 'outdata', 'ierr'])
            if self.filetype == self.knowntypes['fortran']:
                txt = "call @{3}(common_helper%engine, {0}, {1}, {2})".format(commanddict['varname'], commanddict['outdata'], commanddict['ierr'], self.PutCommand)
            between = '{0}{1}{2}'.format(between[:start], txt, between[stop:])
        return between, commanddict, start


    def Replacer(self, func, between, commanddict, keydict):
        start = True
        while start is not None:
            between, commanddict, start = func(between, commanddict, keydict)
        for name in [self.DefineCommand, self.InquireCommand, self.GetCommand, self.PutCommand]:
            between = between.replace("@{0}".format(name), name)
        return between, commanddict


    def FileReplacements(self):
        with open(self.filename, 'r') as infile:
            text = infile.read()
        matches = self.FindMarkups(text)
        start = 0
        newtext = ""

        keydict = None
        for i in range(len(matches)):
            self.AddStep = False
            matchtext = matches[i].group(2)
            if matchtext.strip() == "":
                keydict = None
                continue

            keydict = self.FindKeyVals(matchtext, keydict=keydict)
            between, bstart, bend = self.FindCode(matches, i, text)
            indentation = self.GetIndentation(between)

            commanddict = {'helper': 'common_helper'}
            between, commanddict = self.Replacer(self.ReplaceDeclareIO, between, commanddict, keydict)
            between, commanddict = self.Replacer(self.ReplaceDefineVariable, between, commanddict, keydict)
            between, commanddict = self.Replacer(self.ReplaceOpen, between, commanddict, keydict)
            between, commanddict = self.Replacer(self.ReplaceBeginStep, between, commanddict, keydict)
            between, commanddict = self.Replacer(self.ReplaceInquire, between, commanddict, keydict)
            between, commanddict = self.Replacer(self.ReplaceEndStep, between, commanddict, keydict)
            between, commanddict = self.Replacer(self.ReplaceClose, between, commanddict, keydict)
            between, commanddict = self.Replacer(self.ReplaceGet, between, commanddict, keydict)
            between, commanddict = self.Replacer(self.ReplacePut, between, commanddict, keydict)
            between = "\n{0}call kittie_get_helper({1}, common_helper){2}".format(indentation, keydict['group'], between)

            newtext = "{0}{1}{2}".format(newtext, text[start:bstart], between)
            start = bend

        newtext = "{0}{1}".format(newtext, text[start:])
        with open(self.outfilename, 'w') as out:
            out.write(newtext)


    def FindGroups(self, groups):
        with open(self.filename, 'r') as infile:
            text = infile.read()
        matches = self.FindMarkups(text)
        start = 0
        newtext = ""

        keydict = None
        for i in range(len(matches)):
            matchtext = matches[i].group(2)
            if matchtext.strip() == "":
                keydict = None
                continue

            keydict = self.FindKeyVals(matchtext, keydict=keydict)
            if keydict['group'] not in groups:
                groups.append(keydict['group'])
        return groups


    def WriteGroupsFile(self, groups, outdir, name):
        scalars = "ngroupnames = {0}{1}appname = '{2}'".format(len(groups), '\n', name)
        setup = ["setup", scalars]

        gstrs = []
        for i, group in enumerate(groups):
            gstrs.append("groupnames({0}) = {1}".format(i+1, group))
        gstrs = '\n'.join(gstrs)
        gsetup = ["helpers_list", gstrs]

        outstr = kittie_common.Namelist(setup, gsetup)
        kittie_common.NMLFile("kittie-setup", outdir, outstr)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help="sub-command help")
    parser.set_defaults(which='top')

    RepoParser = subparsers.add_parser("repo", help="Process code repository to determine its KITTIE-dependent files and group names")
    RepoParser.add_argument("directory", help="Code repository to look through for KITTIE markups")
    RepoParser.add_argument("outdir", help="Output groups namelist file")
    RepoParser.add_argument("-s", "--suffix", help="String to append to file names when replaced", type=str, default="-kittie")
    RepoParser.add_argument("-n", "--name", help="Name IDing the app", type=str, default=None)
    RepoParser.set_defaults(which='repo')

    FileParser = subparsers.add_parser("file", help="Process one source file and replace KITTIE markups with appropriate APIs")
    FileParser.add_argument("srcfile", help="Source file to read and make replacements")
    FileParser.add_argument("outfile", help="Output file name")
    FileParser.set_defaults(which='file')

    args = parser.parse_args()

    if args.which == "file":
        fparser = KittieParser(args.srcfile, args.outfile)
        fparser.FileReplacements()

    elif args.which == "repo":
        thisfile = os.path.realpath(__file__)
        out = subprocess.check_output(["grep", "-r", "\\!@kittie", args.directory, "--files-with-matches"])
        files = out.strip().split()
        groups = []

        for filename in files:
            filename = filename.decode("utf-8")
            outfile = "{0}{1}.F90".format(filename[:-4], args.suffix)

            if filename.endswith('.F90'):
                fparser = KittieParser(filename, outfile)
                groups = fparser.FindGroups(groups)
                fparser.FileReplacements()

        if args.name is None:
            args.name = os.path.basename(args.directory)

        fparser.WriteGroupsFile(groups, args.outdir, args.name)
