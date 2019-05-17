# Using the Pre-processor

When EFFIS is installed, one of the scripts is `kittie-cpp.py`. This is the EFFIS pre-processor,
a source-to-source engine that goes through the source files making the updates to the code needed for EFFIS.
As it does so, it makes a list of the groups it finds that use EFFIS, and writes out a small text file called 
`.kittie-setup.yaml` (`.kittie-setup.nml` for Fortran) that EFFIS will read at job time when the program starts.

Using `kittie-cpp.py` like:

```
kittie-cpp.py repo $REPO_TOP
```

* `$REPO_TOP`     The source directory to look through. (All subdirectories will be checked too.)

Options:

* `--suffix`      Each file that needs replacements will be written out as a new file, as ${base}${suffix}${ext}. The default is "-kittie".
* `--tree-output` Ordinarily, updated source files write into the same directory as the corresponding source file. Setting `--tree-output` to
to a directory sends the output files to this directory, into subdirectories mimicking the original directory structure
* `--confdir`     Where the setup file writes. Default is $REPO_TOP
them into $OUPUT_ DIR using a mimicked directory structure.
* `--name`        A name for the application. This is written into the setup file. The default is the repository top directory name.
This only affects things that happen behind the scenes.

