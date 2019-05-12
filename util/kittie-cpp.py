#!/usr/bin/env python

from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import os
import re
import copy
import subprocess
import yaml
import logging
import kittie_common


def GetArgList(text):
    bss = text.strip()
    argstart = bss.find('(') + 1
    argend = bss.rfind(')')
    astr = bss[argstart:argend]

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


def GetAdiosArgs(text, commanddict, names):
    alist = GetArgList(text)
    for i, name in enumerate(names):
        commanddict[name] = alist[i]
    return commanddict


def CommandKeyAdd(names, keydict, commanddict):
    for key in names:
        if (key in keydict) and (keydict[key] is not None):
            commanddict[key] = keydict[key]
    return commanddict


class BaseReplacer(object):

    def _EscapeSearch(self, text, shift):
        exp1 = "[ \t\r\f\v]*"
        search1 = re.compile(exp1)
        search2 = re.compile(self.continuation)

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

        if self.FunctionKey != "":
            startexpr = "{0}".format(self.FunctionKey)
        else:
            startexpr = "{0}".format(command)
        search = re.compile(startexpr)
        results = list(search.finditer(text))

        for i, result in enumerate(results):
            shift = 0

            if result is not None:
                open_index = result.start()

                if self.FunctionKey != "":
                    end_index = result.end()
                    newstr = text[end_index:]
                    shift += result.end() - result.start()
                    newstr, shift = self._EscapeSearch(newstr, shift)

                    startexp = "{0}".format(command)
                    search = re.compile(startexp)

                else:
                    newstr = text[result.start():]

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

                search = re.compile(self.paren)
                num = 0
                while True:
                    result = search.match(newstr)

                    if result is None:
                        #nstr = newstr.replace("&\n", "", 1)
                        nstr = newstr.replace(self.continuation, "", 1)
                        if nstr == newstr:
                            raise ValueError("Error in {0} function close".format(command))
                        else:
                            num += 1
                            newstr = nstr
                    else:
                        break

                shift += result.end() + num * self.clen
                end_index = open_index + shift
                found = True
                break

        if found:
            return (open_index, end_index)
        else:
            return (None, None)


    def EqualStart(self, text, start, cond=True):
        old = start
        while cond:
            if text[start-1] == "=":
                break
            if (text[start-1] == ";") or (start == 0):
                cond = False
            start -= 1

        if not cond:
            return old
        else:
            return start


    def FindEqual(self, text, start, kittie_command, commanddict, newargs, result=None, obj=False, pre=""):
        start = self.EqualStart(text, start, cond=obj)

        if result is not None:
            txt = "{0} = {1}(".format(commanddict[result], kittie_command)
        else:
            txt = "{0}{1}(".format(pre, kittie_command)

        for key in newargs:
            txt = "{0}{1}, ".format(txt, commanddict[key])
        txt = "{0})".format(txt.rstrip(', '))
        return txt


    def CommonNoOptions(self, commanddict, keydict, command, text, args, newargs, kittie_command, result=None, obj=False, pre="", single=False):
        start, stop = self.ParseCommand(command, text)
        if start is not None:
            commanddict = GetAdiosArgs(text[start:stop], commanddict, args)
            commanddict = CommandKeyAdd(newargs, keydict, commanddict)
            txt = self.FindEqual(text, start, kittie_command, commanddict, newargs, result=result, obj=obj, pre=pre)
            if not single:
                text = '{0}{1}{2}'.format(text[:start], txt, text[stop:])
            else:
                text = '{0}{1}'.format(text[:start], txt)
        return text, commanddict, start


    def __init__(self):
        self.FunctionKey = None
        self.continuation = None
        self.paren = None

        self.DeclareCommand   = None
        self.OpenCommand      = None
        self.CloseCommand     = None
        self.BeginStepCommand = None
        self.EndStepCommand   = None

        self.AddStep = False


def GetVar(between, start):
    ws = [' ', '\n', '\t', '\r', '\f', '\v']
    wordend = start - 1
    while between[wordend-1] in ws:
        wordend -= 1
    wordstart = wordend - 1
    while between[wordstart-1] not in (ws + [';', '{', '}']):
        wordstart -= 1
    return between[wordstart:wordend]


class CppReplacer(BaseReplacer):

    def __init__(self, AddStep=False):
        self.FunctionKey = ''
        self.continuation = "\n"
        self.clen = 1
        self.paren = "^\(.*\);"

        self.DeclareCommand   = 'DeclareIO'
        self.OpenCommand      = 'Open'
        self.CloseCommand     = 'Close'
        self.BeginStepCommand = 'BeginStep'
        self.EndStepCommand   = 'EndStep'

        self.AddStep = AddStep


    def OptionAdd(self, name, keydict, commanddict, argstr, first=False):
        if not first:
            if keydict[name] is not None:
                argstr = "{0}, {2}".format(argstr, name, keydict[name])
            elif name in commanddict:
                argstr = "{0}, {2}".format(argstr, name, commanddict[name])
        else:
            if keydict[name] is not None:
                argstr = "{0}{2}".format(argstr, name, keydict[name])
            elif name in commanddict:
                argstr = "{0}{2}".format(argstr, name, commanddict[name])

        return argstr


    def ReplaceInit(self, between, commanddict, keydict, single=False, indentation=""):
        if not single:
            raise ValueError("It doens't make sense to try to initialize Kittie without single line replacement")

        args = []
        if keydict["init"] is not None:
            args += [keydict["init"]]
        if keydict['comm'] is not None:
            args += [keydict['comm']]
        args += ['adios2::DebugON']

        between = "\n{1}kittie::initialize({2});".format(between, indentation, ', '.join(args))
        start = None
        stop = 0

        return between, commanddict, start, stop


    def ReplaceDeclareIO(self, between, commanddict, keydict, single=False):
        if keydict['io'] is not None:
            commanddict['io'] = keydict['io']
        command = "{0}".format(self.DeclareCommand)
        #command = "kittie_adios.{1}.{0}".format(self.DeclareCommand, keydict['group'])

        start, stop = self.ParseCommand(command, between)
        if start is not None:
            commanddict = GetAdiosArgs(between[start:stop], commanddict, ['group'])
            commanddict = CommandKeyAdd(['group'], keydict, commanddict)
            argstr = "kittie::declare_io({0});".format(keydict['group'])
            start = self.EqualStart(between, start)

            if not single:
                between = '{0} {1}{2}'.format(between[:start], argstr, between[stop:])
            else:
                between = '{0} {1}'.format(between[:start], argstr)

            if keydict['io'] is None:
                io = GetVar(between, start)
                commanddict['io'] = io

        return between, commanddict, start, stop


    def ReplaceOpen(self, between, commanddict, keydict, indentation="", single=False):
        if keydict['engine'] is not None:
            commanddict['engine'] = keydict['engine']
        command = "{1}.{0}".format(self.OpenCommand, commanddict['io'])

        start, stop = self.ParseCommand(command, between)
        if start is not None:
            try:
                commanddict = GetAdiosArgs(between[start:stop], commanddict, ['filename', 'open_mode', 'comm'])
            except:
                commanddict = GetAdiosArgs(between[start:stop], commanddict, ['filename', 'open_mode'])


            #argstr = "kittie::Couplers[{0}]->open({1}, {2}".format(keydict['group'], commanddict['filename'], commanddict['open_mode'])
            argstr = "kittie::open({0}, {1}, {2}".format(keydict['group'], commanddict['filename'], commanddict['open_mode'])
            if 'comm' in commanddict:
                argstr = "{0}, {1}".format(argstr, commanddict['comm'])
            argstr = "{0});".format(argstr)
            start = self.EqualStart(between, start)


            if keydict['engine'] is None:
                engine = GetVar(between, start)
                commanddict['engine'] = engine


            if self.AddStep:
                if commanddict['open_mode'] == "adios2::Mode::Read":
                    keydict["step"] = 0

                if keydict['step'] is None:
                    astr = "{2} = kittie::Couplers[{0}]->begin_step();".format(keydict['group'], keydict['step'], commanddict['engine'])
                else:
                    astr = "{2} = kittie::Couplers[{0}]->begin_step({1});".format(keydict['group'], keydict['step'], commanddict['engine'])

                argstr = '{0}\n{1}'.format(argstr, astr)


            if not single:
                between = '{0} {1}{2}'.format(between[:start], argstr, between[stop:])
            else:
                between = '{0} {1}'.format(between[:start], argstr)

        return between, commanddict, start, stop


    def ReplaceBeginStep(self, between, commanddict, keydict, indentation="", single=False):
        if 'engine' in commanddict:
            command = "{1}.{0}".format(self.BeginStepCommand, commanddict['engine'])
            start, stop = self.ParseCommand(command, between)
        else:
            start = None
            stop = None

        if start is not None:
            num = 2
            args = ['step_mode', 'timeout']
            while num > 0:
                try:
                    commanddict = GetAdiosArgs(between[start:stop], commanddict, args[0:num])
                    break
                except:
                    num -= 1

            start = self.EqualStart(between, start)
            """
            old = start
            start = self.EqualStart(between, start)
            if start != old:
                status = GetVar(between, start)
            """

            if keydict['step'] is None:
                argstr = " kittie::Couplers[{0}]->begin_step(".format(keydict['group'], keydict['step'])
                argstr = self.OptionAdd("timeout", keydict, commanddict, argstr, first=True)
            else:
                argstr = " kittie::Couplers[{0}]->begin_step({1}".format(keydict['group'], keydict['step'])
                argstr = self.OptionAdd("timeout", keydict, commanddict, argstr)

            estr = "{0} = kittie::Couplers[{1}]->engine;".format(commanddict['engine'], keydict['group'])
            txt = "{0}); {1}".format(argstr, estr)

            if not single:
                between = '{0}{1}{2}'.format(between[:start], txt, between[stop:])
            else:
                between = '{0}{1}'.format(between[:start], txt)

        return between, commanddict, start, stop


    def ReplaceEndStep(self, between, commanddict, keydict, single=False):
        if 'engine' in commanddict:
            command = "{1}.{0}".format(self.EndStepCommand, commanddict['engine'])
            start, stop = self.ParseCommand(command, between)
        else:
            start = None
            stop = None

        if start is not None:
            commanddict = GetAdiosArgs(between[start:stop], commanddict, [])
            argstr = "kittie::Couplers[{0}]->end_step();".format(keydict['group'])
            if not single:
                between = '{0}{1}{2}'.format(between[:start], argstr, between[stop:])
            else:
                between = '{0}{1}'.format(between[:start], argstr)
        return between, commanddict, start, stop


    def ReplaceClose(self, between, commanddict, keydict, single=False):
        if 'engine' in commanddict:
            command = "{1}.{0}".format(self.CloseCommand, commanddict['engine'])
            start, stop = self.ParseCommand(command, between)
        else:
            start = None
            stop = None

        if start is not None:
            commanddict = GetAdiosArgs(between[start:stop], commanddict, [])
            argstr = ""
            if self.AddStep:
                argstr = "kittie::Couplers[{0}]->end_step();\n".format(keydict['group'])
            argstr = "{0}kittie::Couplers[{1}]->close();".format(argstr, keydict['group'])
            if not single:
                between = '{0}{1}{2}'.format(between[:start], argstr, between[stop:])
            else:
                between = '{0}{1}'.format(between[:start], argstr)
        return between, commanddict, start, stop



class FortranReplacer(BaseReplacer):

    def __init__(self, AddStep=False):
        self.FunctionKey = 'call'
        self.continuation = "&\n"
        self.clen = 2
        self.paren = "^\(.*(?<!/)\)"

        self.DeclareCommand   = 'adios2_declare_io'
        self.OpenCommand      = 'adios2_open'
        self.CloseCommand     = 'adios2_close'
        self.BeginStepCommand = 'adios2_begin_step'
        self.EndStepCommand   = 'adios2_end_step'

        self.AddStep = AddStep


    def OptionAdd(self, name, keydict, commanddict, argstr):
        if keydict[name] is not None:
            argstr = "{0}, {1}={2}".format(argstr, name, keydict[name])
        elif name in commanddict:
            argstr = "{0}, {1}={2}".format(argstr, name, commanddict[name])
        return argstr



    def ReplaceOpen(self, between, commanddict, keydict, indentation="", single=False):
        start, stop = self.ParseCommand(self.OpenCommand, between)
        if start is not None:
            commanddict = GetAdiosArgs(between[start:stop], commanddict, ['engine', 'io', 'filename', 'open_mode', 'comm', 'ierr'])

            if self.AddStep:
                if commanddict['open_mode'] == "adios2_mode_read":
                    keydict["step"] = 0

                argstr = "common_helper, {0}, {1}, {2}, {3}".format(commanddict['filename'], commanddict['group'], commanddict['open_mode'], commanddict['comm'])
                for name in ["step", "ierr", "dir", "timefile"]:
                    argstr = self.OptionAdd(name, keydict, commanddict, argstr)
                txt = "call kittie_couple_start({0})".format(argstr)
                engine = "{0} = common_helper%engine".format(commanddict['engine'])
                space = "\n"

                if not single:
                    between = '{0}{1}{3}{4}{2}'.format(between[:start], txt, between[stop:], space, engine)
                else:
                    between = '{0}{1}{3}{4}'.format(between[:start], txt, between[stop:], space, engine)

            else:
                if not single:
                    between = '{0}{1}{2}'.format(between[:start], "", between[stop:])
                else:
                    between = '{0}{1}'.format(between[:start], "")

        return between, commanddict, start, stop


    def ReplaceClose(self, between, commanddict, keydict, single=False):
        start, stop = self.ParseCommand(self.CloseCommand, between)
        if start is not None:
            commanddict = GetAdiosArgs(between[start:stop], commanddict, ['engine', 'ierr'])
            if self.AddStep:
                between, commanddict, start = self.CommonNoOptions(commanddict, keydict, self.CloseCommand, between, ['engine', 'ierr'], ['helper', 'ierr'], "kittie_couple_end_step", pre="call ", single=single)
            else:
                if not single:
                    between = '{0}{1}{2}'.format(between[:start], "", between[stop:])
                else:
                    between = '{0}{1}'.format(between[:start], "")

        return between, commanddict, start, stop


    def ReplaceDeclareIO(self, between, commanddict, keydict, single=False):
        #between, commanddict, start = self.CommonNoOptions(commanddict, keydict, self.DeclareCommand, between, ['io', 'adios', 'group', 'ierr'], ['group', 'ierr'], "kittie_declare_io")
        between, commanddict, start = self.CommonNoOptions(commanddict, keydict, self.DeclareCommand, between, ['io', 'adios', 'group', 'ierr'], ['group', 'ierr'], "KittieDeclareIO", result='io', single=single)
        return between, commanddict, start, stop


    def ReplaceEndStep(self, between, commanddict, keydict, single=False):
        between, commanddict, start = self.CommonNoOptions(commanddict, keydict, self.EndStepCommand, between, ['engine', 'ierr'], ['helper', 'ierr'], "kittie_couple_end_step", pre="call ", single=single)
        return between, commanddict, start, stop


    def ReplaceBeginStep(self, between, commanddict, keydict, indentation="", single=False):
        start, stop = self.ParseCommand(self.BeginStepCommand, between)

        if start is not None:

            try:
                commanddict = GetAdiosArgs(between[start:stop], commanddict, ['engine', 'step_mode', 'timeout', 'status', 'ierr'])
            except:
                commanddict = GetAdiosArgs(between[start:stop], commanddict, ['engine', 'step_mode', 'ierr'])

            argstr = "common_helper, {0}, {1}, {2}, {3}".format(commanddict['filename'], keydict['group'], commanddict['open_mode'], commanddict['comm'])
            for name in ["step", "ierr", "dir", "timefile"]:
                argstr = self.OptionAdd(name, keydict, commanddict, argstr)
            txt = "call kittie_couple_start({0})".format(argstr)
            engine = "{0} = common_helper%engine".format(commanddict['engine'])
            space = "\n"

            between = '{0}{1}{3}{4}{2}'.format(between[:start], txt, between[stop:], space, engine)

        return between, commanddict, start, stop



class KittieParser(object):

    @property
    def InitStr(self):
        comment = {
            'python': '#',
            'fortran': '!',
            'c++': '//'
        }
        return "{0}@kittie".format(comment[self.filetype])


    def DetectFiletype(self):
        self.filetype = None
        tests = [
            ('.py',  'python'),
            ('.F90', 'fortran'),
            ('.f90', 'fortran'),
            ('.cpp', 'c++'),
            ('.c++', 'c++')
        ]

        for test in tests:
            if self.filename.endswith(test[0]):
                self.filetype = test[1]
                break

        if self.filetype is None:
            raise ValueError("Recognized filetype was not detected for {0}".format(filename))


    def FindMarkups(self, text):
        expr = "({0})(.*)$".format(self.InitStr)
        comp = re.compile(expr, re.MULTILINE)
        matches = list(comp.finditer(text))
        return matches


    def FindKeyVals(self, text, keydict=None, skip=[]):
        if keydict is None:
            keydict = copy.copy(self.keydict)
        kvs = text.split(",")
        for kv in kvs:
            k = kv.strip()
            key, value = k.split("=")
            key = key.strip()
            value = value.strip()

            if value.endswith(';'):
                value = value[:-1]

            if (key == "init"):
                if value == "None":
                    keydict["init"] = None
                else:
                    keydict["init"] = value

            if (key == "group"):
                v = value
                if (v[0] == '"') or (v[0] == "'"):
                    v = v[1:-1]
                if v in skip:
                    keydict = None
                    return keydict
            if (key == "step") and (value == "None"):
                self.AddStep = True
                continue
            if key in self.keywords:
                keydict[key] = value

        if (keydict["group"] is None) and (text.find("init") == -1):
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


    def Replacer(self, func, between, commanddict, keydict, indentation=None, single=False, stop=None):
        if stop is not None:
            return between, commanddict, stop

        start = True
        while start is not None:
            oldbetween = between
            if indentation is not None:
                between, commanddict, start, stop = func(between, commanddict, keydict, indentation=indentation, single=single)
            else:
                between, commanddict, start, stop = func(between, commanddict, keydict, single=single)

            if single and (oldbetween != between):
                break

        """
        for name in [self.DefineCommand, self.InquireCommand, self.GetCommand, self.PutCommand]:
            between = between.replace("@{0}".format(name), name)
        """

        return between, commanddict, stop



    def FileReplacements(self, skip):
        with open(self.filename, 'r') as infile:
            text = infile.read()
        matches = self.FindMarkups(text)
        start = 0
        newtext = ""

        cdict = {}
        keydict = None
        for i in range(len(matches)):
            self.AddStep = False
            matchtext = matches[i].group(2)
            if matchtext.strip() == "":
                keydict = None
                continue

            keydict = self.FindKeyVals(matchtext, keydict=keydict, skip=skip)

            if keydict is None:
                continue

            group = keydict['group']
            if group not in cdict.keys():
                cdict[group] = {'helper': 'common_helper'}


            if not matches[i].group(2).strip().endswith(';'):
                between, bstart, bend = self.FindCode(matches, i, text)
                indentation = self.GetIndentation(between)
                single = False
            else:
                bstart = matches[i].end()
                between = text[bstart:]
                indentation = self.GetIndentation(between)
                single = True


            if self.filetype == 'fortran':
                replacer = FortranReplacer(AddStep=self.AddStep)
            elif self.filetype == 'c++':
                replacer = CppReplacer(AddStep=self.AddStep)

            end = None
            if "init" in keydict:
                #between = text[matches[i].start():]
                #between, cdict[group], end = self.Replacer(replacer.ReplaceInit, between, cdict[group], keydict, single=single, stop=end)
                between, cdict[group], end = self.Replacer(replacer.ReplaceInit, between, cdict[group], keydict, single=single, stop=end, indentation=indentation)
                del keydict["init"]
            between, cdict[group], end = self.Replacer(replacer.ReplaceDeclareIO, between, cdict[group], keydict, single=single, stop=end)
            between, cdict[group], end = self.Replacer(replacer.ReplaceOpen,      between, cdict[group], keydict, single=single, stop=end)
            between, cdict[group], end = self.Replacer(replacer.ReplaceBeginStep, between, cdict[group], keydict, single=single, stop=end)
            between, cdict[group], end = self.Replacer(replacer.ReplaceEndStep,   between, cdict[group], keydict, single=single, stop=end)
            between, cdict[group], end = self.Replacer(replacer.ReplaceClose,     between, cdict[group], keydict, single=single, stop=end)

            if self.filetype == 'fortran':
                between = "\n{0}call kittie_get_helper({1}, common_helper){2}".format(indentation, group, between)

            newtext = "{0}{1}{2}".format(newtext, text[start:bstart], between)

            if single:
                start = bstart + end
            else:
                start = bend

        newtext = "{0}{1}".format(newtext, text[start:])
        with open(self.outfilename, 'w') as out:
            out.write(newtext)


    def FindGroups(self, groups, skip):
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

            keydict = self.FindKeyVals(matchtext, keydict=keydict, skip=skip)

            if (keydict is not None) and (keydict['group'] not in groups):
                if "init" not in keydict:
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


        gdict = {'n': len(groups), 'appname': name, 'groups': []}
        for i, group in enumerate(groups):
            gdict['groups'].append(group)
        outstr = yaml.dump(gdict, default_flow_style=False)
        outpath = os.path.join(outdir, ".kittie-setup.yaml")
        with open(outpath, "w") as outfile:
            outfile.write(outstr)


    def __init__(self, filename, outfilename):
        self.AddStep = False
        self.filename = os.path.realpath(filename)
        self.outfilename = os.path.realpath(outfilename)
        self.DetectFiletype()

        self.keydict = {}
        self.keywords = ["step", "dir", "timefile", "group", "filename", "ierr", "varname", "varid", "io", "engine", "timeout", "comm"]
        for key in self.keywords:
            self.keydict[key] = None


def WriteGroupsFile(groups, outdir, name):
    scalars = "ngroupnames = {0}{1}appname = '{2}'".format(len(groups), '\n', name)
    setup = ["setup", scalars]

    gstrs = []
    for i, group in enumerate(groups):
        gstrs.append("groupnames({0}) = {1}".format(i+1, group))
    gstrs = '\n'.join(gstrs)
    gsetup = ["helpers_list", gstrs]

    outstr = kittie_common.Namelist(setup, gsetup)
    kittie_common.NMLFile("kittie-setup", outdir, outstr)


    gdict = {'n': len(groups), 'appname': name, 'groups': []}
    for i, group in enumerate(groups):
        gdict['groups'].append(group)
    outstr = yaml.dump(gdict, default_flow_style=False)
    outpath = os.path.join(outdir, ".kittie-setup.yaml")
    with open(outpath, "w") as outfile:
        outfile.write(outstr)


def GetArgumentList(text, end=False):
    #bss = text.strip()
    argstart = text.find('(') + 1
    astr = text[argstart:]

    alist = []
    opened = 0
    start = 0
    for i in range(len(astr)):
        if astr[i] == '(':
            opened += 1
        elif (astr[i] == ',') and (opened == 0):
            alist += [astr[start:i].strip()]
            start = i + 1
        elif astr[i] == ')':
            if (opened == 0):
                alist += [astr[start:i].strip()]
                break
            opened -= 1

    if end:
        return alist, argstart+i+1
    else:
        return alist


def EqualStart(text, start, cond=True):
    old = start
    while cond:
        if text[start-1] == "=":
            break
        if (text[start-1] == ";") or (start == 0):
            cond = False
        start -= 1

    if not cond:
        return old
    else:
        return start

def SplitOn(txt, splitkey):
    outarr = []
    for entry in txt.split(splitkey):
        entry = entry.strip()
        if entry == "":
            continue
        outarr += [entry]
    return outarr


def MatchPattern(pattern, fmt, InnerText):
    if len(fmt) > 0:
        Pattern = pattern.format(*fmt)
    else:
        Pattern = pattern
    Comp = re.compile(Pattern)
    match = Comp.search(InnerText)
    return match


class BlockFiles(object):
    """ Class to parse the blocks between @effis-begin and @effis-end """

    '''
    def NameKeysSearch(self, LookForKey, MatchTo, ReturnKey):
        """ Look if something is in the current @effis-begin map, and if it is return what it's mapped to """

        newname = None
        keys = None
        for i, dictionary in enumerate(self.TmpMap):
            if (LookForKey in dictionary) and (MatchTo == dictionary[LookForKey]):
                newname = dictionary[ReturnKey]
                keys = dictionary['keys']
                break
        return newname, keys


    def EngOpenParse(self, Inner, io=None, name=None, out=None, UpdateText=None, pos=None):
        if out is not None:
            name = out['name']
            io = out['io']

        engine = None
        OpenPattern = self.OpenPattern(io)
        OpenComp = re.compile(OpenPattern)
        match = OpenComp.search(Inner)
        if match is not None:
            OpenArgs, OpenArgsStr, ParenClose = self.GetOpenArgumentList(name, Inner[match.end():])
            if out is not None:
                out['engine'] = self.GetEngObj(Inner, match.start(), OpenArgs)
            else:
                engine = self.GetEngObj(Inner, match.start(), OpenArgs)

            if (out is not None) and (name is not None):
                UpdateText += Inner[pos:match.start()] + self.OpenText(name, OpenArgsStr, out['engine'], out['keys'])
                pos = match.end() + ParenClose

        if out is None:
            return engine
        else:
            return out, UpdateText, pos


    def ParseDeclareIOs(self, InnerText, IOComp):
        """ Make any necessary replacements of DeclareIO statements """

        NewInner = ""
        InnerPos = 0
        Out = []
        IOMatches = list(IOComp.finditer(InnerText))

        for j in range(len(IOMatches)):

            try:
                # Get the arguement of the DeclareIO statement
                InIoName, IOArgs, ParenClose = self.GetIoArgumentList(InnerText[IOMatches[j].end():])
            except:
                # Dont try to do anything if the aruments don't make sense
                self.Raise("Something is wrong with the {0} statement in file {1} beginning at position {2}".format(self.DeclareAdios, self.TmpFilename, self.TmpBegin + IOMatches[j].start()))

            # Find the object on the left side of =
            EqualIndex = EqualStart(InnerText, IOMatches[j].start())
            io = self.GetIoObj(InnerText, EqualIndex, IOArgs)
            engine = self.EngOpenParse(InnerText, io=io, name=newname)

            newname, keys = self.NameKeysSearch('OldName', InIoName, 'NewName')
            if newname is None:
                newname, keys = self.NameKeysSearch('IOobj', io, 'IOName')
                if newname is None:
                    newname, keys = self.NameKeySearch('EngineObj', engine, 'EngineName')
            Out += [{'name': newname, 'obj': io, 'engine': engine, 'keys': keys}]

            if newname is None:
                # Inform us if there are DeclareIOs in the code block that we didn't give any mappings for. Not necessarily an error, but could be helpful info to have
                self.logger.warning("{0} I/O declared at position {1} in {2} was not remapped in {3} definitions beginning at position {4}".format(InIoName, self.TmpBegin + IOMatches[j].start(), self.TmpFilename, self.begin, self.TmpBegin))

            # Update the text, if it matches something we set in the @effis line
            if newname is not None:
                NewInner += InnerText[InnerPos:EqualIndex] + self.DeclareText(IOArgs, newname)
                InnerPos = IOMatches[j].end() + ParenClose

        NewInner += InnerText[InnerPos:]

        # See if all the DeclareIO mappings given in the @effis line were actually used
        for i, dictionary in enumerate(self.TmpMap):
            if ('OldName' in dictionary):
                found = False
                for entry in Out:
                    if entry['name'] == dictionary['NewName']:
                        found = True
                        break
                if not found:
                    self.logger.warning("I/O group mapping {0}->{1} was not matched to an occurence of {0} in the enclosed code block between positions {2}...{3}".format(dictionary['OldName'], dictionary['NewName'], self.TmpBegin, self.TmpEnd))

        return NewInner, Out


    def ParseOpens(self, Out, NewInner):
        """ Make any necessary replacements of Open statements """

        NewerInner = ""
        InnerPos = 0
        for j in range(len(Out)):
            Out[j], NewerInner, InnerPos = self.EngOpenParse(NewInner, out=Out[j], UpdateText=NewerInner, pos=InnerPos)
        NewerInner += NewInner[InnerPos:]
        return NewerInner


    def ParseBegins(self, Out, NewInner):
        NewerInner = ""
        InnerPos = 0
        for j in range(len(Out)):
            BeginPattern = self.BeginPattern(Out[j]['engine'])
            BeginComp = re.compile(BeginPattern)
            match = BeginComp.search(NewInner)
            if match is not None:
                BeginArgs, BeginArgsStr, ParenClose = self.GetBeginArgumentList(Out[j]['name'], NewInner[match.end(3):])
                status = self.GetStatusObj(NewInner, match.start(1), BeginArgs)

                if Out[j]['name'] is not None:
                    NewerInner += NewInner[InnerPos:match.start(3)] + self.BeginText(Out[j]['name'], BeginArgsStr)
                    InnerPos = match.end(3) + ParenClose

        NewerInner += NewInner[InnerPos:]

        return NewerInner

    '''

    def __init__(self):
        # Use the same logger for the whole use of this program
        self.logger = logging.getLogger(__file__)

        self.begin = "@effis-begin"
        self.end   = "@effis-end"
        self.files = []

        self.init = "@effis-init"
        self.initallowed = ["xml", "comm"]


    def Raise(self, msg, code=None):
        if code is not None:
            msg += ":\n" + code
        raise ValueError(msg)


    def ParseEffisLine(self, InnerText):
        """ Go through the @effis-begin line, and translate the comment to a configuration dictionary for that block of code """

        # These are the recognized additional settings
        keys = ["step"]

        """ There needs to be a way to tell the different types of objects aparts.
            - I've chosen to use different map symbols indicative of the "number of ADIOS statements" away they are from the I/O name
            - This could be done with different keys (i.e. [io: IOobj->"Name"] vs. [name: "old"->"Name"]) """
        patterns = ["--->", "-->", "->", "="]

        self.TmpMap = []
        EndIndex = InnerText.find("\n")
        line = InnerText[:EndIndex].strip()

        # Parse the mappings
        for group in SplitOn(line, ';'):
            TmpMap = {'keys': {}}
            for definition in SplitOn(group, ','):
                found = False
                DeclareFound = False
                IOFound = False
                EngineFound = False

                for pattern in patterns:
                    if definition.find(pattern) != -1:
                        before, after = SplitOn(definition, pattern)
                        found = True
                        break
                if not found:
                    self.Raise("Something unrecognized happened in file {0} beginning at position {1} in the {2} statement".format(self.TmpFilename, self.TmpBegin, self.begin), definition)

                if (after not in self.groupnames) and (pattern != "="):
                    self.groupnames += [after]

                """ All the Raises are to make sure the user doesn't over/contradictorily prescribe what is supposed to happen
                    - For example, if you tried to remap the input IO name and IO objects to different destination names, that doesn't make sense
                    - Users are only allowed to give the map from one of a Name, IO object, or Engine object
                    - I allow repeats of explictly the same thing, but am waivering on if I should """

                if pattern == "->":
                    if IOFound:
                        self.Raise("File {0}, position {1}: Mapping both the Name and IO object isn't allowed for a parse section".format(self.TmpFilename, self.TmpBegin), group)
                    if EngineFound:
                        self.Raise("File {0}, position {1}: Mapping both the Name and Engine object isn't allowed for a parse section".format(self.TmpFilename, self.TmpBegin), group)
                    elif DeclareFound and (TmpMap['OldName'] != before):
                        self.Raise("File {0}, position {1}: Can't map two different source Names in same section of the parse. Separate Name sections with a ';'".format(self.TmpFilename, self.TmpBegin), group)
                    elif DeclareFound and (TmpMap['NewName'] != after):
                        self.Raise("File {0}, position {1}: Can't map two different destination Names in same section of the parse. Separate Name sections with a ';'".format(self.TmpFilename, self.TmpBegin), group)
                    DeclareFound = True
                    TmpMap['OldName'] = before
                    TmpMap['NewName'] = after

                elif pattern == "-->":
                    if DeclareFound:
                        self.Raise("File {0}, position {1}: Mapping both the Name and IO object isn't allowed for a parse section".format(self.TmpFilename, self.TmpBegin), group)
                    if EngineFound:
                        self.Raise("File {0}, position {1}: Mapping both the IO and Engine object isn't allowed for a parse section".format(self.TmpFilename, self.TmpBegin), group)
                    if IOFound and (TmpMap["IoName"] != after):
                        self.Raise("File {0}, position {1}: Can't map two different destination IOs in same section of the parse. Separate Name sections with a ';'".format(self.TmpFilename, self.TmpBegin), group)
                    if IOFound and (TmpMap['IOobj'] != after):
                        self.Raise("File {0}, position {1}: Can't map two different source IOs in same section of the parse. Separate Name sections with a ';'".format(self.TmpFilename, self.TmpBegin), group)
                    IOFound = True
                    TmpMap['IOobj']  = before
                    TmpMap['IOName'] = after

                elif pattern == "--->":
                    if DeclareFound:
                        self.Raise("File {0}, position {1}: Mapping both the Name and Engine object isn't allowed for a parse section".format(self.TmpFilename, self.TmpBegin), group)
                    if IOFound:
                        self.Raise("File {0}, position {1}: Mapping both the IO and Engine object isn't allowed for a parse section".format(self.TmpFilename, self.TmpBegin), group)
                    if EngineFound and (TmpMap["EngineName"] != after):
                        self.Raise("File {0}, position {1}: Can't map two different destination IOs in same section of the parse. Separate Name sections with a ';'".format(self.TmpFilename, self.TmpBegin), group)
                    if EngineFound and (TmpMap['EngineObj'] != after):
                        self.Raise("File {0}, position {1}: Can't map two different source IOs in same section of the parse. Separate Name sections with a ';'".format(self.TmpFilename, self.TmpBegin), group)
                    EngineFound = True
                    TmpMap['EngineObj']  = before
                    TmpMap['EngineName'] = after

                else:
                    if before not in keys:
                        self.Raise("Unknown key found in file {0} beginning at position {1} in the {2} statement".format(self.TmpFilename, self.TmpBegin, self.begin, before), before)
                    TmpMap['keys'][before] = after

            if ('OldName' not in TmpMap) and ('IOName' not in TmpMap) and ('EngineName' not in TmpMap):
                self.Raise("Unqualified grouping in file {0} beginning at position {1} in the {2} statement".format(self.TmpFilename, self.TmpBegin, self.begin), group)

            self.TmpMap += [TmpMap]

        return InnerText[EndIndex+1:], self.TmpBegin+EndIndex+1


    def ArgsObj(self, InnerText, match, mpos=1, fpos=0, vpos=None, remove=[], size=None):
        ArgsStr = match.group(mpos)
        Args = SplitOn(ArgsStr, ',')
        TmpArgs = None

        if (len(remove) > 0) and (len(Args) == size):
            TmpArgs = []
            for i, arg in enumerate(Args):
                if i not in remove:
                    TmpArgs += [arg]
            ArgsStr = ", ".join(TmpArgs)

        if self.language == "fortran":
            if len(Args) > fpos:
                val = Args[fpos]
            else:
                val = None
        elif self.language == "c++":
            if InnerText[match.start()] == "=":
                val = GetVar(InnerText, match.start())
            elif vpos is not None:
                val = match.group(vpos)
            else:
                val = None

        return val, ArgsStr, Args


    def ForwardReplaceDeclare(self, match, TmpMap, InternalText, NewInner, UpdatePos):
        io, IOArgsStr, IOArgs = self.ArgsObj(InternalText, match, fpos=0)
        NewInner += InternalText[UpdatePos:match.start()] + self.DeclareText(IOArgs, TmpMap['NewName'])
        UpdatePos = match.end()
        return io, NewInner, UpdatePos

    def ForwardReplaceOpen(self, match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='NewName'):
        engine, OpenArgsStr, OpenArgs = self.ArgsObj(InternalText, match, fpos=0)
        NewInner += InternalText[UpdatePos:match.start()] + self.OpenText(TmpMap[NameKey], OpenArgsStr, engine, TmpMap['keys'])
        UpdatePos = match.end()
        return engine, NewInner, UpdatePos

    def ForwardReplaceBegin(self, match, TmpMap, InternalText, NewInner, UpdatePos, engine, NameKey='NewName'):
        status, BeginArgStr, BeginArgs = self.ArgsObj(InternalText, match, fpos=3, mpos=3, remove=[0], size=2)
        if InternalText[match.start():].strip()[0] == "=":
            NewInner += InternalText[UpdatePos:match.start()] + self.BeginText(TmpMap[NameKey], BeginArgStr, TmpMap['keys'], engine, equal=True)
        else:
            NewInner += InternalText[UpdatePos:match.end(2)] + self.BeginText(TmpMap[NameKey], BeginArgStr, TmpMap['keys'], engine, equal=False)
        UpdatePos = match.end()
        return status, NewInner, UpdatePos

    def ForwardReplaceEnd(self, match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='NewName'):
        nothing, EndArgStr, EndArgs = self.ArgsObj(InternalText, match)
        NewInner += InternalText[UpdatePos:match.start()] + self.EndText(TmpMap[NameKey], EndArgStr)
        UpdatePos = match.end()
        return nothing, NewInner, UpdatePos

    def ForwardReplaceClose(self, match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='NewName'):
        nothing, EndArgStr, EndArgs = self.ArgsObj(InternalText, match)
        NewInner += InternalText[UpdatePos:match.start()] + self.CloseText(TmpMap[NameKey], EndArgStr, TmpMap['keys'])
        UpdatePos = match.end()
        return nothing, NewInner, UpdatePos


    def ReverseReplaceDeclare(self, match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='IOName', IOobj=None):
        name, IOArgsStr, IOArgs = self.ArgsObj(InternalText, match, fpos=2)
        NewInner += InternalText[UpdatePos:match.start()] + self.DeclareText(IOArgs, TmpMap[NameKey], IOobj=IOobj)
        UpdatePos = match.end()
        return name, NewInner, UpdatePos

    def ReverseReplaceOpen(self, match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='NewName'):
        io, OpenArgsStr, OpenArgs = self.ArgsObj(InternalText, match, fpos=2, vpos=1, mpos=2)
        NewInner += InternalText[UpdatePos:match.start()] + self.OpenText(TmpMap[NameKey], OpenArgsStr, TmpMap['EngineObj'], TmpMap['keys'], EngineObj=TmpMap['EngineObj'])
        UpdatePos = match.end()
        return io, NewInner, UpdatePos


    def ReplaceByName(self, InnerText, ignore=[]):
        """ Make any necessary replacements implied by Name mappings """

        InternalText = InnerText

        for TmpMap in self.TmpMap:
            if ('OldName' not in TmpMap) or ('NewName' in ignore):
                continue
            UpdatePos = 0
            NewInner = ""

            match = MatchPattern(self.FindDeclareIOPattern, [TmpMap['OldName']], InternalText)
            if match is not None:
                io, NewInner, UpdatePos = self.ForwardReplaceDeclare(match, TmpMap, InternalText, NewInner, UpdatePos)
                match = MatchPattern(self.FindOpenPattern, [io], InternalText)
                if match is not None:
                    engine, NewInner, UpdatePos = self.ForwardReplaceOpen(match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='NewName')

                    match = MatchPattern(self.FindBeginPattern(engine), [], InternalText)
                    if match is not None:
                        status, NewInner, UpdatePos = self.ForwardReplaceBegin(match, TmpMap, InternalText, NewInner, UpdatePos, engine, NameKey='NewName')

                    match = MatchPattern(self.FindEndPattern, [engine], InternalText)
                    if match is not None:
                        nothing, NewInner, UpdatePos = self.ForwardReplaceEnd(match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='NewName')

                    match = MatchPattern(self.FindClosePattern, [engine], InternalText)
                    if match is not None:
                        nothing, NewInner, UpdatePos = self.ForwardReplaceClose(match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='NewName')

            NewInner += InternalText[UpdatePos:]
            InternalText = NewInner
        return InternalText


    def ReplaceByIO(self, InnerText, ignore=[]):
        """ Make any necessary replacements implied by IO mappings """

        InternalText = InnerText

        for TmpMap in self.TmpMap:
            if ('IOobj' not in TmpMap) or ('IOName' in ignore):
                continue
            UpdatePos = 0
            NewInner = ""

            match = MatchPattern(self.FindOpenPattern, [TmpMap['IOobj']], InternalText)
            if match is not None:
                engine, NewInner, UpdatePos = self.ForwardReplaceOpen(match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='IOName')

                match = MatchPattern(self.FindBeginPattern(engine), [], InternalText)
                if match is not None:
                    status, NewInner, UpdatePos = self.ForwardReplaceBegin(match, TmpMap, InternalText, NewInner, UpdatePos, engine, NameKey='IOName')

                match = MatchPattern(self.FindEndPattern, [engine], InternalText)
                if match is not None:
                    nothing, NewInner, UpdatePos = self.ForwardReplaceEnd(match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='IOName')

                match = MatchPattern(self.FindClosePattern, [engine], InternalText)
                if match is not None:
                    nothing, NewInner, UpdatePos = self.ForwardReplaceClose(match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='IOName')

                # Need to go back to the to look for the DeclareIO
                NewInner += InternalText[UpdatePos:]
                InternalText = NewInner
                UpdatePos = 0
                NewInner = ""
                match = MatchPattern(self.FindDeclareIOPatternByIO, [TmpMap['IOobj']], InternalText)
                if match is not None:
                    name, NewInner, UpdatePos = self.ReverseReplaceDeclare(match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='IOName', IOobj=TmpMap['IOobj'])

            NewInner += InternalText[UpdatePos:]
            InternalText = NewInner

        return InternalText


    def ReplaceByEngine(self, InnerText, ignore=[]):
        """ Make any necessary replacements implied by Engine mappings """

        InternalText = InnerText

        for TmpMap in self.TmpMap:
            if ('EngineObj' not in TmpMap) or ('EngineName' in ignore):
                continue
            UpdatePos = 0
            NewInner = ""

            match = MatchPattern(self.FindBeginPattern(TmpMap['EngineObj']), [], InternalText)
            if match is not None:
                status, NewInner, UpdatePos = self.ForwardReplaceBegin(match, TmpMap, InternalText, NewInner, UpdatePos, TmpMap['EngineObj'], NameKey='EngineName')

            match = MatchPattern(self.FindEndPattern, [TmpMap['EngineObj']], InternalText)
            if match is not None:
                nothing, NewInner, UpdatePos = self.ForwardReplaceEnd(match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='EngineName')

            match = MatchPattern(self.FindClosePattern, [TmpMap['EngineObj']], InternalText)
            if match is not None:
                nothing, NewInner, UpdatePos = self.ForwardReplaceClose(match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='EngineName')

            # Need to go back to the to look for the Open
            NewInner += InternalText[UpdatePos:]
            InternalText = NewInner
            UpdatePos = 0
            NewInner = ""
            match = MatchPattern(self.FindOpenPatternByEngine, [TmpMap['EngineObj']], InternalText)
            if match is not None:
                io, NewInner, UpdatePos = self.ReverseReplaceOpen(match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='EngineName')

                # Need to go back to the to look for the DeclareIO
                NewInner += InternalText[UpdatePos:]
                InternalText = NewInner
                UpdatePos = 0
                NewInner = ""
                match = MatchPattern(self.FindDeclareIOPatternByIO, [io], InternalText)
                if match is not None:
                    name, NewInner, UpdatePos = self.ReverseReplaceDeclare(match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='EngineName', IOobj=io)

            NewInner += InternalText[UpdatePos:]
            InternalText = NewInner

        return InternalText


    def AddInit(self, InitComp, FileText):
        InitMatch = InitComp.search(FileText)
        OutText = FileText

        if InitMatch is not None:
            InnerText = FileText[InitMatch.end():]
            EndIndex = InnerText.find("\n")
            line = InnerText[:EndIndex].strip()

            dictionary = {}
            for kv in SplitOn(line, ','):
                key, val = SplitOn(kv, '=')
                if key not in self.initallowed:
                    self.Raise("Unknown key found in file {0} beginning at position {1} in the {2} statement".format(self.TmpFilename, InitMatch.start(), self.init), key)
                dictionary[key] = val

            OutText = FileText[:InitMatch.start()] + self.InitText(dictionary) + FileText[(InitMatch.end()+EndIndex):]
        return OutText


    def AddHeader(self, FileText):
        for expr in self.HeadExpr:
            FileText = FileText.replace(expr, "{0}\n{1}".format(expr, self.Header))
        return FileText


    ### These are the functions that get called by __main__ ###

    def GrepFor(self, find, filesarr):
        try:
            cmdout = subprocess.check_output(["grep", "-r", "{0}{1}".format(self.GrepComment, find), self.TopDir, "--files-with-matches"])
        except:
            return filesarr

        files = cmdout.strip().split()
        for filename in files:
            # Needing the decode has something to do with getting the text from the commandline
            filename = filename.decode("utf-8")
            for ext in self.extensions:
                if (filename.endswith(ext)) and (filename not in filesarr):
                    filesarr += [filename]
                    break
        return filesarr


    def FindFiles(self, directory):
        """ Use grep to first pick out the relevant files. (Using grep is simpler than manually opening everyting in Python) """

        self.TopDir = directory
        self.files = self.GrepFor(self.begin, self.files)
        self.files = self.GrepFor(self.init,  self.files)


    def MakeReplacements(self, outdir, groupnames, mimic=False, ignore=[], suffix="-kittie", new=False):
        """ Go through the identified files, and replace ADIOS-2 statements with slightly updated ones to support Effis """

        InitExpr  = "{0}{1}".format(self.ReComment, self.init)
        StartExpr = "{0}{1}".format(self.ReComment, self.begin)
        EndExpr   = "{0}{1}".format(self.ReComment, self.end)
        StartComp = re.compile(StartExpr, re.MULTILINE)
        EndComp   = re.compile(EndExpr, re.MULTILINE)
        IOComp    = re.compile(self.DeclareAdios)
        InitComp  = re.compile(InitExpr, re.MULTILINE)

        self.groupnames = []
        for filename in self.files:
            UpdatedPos = 0
            UpdatedText = ""
            self.TmpFilename = filename

            with open(self.TmpFilename, 'r') as infile:
                FileText = infile.read()

            # Add header
            FileText = self.AddHeader(FileText)

            # Look for init
            FileText = self.AddInit(InitComp, FileText)


            # Get the bounds of the replacement blocks
            StartMatches = list(StartComp.finditer(FileText))
            EndMatches   = list(EndComp.finditer(FileText))

            # I don't know what to try to do if the number of starts and ends don't match
            if len(StartMatches) != len(EndMatches):
                self.Raise("{0}: Something isn't begun/ended properly. Found {1} {2}s and {3} {4}s".format(sef.TmpFilename, len(StartMatches), self.begin, len(EndMatches), self.end))

            # Find and parse all the DeclareIOs, Opens, etc. matching to any mapping defintions @effis-begin header pragma
            for i in range(len(StartMatches)):
                self.TmpBegin = StartMatches[i].end()
                self.TmpEnd   = EndMatches[i].start()
                InnerText = FileText[self.TmpBegin:self.TmpEnd]

                # Parse the mappings
                #InnerText = self.ParseEffisLine(InnerText)
                NewInner, PragmaEnd = self.ParseEffisLine(InnerText)

                """
                # Parse the DeclareIOs
                NewInner, Out = self.ParseDeclareIOs(InnerText, IOComp)

                # Parse the Opens
                NewInner = self.ParseOpens(Out, NewInner)

                # Parse the BeginSteps
                NewInner = self.ParseBegins(Out, NewInner)
                """

                # Replace the Name mappings
                NewInner = self.ReplaceByName(NewInner, ignore=ignore)

                # Replace the IO mappins
                NewInner = self.ReplaceByIO(NewInner, ignore=ignore)

                # Replace the Engine mappins
                NewInner = self.ReplaceByEngine(NewInner, ignore=ignore)

                # Put the section back into the rest of the file
                UpdatedText += FileText[UpdatedPos:PragmaEnd] + NewInner
                UpdatedPos = self.TmpEnd

            # Whatever is remaining in the file
            UpdatedText += FileText[UpdatedPos:]

            if mimic:
                RelativeFromTop = os.path.dirname(self.TmpFilename.replace(self.TopDir, "").lstrip("/"))
                OutSubdir = os.path.join(outdir, RelativeFromTop)
                base, ext = os.path.splitext(os.path.basename(self.TmpFilename))
                if not os.path.exists(OutSubdir):
                    os.makedirs(OutSubdir)
                outfile = os.path.join(OutSubdir, "{0}{1}{2}".format(base, suffix, ext))
            else:
                base, ext = os.path.splitext(self.TmpFilename)
                outfile = "{0}{1}{2}".format(base, suffix, ext)

            if new:
                with open(outfile, 'w') as out:
                    out.write(UpdatedText)

        return groupnames + self.groupnames


class CppBlocks(BlockFiles):
    language = "c++"
    extensions = [".cpp", ".cxx", ".c++"]
    ReComment = "//"
    GrepComment = ReComment

    HeadExpr = ["#include <adios2.h>", '#include "adios2.h"']
    Header   = '#include "kittie.h"'

    DeclareAdios = '\.DeclareIO'
    FindDeclareIOPattern = "=\s*.*\.DeclareIO\s*\((\s*{0}\s*)\)"
    FindOpenPattern = "=\s*{0}.Open\s*\((.*?)\)"
    FindEndPattern = "{0}.EndStep\s*\((.*?)\)"
    FindClosePattern = "{0}.Close\s*\((.*?)\)"

    FindDeclareIOPatternByIO = "{0}\s*=\s*.*\.DeclareIO\s*\((.*?)\)"
    FindOpenPatternByEngine = "{0}\s*=\s*(.*?).Open\s*\((.*?)\)"

    def FindBeginPattern(self, engine):
        return "([=;}{])?(\s*)" + engine + ".BeginStep\s*\((.*?)\)"

    def InitText(self, keydict):
        args = []
        for key in self.initallowed:
            if key in keydict:
                args += [keydict[key]]
        args += ['adios2::DebugON']
        return "kittie::initialize({0});".format(', '.join(args))


    def DeclareText(self, args, IOName, IOobj=None):
        if IOobj is None:
            base = "= kittie::declare_io({0})"
        else:
            base = "{1} = kittie::declare_io({0})"
        return base.format(IOName, IOobj)

    def OpenText(self, IOName, argstr, engine, keys, EngineObj=None):
        if EngineObj is None:
            base = "= kittie::open({1}, {0})".format(argstr, IOName)
        else:
            base = "{1} = kittie::open({2}, {0})".format(argstr, EngineObj, IOName)

        if ('step' in keys) and (keys['step'].lower() == 'off'):
            step = 0
            base += ";\n" + "{2} = kittie::Couplers[{0}]->begin_step({1})".format(IOName, step, engine)
        return base

    def BeginText(self, Name, argstr, keys, engine, equal=True):
        if 'step' in keys:
            if (keys['step'].lower() == 'off'):
                step = 0
            else :
                step = keys['step']
        else:
            step = None

        if step is not None:
            if argstr.strip() == "":
                argstr = "{0}".format(step)
            else:
                argstr = "{0}, {1}".format(step, argstr)

        if equal:
            base = "= kittie::Couplers[{0}]->begin_step({1}); ".format(Name, argstr)
        else:
            base = "kittie::Couplers[{0}]->begin_step({1}); ".format(Name, argstr)

        base += "{0} = kittie::Couplers[{1}]->engine".format(engine, Name)

        return base


    def EndText(self, Name, argstr):
        base = "kittie::Couplers[{0}]->end_step({1})".format(Name, argstr)
        return base

    def CloseText(self, Name, argstr, keys):
        base = "kittie::Couplers[{0}]->close({1})".format(Name, argstr)
        if ('step' in keys) and (keys['step'].lower() == 'off'):
            step = 0
            base += ";\n" + "kittie::Couplers[{0}]->end_step({1})".format(Name, step)
        return base


    ### DeclareIO related ###

    def GetIoArgumentList(self, SeekedInnerText):
        args, ParenClose = GetArgumentList(SeekedInnerText, end=True)
        return args[0], args, ParenClose

    def GetIoObj(self, InnerText, EqualIndex, args):
        io = GetVar(InnerText, EqualIndex)
        return io


    ### Open related ###

    def OpenPattern(self, io):
        return "=\s*{0}\.Open".format(io)

    def GetOpenArgumentList(self, group, SeekedInnerText):
        args, ParenClose = GetArgumentList(SeekedInnerText, end=True)
        extra = ", ".join(args)
        argstr = "{0}, {1}".format(group, extra)
        return args, argstr, ParenClose

    def GetEngObj(self, InnerText, EqualIndex, args):
        return self.GetIoObj(InnerText, EqualIndex, args)


    ### BeginStep related ###
    def BeginPattern(self, engine):
        first = "[=;}{]"
        second = "{0}\.BeginStep".format(engine)
        return "({0})(\s*)({1})".format(first, second)

    def GetBeginArgumentList(self, group, SeekedInnerText):
        args, ParenClose = GetArgumentList(SeekedInnerText, end=True)
        extra = ", ".join(args)
        argstr = "{0}".format(extra)
        return args, argstr, ParenClose

    def GetStatusObj(self, InnerText, start, args):
        if InnerText[start] == "=":
            status = GetVar(InnerText, start)
        else:
            status = None
        return status



class FortranBlocks(BlockFiles):
    language = "fortran"
    extensions = [".F90", ".f90"]
    ReComment = "!"
    GrepComment = "\\{0}".format(ReComment)
    slash = "\\\\"

    DeclareAdios = 'call[\s{0}]*adios2_declare_io'.format(slash)
    DeclareKittie = 'KittieDeclareIO'
    OpenKittie = "#kittie::open"

    FindDeclareIOPattern = "adios2_declare_io\s*\((.*{0}.*)\)"
    FindOpenPattern = "adios2_open\s*\((.*{0}.*)\)"

    FindDeclareIOPatternByIO = "{0}\s*=\s*.*\.DeclareIO\s*\((.*)\)"

    def FindBeginPattern(self, engine):
        return "adios_begin_step\s*\((.*{0}.*)\)".format(engine)

    def DeclareText(self, args, IOName, IOObj=None):
        return "{1} = {0}({2}, {3})".format(self.DeclareKittie, args[0], IOName, args[3])

    def OpenText(self, IOName, argstr, engine, keys, EngineObj=None):
        return "kittie::open({0})".format(argstr)

    def BeginText(self, IOName, argstr, keys, engine, equal=True):
        base = "kittie::couplers[{0}]->begin_step({1})".format(IOName, argstr)
        return base


    ### declare_io related ###
    # Not tested yet

    def GetIoArgumentList(self, SeekedInnerText):
        args, ParenClose = GetArgumentList(SeekedInnerText, end=True)
        return args[2], args, ParenClose

    def GetIoObj(self, InnerText, EqualIndex, args):
        return args[2]


    ### open related ###
    ### Not implemented yet ###

    def OpenPattern(self, io):
        return "call[\s{0}]*adios2_open".format(self.slash)

    def GetOpenrgumentList(self, group, SeekedInnerText):
        args, ParenClose = GetArgumentList(SeekedInnerText, end=True)
        extra = ", ".join(args)
        argstr = "{0}, {1}".format(group, extra)
        return args, argstr, ParenClose

    def GetEngObj(self, InnerText, EqualIndex, args):
        return args[0]

    ### begin_step related ###
    ### Not implemented yet ###

    def BeginPattern(self, engine):
        return "([=;{}])(\s*{0}\.BeginStep)".format(engine)

    def GetBeginArgumentList(self, group, SeekedInnerText):
        return self.GetOpenArgumentList(group, SeekedInnerText)

    def GetStatusObj(self, InnerText, start, args):
        if InnerText[start] == "=":
            status = GetVar(InnerText, start)
        else:
            status = None
        return status




if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help="sub-command help")
    parser.set_defaults(which='top')

    RepoParser = subparsers.add_parser("repo", help="Process code repository to determine its KITTIE-dependent files and group names")
    RepoParser.add_argument("directory", help="Code repository to look through for KITTIE markups")
    RepoParser.add_argument("outdir", help="Output groups namelist file")
    RepoParser.add_argument("-s", "--suffix", help="String to append to file names when replaced", type=str, default="-kittie")
    RepoParser.add_argument("-n", "--name", help="Name IDing the app", type=str, default=None)
    RepoParser.add_argument("-k", "--skip", help="Groups to skip", type=str, default="")
    RepoParser.add_argument("-m", "--mimic", help="Mimic", action='store_true', default=False)
    RepoParser.add_argument("-w", "--new", help="Use new parser", action='store_true', default=False)
    RepoParser.set_defaults(which='repo')

    FileParser = subparsers.add_parser("file", help="Process one source file and replace KITTIE markups with appropriate APIs")
    FileParser.add_argument("srcfile", help="Source file to read and make replacements")
    FileParser.add_argument("outfile", help="Output file name")
    FileParser.add_argument("-k", "--skip", help="Groups to skip", type=str, default="")
    FileParser.set_defaults(which='file')


    logger = logging.getLogger(__file__)
    logger.setLevel(logging.DEBUG)
    StreamHandler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    StreamHandler.setLevel(logging.DEBUG)
    StreamHandler.setFormatter(formatter)
    logger.addHandler(StreamHandler)


    args = parser.parse_args()
    if len(args.skip.strip()) == 0:
        args.skip = []
    else:
        args.skip = args.skip.split(',')

    if args.which == "file":
        fparser = KittieParser(args.srcfile, args.outfile)
        fparser.FileReplacements(args.skip)


    elif args.which == "repo":
        thisfile = os.path.realpath(__file__)

        groupnames = []
        BlockFinders = [FortranBlocks(), CppBlocks()]
        for finder in BlockFinders:
            finder.FindFiles(args.directory)
            groupnames = finder.MakeReplacements(args.outdir, groupnames, mimic=args.mimic, ignore=args.skip, suffix=args.suffix, new=args.new)
        if args.new:
            if args.name is None:
                args.name = os.path.basename(args.directory)
            WriteGroupsFile(groupnames, args.outdir, args.name)


        if not args.new:
            groups = []
            out = []
            keys = ["\\!", "//"]
            for key in keys:
                try:
                    thisout = subprocess.check_output(["grep", "-r", "{0}@kittie".format(key), args.directory, "--files-with-matches"])
                    out.append(thisout)
                except:
                    pass

            for fname in out:
                files = fname.strip().split()

                for filename in files:
                    filename = filename.decode("utf-8")

                    if args.mimic:
                        dname = os.path.dirname(filename.replace(args.directory, "").lstrip("/"))
                        fname = os.path.basename(filename)
                    else:
                        fname = filename

                    for ext in [".F90", ".cpp"]:
                        if not fname.endswith(ext):
                            continue

                        if args.mimic:
                            subdir = os.path.join(args.outdir, dname)
                            if not os.path.exists(subdir):
                                os.makedirs(subdir)
                            outfile = os.path.join(subdir, "{0}{1}{2}".format(fname[:-len(ext)], args.suffix, ext))
                        else:
                            outfile = "{0}{1}{2}".format(filename[:-len(ext)], args.suffix, ext)

                    if filename.endswith('.F90') or filename.endswith('.cpp'):
                        fparser = KittieParser(filename, outfile)
                        groups = fparser.FindGroups(groups, args.skip)
                        fparser.FileReplacements(args.skip)

            if args.name is None:
                args.name = os.path.basename(args.directory)
            fparser.WriteGroupsFile(groups, args.outdir, args.name)

