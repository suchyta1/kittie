#!/usr/bin/env python

from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import os
import re
import copy
import subprocess
import yaml

import kittie_common


def GetArgList(text, elen=1):
    bss = text.strip()
    argstart = bss.find('(') + 1
    astr = bss[argstart:-elen]

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


def GetAdiosArgs(text, commanddict, names, elen=1):
    alist = GetArgList(text, elen=elen)
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


    def FindEqual(self, text, start, kittie_command, commanddict, newargs, result=None, elen=1, obj=False, pre=""):
        start = self.EqualStart(text, start, cond=obj)

        if result is not None:
            txt = "{0} = {1}(".format(commanddict[result], kittie_command)
        else:
            txt = "{0}{1}(".format(pre, kittie_command)

        for key in newargs:
            txt = "{0}{1}, ".format(txt, commanddict[key])
        txt = "{0})".format(txt.rstrip(', '))
        return txt


    def CommonNoOptions(self, commanddict, keydict, command, text, args, newargs, kittie_command, result=None, elen=1, obj=False, pre=""):
        start, stop = self.ParseCommand(command, text)
        if start is not None:
            commanddict = GetAdiosArgs(text[start:stop], commanddict, args, elen=elen)
            commanddict = CommandKeyAdd(newargs, keydict, commanddict)
            txt = self.FindEqual(text, start, kittie_command, commanddict, newargs, result=result, elen=elen, obj=obj, pre=pre)
            text = '{0}{1}{2}'.format(text[:start], txt, text[stop:])
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


    def ReplaceDeclareIO(self, between, commanddict, keydict):
        if keydict['io'] is not None:
            commanddict['io'] = keydict['io']
        command = "{0}".format(self.DeclareCommand)
        #command = "kittie_adios.{1}.{0}".format(self.DeclareCommand, keydict['group'])

        start, stop = self.ParseCommand(command, between)
        if start is not None:
            commanddict = GetAdiosArgs(between[start:stop], commanddict, ['group'], elen=2)
            commanddict = CommandKeyAdd(['group'], keydict, commanddict)
            argstr = "kittie::declare_io({0});".format(keydict['group'])
            start = self.EqualStart(between, start)
            between = '{0} {1}{2}'.format(between[:start], argstr, between[stop:])

            if keydict['io'] is None:
                io = GetVar(between, start)
                commanddict['io'] = io

        return between, commanddict, start


    def ReplaceOpen(self, between, commanddict, keydict, indentation=""):
        if keydict['engine'] is not None:
            commanddict['engine'] = keydict['engine']
        command = "{1}.{0}".format(self.OpenCommand, commanddict['io'])

        start, stop = self.ParseCommand(command, between)
        if start is not None:
            try:
                commanddict = GetAdiosArgs(between[start:stop], commanddict, ['filename', 'open_mode', 'comm'], elen=2)
            except:
                commanddict = GetAdiosArgs(between[start:stop], commanddict, ['filename', 'open_mode'], elen=2)


            #argstr = "kittie::Couplers[{0}]->open({1}, {2}".format(keydict['group'], commanddict['filename'], commanddict['open_mode'])
            argstr = "kittie::open({0}, {1}, {2}".format(keydict['group'], commanddict['filename'], commanddict['open_mode'])
            if 'comm' in commanddict:
                argstr = "{0}, {1}".format(argstr, commanddict['comm'])
            argstr = "{0});".format(argstr)
            start = self.EqualStart(between, start)

            """
            ws = [' ', '\n', '\t', '\r', '\f', '\v']
            wordend = start - 1
            while between[wordend-1] in ws:
                wordend -= 1
            wordstart = wordend - 1
            while between[wordstart-1] not in (ws + [';', '{', '}']):
                wordstart -= 1
            engine = between[wordstart:wordend]
            """

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


            between = '{0} {1}{2}'.format(between[:start], argstr, between[stop:])
        return between, commanddict, start


    def ReplaceBeginStep(self, between, commanddict, keydict, indentation=""):
        if 'engine' in commanddict:
            command = "{1}.{0}".format(self.BeginStepCommand, commanddict['engine'])
            start, stop = self.ParseCommand(command, between)
        else:
            start = None

        if start is not None:
            num = 2
            args = ['step_mode', 'timeout']
            while num > 0:
                try:
                    commanddict = GetAdiosArgs(between[start:stop], commanddict, args[0:num], elen=2)
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
            between = '{0}{1}{2}'.format(between[:start], txt, between[stop:])

        return between, commanddict, start


    def ReplaceEndStep(self, between, commanddict, keydict):
        if 'engine' in commanddict:
            command = "{1}.{0}".format(self.EndStepCommand, commanddict['engine'])
            start, stop = self.ParseCommand(command, between)
        else:
            start = None

        if start is not None:
            commanddict = GetAdiosArgs(between[start:stop], commanddict, [], elen=2)
            argstr = "kittie::Couplers[{0}]->end_step();".format(keydict['group'])
            between = '{0}{1}{2}'.format(between[:start], argstr, between[stop:])
        return between, commanddict, start


    def ReplaceClose(self, between, commanddict, keydict):
        if 'engine' in commanddict:
            command = "{1}.{0}".format(self.CloseCommand, commanddict['engine'])
            start, stop = self.ParseCommand(command, between)
        else:
            start = None

        if start is not None:
            commanddict = GetAdiosArgs(between[start:stop], commanddict, [])
            argstr = ""
            if self.AddStep:
                argstr = "kittie::Couplers[{0}]->end_step();\n".format(keydict['group'])
            argstr = "{0}kittie::Couplers[{1}]->close();".format(argstr, keydict['group'])
            between = '{0}{1}{2}'.format(between[:start], argstr, between[stop:])
        return between, commanddict, start



class FortranReplacer(BaseReplacer):

    """
    @property
    def DefineCommand(self):
        command = {self.knowntypes['python']: '', self.knowntypes['fortran']: 'adios2_define_variable'}
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

                #txt = "call kittie_define_variable("
                txt = "{0} = KittieDefineVariable(".format(commanddict['varid'])
                for key in knames:
                    txt = "{0}{1}, ".format(txt, commanddict[key])
                txt = "{0})".format(txt.rstrip(', '))
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
    """

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



    def ReplaceOpen(self, between, commanddict, keydict, indentation=""):
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

                between = '{0}{1}{3}{4}{2}'.format(between[:start], txt, between[stop:], space, engine)

            else:
                between = '{0}{1}{2}'.format(between[:start], "", between[stop:])

        return between, commanddict, start


    def ReplaceClose(self, between, commanddict, keydict):
        start, stop = self.ParseCommand(self.CloseCommand, between)
        if start is not None:
            commanddict = GetAdiosArgs(between[start:stop], commanddict, ['engine', 'ierr'])
            if self.AddStep:
                between, commanddict, start = self.CommonNoOptions(commanddict, keydict, self.CloseCommand, between, ['engine', 'ierr'], ['helper', 'ierr'], "kittie_couple_end_step", pre="call ")
            else:
                between = '{0}{1}{2}'.format(between[:start], "", between[stop:])

        return between, commanddict, start


    def ReplaceDeclareIO(self, between, commanddict, keydict):
        #between, commanddict, start = self.CommonNoOptions(commanddict, keydict, self.DeclareCommand, between, ['io', 'adios', 'group', 'ierr'], ['group', 'ierr'], "kittie_declare_io")
        between, commanddict, start = self.CommonNoOptions(commanddict, keydict, self.DeclareCommand, between, ['io', 'adios', 'group', 'ierr'], ['group', 'ierr'], "KittieDeclareIO", result='io')
        return between, commanddict, start


    def ReplaceEndStep(self, between, commanddict, keydict):
        between, commanddict, start = self.CommonNoOptions(commanddict, keydict, self.EndStepCommand, between, ['engine', 'ierr'], ['helper', 'ierr'], "kittie_couple_end_step", pre="call ")
        return between, commanddict, start


    def ReplaceBeginStep(self, between, commanddict, keydict, indentation=""):
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

        return between, commanddict, start



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


    def Replacer(self, func, between, commanddict, keydict, indentation=None):
        start = True
        while start is not None:
            if indentation is not None:
                between, commanddict, start = func(between, commanddict, keydict, indentation=indentation)
            else:
                between, commanddict, start = func(between, commanddict, keydict)

        """
        for name in [self.DefineCommand, self.InquireCommand, self.GetCommand, self.PutCommand]:
            between = between.replace("@{0}".format(name), name)
        """

        return between, commanddict



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

            between, bstart, bend = self.FindCode(matches, i, text)
            indentation = self.GetIndentation(between)

            if self.filetype == 'fortran':
                replacer = FortranReplacer(AddStep=self.AddStep)
            elif self.filetype == 'c++':
                replacer = CppReplacer(AddStep=self.AddStep)

            between, cdict[group] = self.Replacer(replacer.ReplaceDeclareIO, between, cdict[group], keydict)
            between, cdict[group] = self.Replacer(replacer.ReplaceOpen,      between, cdict[group], keydict)
            between, cdict[group] = self.Replacer(replacer.ReplaceBeginStep, between, cdict[group], keydict)
            between, cdict[group] = self.Replacer(replacer.ReplaceEndStep,   between, cdict[group], keydict)
            between, cdict[group] = self.Replacer(replacer.ReplaceClose,     between, cdict[group], keydict)

            if self.filetype == 'fortran':
                between = "\n{0}call kittie_get_helper({1}, common_helper){2}".format(indentation, group, between)

            newtext = "{0}{1}{2}".format(newtext, text[start:bstart], between)
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
        self.keywords = ["step", "dir", "timefile", "group", "filename", "ierr", "varname", "varid", "io", "engine", "timeout"]
        for key in self.keywords:
            self.keydict[key] = None



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
    RepoParser.set_defaults(which='repo')

    FileParser = subparsers.add_parser("file", help="Process one source file and replace KITTIE markups with appropriate APIs")
    FileParser.add_argument("srcfile", help="Source file to read and make replacements")
    FileParser.add_argument("outfile", help="Output file name")
    FileParser.add_argument("-k", "--skip", help="Groups to skip", type=str, default="")
    FileParser.set_defaults(which='file')

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

        """
        try:
            out = subprocess.check_output(["grep", "-r", "\\!@kittie", args.directory, "--files-with-matches"])
        except:
            pass
        """

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
                    print(ext, fname)
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

