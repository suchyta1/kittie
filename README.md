The development is being done from the [`dev`](https://github.com/suchyta1/kittie/tree/dev) branch during the initial stages of this repository.


# Kittie

Kittie is a framework and set of software services to support code coupling jobs.
It is intended to ease complexities to execute, compose, monitor, and control complex coupled simulations.


## Job composition

Kittie is configured with an input configuration file; currently we support YAML files.
This will describe what one wants to do in the job.
It will include submitting a batch job for at least one executable to run, packaged with its necessary input files, 
as well as how many nodes and processes should be used to run parallel applications on the target system.
Other setup can be requested, such as creating directories that need to exist during the job.

Sample configuration files can be found in in [`examples/`](examples/).
