# Job Composition

EFFIS jobs are created used a YAML config file.
These files are parsed by `kittie-compose.py`, which builds the job in the run directory (`rundir`) set in the file.
`kittie-submit` submits the job (e.g. `kittie-submit $rundir`).


Here is an example I use for running Gray-Scott on my Mac.

``` yaml
jobname: gray-scott
rundir: /Users/eqs/Work/wdm/kittie-runs/gray-scott-2
installdir: /Users/eqs/Work/spack/spack/opt/spack/darwin-highsierra-x86_64/clang-10.0.0-apple/gray-scott-cpp-uirzllqphyp5b25ai2bc4hsf6t7lro7k

machine:
  name: local
  job_setup: "/Users/eqs/Work/wdm/kittie-wdm/machine-setups/setup.mac.sh"

run:

  gray-scott:
    path: ${installdir}/simulation/gray-scott
    args:
    - settings.json
    processes: 1
    processes-per-node: 1
    copy:
    - ${installdir}/settings/adios2.xml
    - ${installdir}/settings/settings.json

    groups:
      ConcentrationData:
        filename: ${rundir}/gray-scott/gs.bp
        engine: BPFile
        plot:
          U:
            image: U[28, :, :]
          V:
            image: V[28, :, :]

  pdf:
    path: ${installdir}/analysis/pdf_calc
    args:
    - ../gray-scott/gs.bp
    - pdf.bp
    - 100

    processes: 1
    processes-per-node: 1
    copy:
    - ${installdir}/settings/adios2.xml

    groups:
      ConcentrationData:
        engine: BPFile
      PDFData:
        engine:
          name: BPFile
          Substreams: 1
        filename: ${rundir}/pdf/pdf.bp
        plot:
          U-pdf:
            x: U/bins
            y: U/pdf[28, :]
```

The `machine` section is required. Possible names include `local`, `summit`, `theta`, and `titan`.
`job_setup` is a script to source that runs before the actual codes start, like from a batch file if running through a scheduler.

The `run` section is where the codes to run are defined. 
`path` is where the executables live in the file system and `args` specify any command line arguments for the them.
The names `gray-scott` and `pdf` aren't special, they're just labels.
Each code will run in its own directory under `rundir`, named by these labels.
There are settings to indicate how many total processes to run, and how many are on each node.
At the moment, node sharing between applications isn't turned on, but that's coming.
Files are copied into the run directory with the `copy` lists.

`groups` is the section connected to the EFFIS names in the @effis pragmas.
Each group is one that was tagged in the source code. 
Here one sets the ADIOS engine type -- which can be a simple string or a dictionary if the engine parameters need to be set.
`filename` would take precedence over that set in the source code.
`plot` triggers the automatic plotting. The labels `U`, `V`, `U-pdf` become the title of the plots.
1D (`x` vs. `y`) plotting and 2D (`image`) plotting is supported, where the quantities available to plot are those in the output EFFIS data.
Slicing syntax is like numpy. Plots save to the `kittie-plotter` directory.

Users can define there own variables to use throughout the file, then dereferenced then with ${} syntax, for example as used with `installdir`.
In fact, any key in the file can be dereferenced with ${}, and `.` then index into dictionaries. For example one could use something like ${machine}.name.

