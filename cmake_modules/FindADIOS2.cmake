find_file(ADIOS2_CONFIG adios2-config  HINTS "$ENV{ADIOS2_DIR}/bin")
message(STATUS "ADIOS2_CONFIG: ${ADIOS2_CONFIG}")


if(ADIOS2_CONFIG)
	set(ADIOS2_FOUND TRUE)
	get_filename_component(ADIOS2_BINDIR ${ADIOS2_CONFIG} DIRECTORY)
	get_filename_component(ADIOS2_PREFIX ${ADIOS2_BINDIR} DIRECTORY)
	set(ADIOS2_INCLUDE_DIRS ${ADIOS2_PREFIX}/include ${ADIOS2_PREFIX}/include/fortran) 
	set(ADIOS2_LIBRARY_DIRS ${ADIOS2_PREFIX}/lib) 
	find_library(libadios2  NAMES adios2   HINTS ${ADIOS2_LIBRARY_DIRS})
	find_library(libfortran NAMES adios2_f HINTS ${ADIOS2_LIBRARY_DIRS})
else(ADIOS2_CONFIG)
	set(ADIOS2_FOUND FALSE)
endif(ADIOS2_CONFIG)


if(NOT ADIOS2_FOUND)
    unset(ADIOS2_INCLUDE_DIRS)
	unset(libadios2)
	unset(libfortran)
endif(NOT ADIOS2_FOUND)


include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(ADIOS2 REQUIRED_VARS ADIOS2_INCLUDE_DIRS libadios2 libfortran)

