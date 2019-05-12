# Using the Pre-processor

When EFFIS is installed, one of the scripts is `kittie-cpp.py`. This is the EFFIS pre-processor,
a source-to-source engine that goes through the source files making the updates to the code needed for EFFIS.
As it does so, it makes a list of the groups it finds that use EFFIS, and writes out a small text file called 
`.kittie-setup.yaml` that EFFIS will read at job time when the program starts.

Using `kittie-cpp.py` like:

```
kittie-cpp.py repo $REPO_TOP $OUTPUT_DIR \
	--suffix="-kittie" \
	--mimic \
	--name=grayscott \
	--new
```

* `$REPO_TOP`   The source directory to look through. (All subdirectories will be checked too.)
* `$OUTPUT_DIR` Where the setup file writes. If using `--mimic` updated files go here too.
* `--suffix`    Each file that needs replacements will be written out as a new file, as ${base}${suffix}${ext}. The default is "-kittie".
* `--mimic`     Ordinarily, updated files are suffixed and just rewritten into the same directory as the original. `--mimic` writes 
them into $OUPUT_DIR using a mimicked directory structure.
* `--name`      A name for the application. This is written into the setup file. The default is the repository top directory name.
This only affects things that happen behind the scenes.
* `--new`       This won't actually exist soon. It's just to use some new updates I've recently pushed. 


Some of these options aren't especially intuitive, having persisted out of previous renditions, and I'll update them.
