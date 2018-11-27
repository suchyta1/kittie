# Function to make sure CMake understands all the thinks ADIOS needs for linking
macro(adios2_implicit_deps linkflags libdirs libraries incflags incdirs)

	# Find the include directories
	string(REGEX MATCHALL "-I([A-Za-z_0-9/\\.-]+)" _INCDIRS "${${incflags}}")
	foreach(_INCDIR ${_INCDIRS})
		string(REPLACE "-I" "" _INCDIR ${_INCDIR})
		set(${incdirs} ${${incdirs}} ${_INCDIR})
    endforeach()
	message(STATUS "incdirs: ${incdirs}")


	# Find the library directories
	string(REGEX MATCHALL "-L([A-Za-z_0-9/\\.-]+)" _LIBDIRS "${${linkflags}}")
	foreach(_LIBDIR ${_LIBDIRS})
        string(REPLACE "-L" "" _LIBDIR ${_LIBDIR})
		set(${libdirs} ${${libdirs}} ${_LIBDIR})
    endforeach()
	message(STATUS "libdirs: ${libdirs}")

	# Find the libraries
	string(REGEX MATCHALL " -l([A-Za-z_0-9\\.-]+)" _LIBS "${${linkflags}}")
	foreach(_LIB ${_LIBS})
        string(REPLACE " -l" "" _LIB ${_LIB})
		find_library(_ILIB NAMES ${_LIB} HINTS ${dirs})
		message(STATUS "_ILIB: ${_ILiB}")

        if(_ILIB)
			set(${libraries} ${${libraries}} "${_ILIB}")
        else(_ILIB)
            set(ADIOS2_FOUND FALSE)
            message(STATUS "ADIOS: Could NOT find library ${_LIB}")
        endif(_ILIB)

    endforeach()

endmacro()


find_file(ADIOS2_CONFIG adios2-config  HINTS "$ENV{ADIOS2_DIR}/bin")
message(STATUS "ADIOS2_CONFIG: ${ADIOS2_CONFIG}")
	
if(ADIOS2_CONFIG)
	set(ADIOS2_FOUND TRUE)

	execute_process(COMMAND ${ADIOS2_CONFIG} --prefix    OUTPUT_VARIABLE ADIOS2_ROOT_DIR   RESULT_VARIABLE ADIOS2_CONFIG_RETURN  OUTPUT_STRIP_TRAILING_WHITESPACE)
	message(STATUS "Ran adios2-config")
    if(NOT ADIOS2_CONFIG_RETURN EQUAL 0)
        set(ADIOS2_FOUND FALSE)
        message(STATUS "Can NOT execute 'adios2-config' properly - check file permissions?")
    endif()

	execute_process(COMMAND ${ADIOS2_CONFIG} --version   OUTPUT_VARIABLE ADIOS2_VERSION    RESULT_VARIABLE ADIOS2_CONFIG_RETURN  OUTPUT_STRIP_TRAILING_WHITESPACE)
	execute_process(COMMAND ${ADIOS2_CONFIG} --libs      OUTPUT_VARIABLE ADIOS2_LINKFLAGS  RESULT_VARIABLE ADIOS2_CONFIG_RETURN  OUTPUT_STRIP_TRAILING_WHITESPACE)

	# This should work but adios2-config is somewhat broken
	#execute_process(COMMAND ${ADIOS2_CONFIG} --cxxflags  OUTPUT_VARIABLE ADIOS2_INCFLAGS   RESULT_VARIABLE ADIOS2_CONFIG_RETURN  OUTPUT_STRIP_TRAILING_WHITESPACE)
	set(ADIOS2_INCFLAGS -I${ADIOS2_ROOT_DIR}/include) 

	message(STATUS "ADIOS2_INCFLAGS: ${ADIOS2_INCFLAGS}")
	adios2_implicit_deps(ADIOS2_LINKFLAGS ADIOS2_LIBRARY_DIRS ADIOS2_LIBRARIES ADIOS2_INCFLAGS ADIOS2_INCLUDE_DIRS)

	set(ADIOS2_INCLUDE_DIRS_FORTRAN ${ADIOS2_INCLUDE_DIRS} ${ADIOS2_ROOT_DIR}/include/fortran)
	find_library(libfortran NAMES adios2_f HINTS ${ADIOS2_LIBRARY_DIRS})
	if(libfortran)
		set(ADIOS2_LIBRARIES_FORTRAN ${ADIOS2_LIBRARIES} ${libfortran})
	else()
		set(ADIOS2_FOUND FALSE)
		message(STATUS "ADIOS: Could NOT find library -ladios_f")
	endif()


else(ADIOS2_CONFIG)
	set(ADIOS2_FOUND FALSE)
endif(ADIOS2_CONFIG)


if(NOT ADIOS2_FOUND)
    unset(ADIOS2_INCLUDE_DIRS)
    unset(ADIOS2_LIBRARIES)
	unset(ADIOS2_INCLUDE_DIRS_FORTRAN)
	unset(ADIOS2_LIBRARIES_FORTRAN)
endif(NOT ADIOS2_FOUND)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(ADIOS2 
	REQUIRED_VARS
		ADIOS2_LIBRARIES
		ADIOS2_LIBRARIES_FORTRAN
		ADIOS2_INCLUDE_DIRS
		ADIOS2_INCLUDE_DIRS_FORTRAN
	VERSION_VAR ADIOS2_VERSION
	)
