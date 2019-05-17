# Overview

Welcome to the EFFIS (2.0) documentation. (The software that was formerly known as KITTIE.)
EFFIS is a code coupling integration suite.
It uses [ADIOS](https://github.com/ornladios/ADIOS2) 
to move data between applications and provides job composition support on DOE ECP type machines 
with a simple YAML interface.

Some examples of extensions that EFFIS provide beyond ADIOS alone are:
* Switch between file-based and in-memory data movement (coupling or general output) without any changes
* Automatic step seeking
* Identical job creation on different platforms
* Automated plotting (e.g. to be connected to a dashboard)
* Performance timing
* Source code, input configuration, etc. capture


## Topics
The help pages are organized into subtopics linked below.

* [Installation](doc/installation.md)
* [Code integration](doc/integration.md)
* [Using the pre-processor](doc/preprocessor.md)
* [Job Composition](doc/composition.md)

