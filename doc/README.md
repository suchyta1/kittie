# Kittie Installation

The dependencies for `Kittie` itself are much lighter than the dependencies for the science codes.
(Officially, `Kittie` has been renamed to EFFIS 2.0, but I haven't updated any names anywhere in the code, 
so I'll just keep saying `Kittie` for now in the documentation.)

* [ADIOS-2](https://github.com/ornladios/ADIOS2)
* [Cheetah](https://github.com/suchyta1/cheetah/tree/summit-support) -- notice the 'nonstandard' `summit-support` version, which has not been merged into master. (This is what provides the YAML frontend.)

`Kittie` itself is a CMake package. 
I've never quite been able to figure out how to get the Python installation to work correctly under CMake, 
so the Python installation is done as an extra step after the usual `cmake` followed by `make`.

```
mkdir build
cd build
cmake -DCMAKE_PREFIX_PATH=/some/where ../
pip install --prefix /some/where .
```


# Science Codes

I'm not going to fully explain installing XGC and GENE, because it's not that straightforward, and if you're not already doing it WDM,
learning to do so probably isn't a great use of your time. If you're working with me, you should be able to use my versions or ask me about building.
I will point out, there are certain versions to use for the source code:

* [XGC](https://github.com/suchyta1/XGC-Devel/tree/effis)
* [GENE](https://gitlab.mpcdf.mpg.de/ext-a1e80ec9999b/gene-dev/tree/xgc-user)


Another thing to point out is that these versions are using the `Kittie` preprocessor to translate the pragmas in the code.
The preprocessor writes a lightweight text file alongside the binary executables in order to denote which I/O groups we're using Kittie for.


# Running Workflows

I have a repository of workflows to run [here](https://github.com/suchyta1/kittie-wdm/tree/develop).
The most recent ones are in the `develop` branch under [`YAML/milestone-jobs/summit/`](https://github.com/suchyta1/kittie-wdm/tree/develop/YAML/milestone-jobs/summit),
e.g. [plot1d.yaml](https://github.com/suchyta1/kittie-wdm/blob/develop/YAML/milestone-jobs/summit/plot1d.yaml).

To run the workflows:

```
kittie-compose.py plot1d.yaml
cd /one/up/from/wherever/you/set/rundir
kittie-submit rundir
```
