include_directories(${ADIOS2_INCLUDE_DIRS_FORTRAN})
if(USE_MPI)
	add_definitions(-DUSE_MPI)
endif()

add_library(kittie_f ${CMAKE_CURRENT_SOURCE_DIR}/kittie.F90)
install(TARGETS kittie_f DESTINATION ${CMAKE_INSTALL_PREFIX}/lib)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/kittie.mod DESTINATION ${CMAKE_INSTALL_PREFIX}/include)
