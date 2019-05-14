#!/usr/bin/env python

from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import os
import re
import subprocess
import yaml
import logging
import kittie_common


def GetVar(between, start):
    ws = [' ', '\n', '\t', '\r', '\f', '\v']
    wordend = start - 1
    while between[wordend-1] in ws:
        wordend -= 1
    wordstart = wordend - 1
    while between[wordstart-1] not in (ws + [';', '{', '}']):
        wordstart -= 1
    return between[wordstart:wordend]


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
        NewInner += InternalText[UpdatePos:match.start()] + self.OpenText(TmpMap[NameKey], OpenArgsStr, OpenArgs, engine, TmpMap['keys'])
        UpdatePos = match.end()
        return engine, NewInner, UpdatePos

    def ForwardReplaceBegin(self, match, TmpMap, InternalText, NewInner, UpdatePos, engine, NameKey='NewName'):
        if self.language == "c++":
            status, BeginArgStr, BeginArgs = self.ArgsObj(InternalText, match, fpos=3, mpos=3, remove=[0], size=2)
        else:
            status, BeginArgStr, BeginArgs = self.ArgsObj(InternalText, match, fpos=3, mpos=0, remove=[0], size=2)

        if (InternalText[match.start():].strip()[0] == "=") or (self.language == "fortran"):
            NewInner += InternalText[UpdatePos:match.start()] + self.BeginText(TmpMap[NameKey], BeginArgStr, TmpMap['keys'], engine, equal=True)
        else:
            NewInner += InternalText[UpdatePos:match.end(2)] + self.BeginText(TmpMap[NameKey], BeginArgStr, TmpMap['keys'], engine, equal=False)
        UpdatePos = match.end()
        return status, NewInner, UpdatePos

    def ForwardReplaceEnd(self, match, TmpMap, InternalText, NewInner, UpdatePos, engine, NameKey='NewName'):
        nothing, EndArgStr, EndArgs = self.ArgsObj(InternalText, match)
        NewInner += InternalText[UpdatePos:match.start()] + self.EndText(TmpMap[NameKey], EndArgStr, engine)
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
        NewInner += InternalText[UpdatePos:match.start()] + self.OpenText(TmpMap[NameKey], OpenArgsStr, OpenArgs, TmpMap['EngineObj'], TmpMap['keys'], EngineObj=TmpMap['EngineObj'])
        UpdatePos = match.end()
        return io, NewInner, UpdatePos


    def ReplaceByName(self, InnerText, ignore=[], only=None):
        """ Make any necessary replacements implied by Name mappings """

        InternalText = InnerText

        for TmpMap in self.TmpMap:

            if ('OldName' not in TmpMap) or (TmpMap['NewName'] in ignore):
                continue

            if (only is not None) and (TmpMap['NewName'] not in only):
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
                        nothing, NewInner, UpdatePos = self.ForwardReplaceEnd(match, TmpMap, InternalText, NewInner, UpdatePos, engine, NameKey='NewName')

                    match = MatchPattern(self.FindClosePattern, [engine], InternalText)
                    if match is not None:
                        nothing, NewInner, UpdatePos = self.ForwardReplaceClose(match, TmpMap, InternalText, NewInner, UpdatePos, NameKey='NewName')

            NewInner += InternalText[UpdatePos:]
            InternalText = NewInner
        return InternalText


    def ReplaceByIO(self, InnerText, ignore=[], only=None):
        """ Make any necessary replacements implied by IO mappings """

        InternalText = InnerText

        for TmpMap in self.TmpMap:

            if ('IOobj' not in TmpMap) or (TmpMap['IOName'] in ignore):
                continue

            if (only is not None) and (TmpMap['IOName'] not in only):
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
                    nothing, NewInner, UpdatePos = self.ForwardReplaceEnd(match, TmpMap, InternalText, NewInner, UpdatePos, engine, NameKey='IOName')

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


    def ReplaceByEngine(self, InnerText, ignore=[], only=None):
        """ Make any necessary replacements implied by Engine mappings """

        InternalText = InnerText

        for TmpMap in self.TmpMap:

            if ('EngineObj' not in TmpMap) or (TmpMap['EngineName'] in ignore):
                continue

            if (only is not None) and (TmpMap['EngineName'] not in only):
                continue

            UpdatePos = 0
            NewInner = ""

            match = MatchPattern(self.FindBeginPattern(TmpMap['EngineObj']), [], InternalText)
            if match is not None:
                status, NewInner, UpdatePos = self.ForwardReplaceBegin(match, TmpMap, InternalText, NewInner, UpdatePos, TmpMap['EngineObj'], NameKey='EngineName')

            match = MatchPattern(self.FindEndPattern, [TmpMap['EngineObj']], InternalText)
            if match is not None:
                nothing, NewInner, UpdatePos = self.ForwardReplaceEnd(match, TmpMap, InternalText, NewInner, UpdatePos, TmpMap['EngineObj'], NameKey='EngineName')

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
            if self.language == "fortran":
                comp = re.compile(expr)
                FileText = comp.sub(self.Header, FileText)
            else:
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


    def MakeReplacements(self, outdir, groupnames, mimic=False, ignore=[], only=None, suffix="-kittie"):
        """ Go through the identified files, and replace ADIOS-2 statements with slightly updated ones to support Effis """

        InitExpr  = "{0}{1}".format(self.ReComment, self.init)
        StartExpr = "{0}{1}".format(self.ReComment, self.begin)
        EndExpr   = "{0}{1}".format(self.ReComment, self.end)
        StartComp = re.compile(StartExpr, re.MULTILINE)
        EndComp   = re.compile(EndExpr, re.MULTILINE)
        #IOComp    = re.compile(self.DeclareAdios)
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
                NewInner, PragmaEnd = self.ParseEffisLine(InnerText)

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

    #DeclareAdios = '\.DeclareIO'
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

    def OpenText(self, IOName, argstr, args, engine, keys, EngineObj=None):
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


    def EndText(self, Name, argstr, engine):
        base = "kittie::Couplers[{0}]->end_step({1})".format(Name, argstr)
        return base

    def CloseText(self, Name, argstr, keys):
        base = "kittie::Couplers[{0}]->close({1})".format(Name, argstr)
        if ('step' in keys) and (keys['step'].lower() == 'off'):
            step = 0
            base = "kittie::Couplers[{0}]->end_step({1});".format(Name, step) + '\n'+ base
        return base


class FortranBlocks(BlockFiles):
    language = "fortran"
    extensions = [".F90", ".f90"]
    ReComment = "!"
    GrepComment = "\\{0}".format(ReComment)
    slash = "\\\\"
    spaceslash = '[\s{0}]*'.format(slash)
    call = 'call{0}'.format(spaceslash)

    HeadExpr = ["use{0}adios2{0}\n".format(spaceslash)]
    Header   = 'use kittie\n'

    FindDeclareIOPattern = call + "adios2_declare_io" + spaceslash + "\((.*{0}.*)\)"
    FindOpenPattern      = call + "adios2_open"       + spaceslash + "\((.*{0}.*)\)"
    FindEndPattern       = call + "adios2_end_step"   + spaceslash + "\((.*{0}.*)\)"
    FindClosePattern     = call + "adios2_close"      + spaceslash + "\((.*{0}.*)\)"

    FindDeclareIOPatternByIO = FindDeclareIOPattern
    FindOpenPatternByEngine  = FindOpenPattern


    # I'm not using ierr anywhere yet

    def FindBeginPattern(self, engine):
        return self.call + "adios2_begin_step" + self.spaceslash + "\((.*{0}.*)\)".format(engine)

    def InitText(self, keydict):
        for key in self.initallowed:
            if 'comm' in keydict:
                args += [keydict[key]]
            if 'xml' in keydict:
                args += [keydict[key]]
        return "call kittie_initialize({0})".format(', '.join(args))

    def DeclareText(self, args, IOName, IOObj=None):
        return "{0} = KittieDeclareIO({1}, {2})".format(args[0], IOName, args[3])

    def HelperLine(self, EffisName):
        cmd = "call kittie_get_helper({0}, common_helper)".format(EffisName)
        return cmd

    def EngineLine(self, engine):
        return "{0} = common_helper%engine".format(engine)


    def OpenText(self, IOName, argstr, args, engine, keys, EngineObj=None):
        ArgsStr = ", ".join(args[2:])
        base = self.HelperLine(IOName) + "\n" + "call kittie_open(common_helper, {0}, {1})".format(IOName, ArgsStr)
        if ('step' in keys) and (keys['step'].lower() == 'off'):
            step = 0
            base += "\n" + "call kittie_couple_start(common_helper, {0})".format(step)
        base += "\n" + self.EngineLine(engine)
        return base

    # I'm not using timeout or status yet
    def BeginText(self, IOName, argstr, keys, engine, equal=True):
        args = []

        if 'step' in keys:
            args+= "step={0}".format(keys['step'])

        if len(args) > 0:
            base = self.HelperLine(IOName) + "\n" + "call kittie_couple_start(common_helper, {0})".format(', '.join(args))
        else:
            base = self.HelperLine(IOName) + "\n" + "call kittie_couple_start(common_helper)"

        base += '\n' + self.EngineLine(engine)
        return base


    def EndText(self, Name, argstr, engine):
        base = self.HelperLine(Name) + "\n" + "call kittie_couple_end_step(common_helper)" + "\n" + self.EngineLine(engine)
        return base

    def CloseText(self, Name, argstr, keys):
        base = "kittie_close(common_helper)".format(Name, argstr)

        if ('step' in keys) and (keys['step'].lower() == 'off'):
            step = 0
            base = self.HelperLine(Name) + "\n" + "call kittie_couple_end_step(common_helper)" + '\n' + base
        else:
            base = self.HelperLine(Name) + "\n" + base

        base += "\n" + self.EngineLine(engine)
        return base


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
    RepoParser.add_argument("-o", "--only", help="Groups to keep", type=str, default="")
    RepoParser.add_argument("-m", "--mimic", help="Mimic", action='store_true', default=False)
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

    if len(args.only.strip()) == 0:
        args.only = None
    else:
        args.only = args.only.split(',')


    # Need to implement single file version
    if args.which == "repo":
        thisfile = os.path.realpath(__file__)

        groupnames = []
        BlockFinders = [FortranBlocks(), CppBlocks()]
        for finder in BlockFinders:
            finder.FindFiles(args.directory)
            groupnames = finder.MakeReplacements(args.outdir, groupnames, mimic=args.mimic, ignore=args.skip, only=args.only, suffix=args.suffix)

        if args.name is None:
            args.name = os.path.basename(args.directory)
        WriteGroupsFile(groupnames, args.outdir, args.name)

