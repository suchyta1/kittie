include_directories(${ADIOS2_INCLUDE_DIRS})
add_definitions(-ffree-line-length-none)

if(USE_MPI)
	add_definitions(-DUSE_MPI)
endif()

if(FINE_TIME)
	add_definitions(-DFINE_TIME)
endif()

set(module_objects ${CMAKE_CURRENT_SOURCE_DIR}/kittie.F90 ${CMAKE_CURRENT_SOURCE_DIR}/kittie_internal.F90)
add_library(kittie_f ${module_objects})
target_link_libraries(kittie_f PRIVATE ${libadios2} ${libfortran})
set_source_files_properties(${CMAKE_CURRENT_SOURCE_DIR}/kittie.F90  PROPERTIES OBJECT_DEPENDS  ${CMAKE_CURRENT_SOURCE_DIR}/kittie_internal.F90)

install(DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/ DESTINATION ${CMAKE_INSTALL_PREFIX}/include  FILES_MATCHING PATTERN "kittie*.mod" PATTERN "CMakeFiles" EXCLUDE)
install(TARGETS kittie_f DESTINATION ${CMAKE_INSTALL_PREFIX}/lib)

