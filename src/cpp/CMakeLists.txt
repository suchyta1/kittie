include_directories(${ADIOS2_INCLUDE_DIRS} ${YAML_INCLUDE_DIRS})
add_definitions(-std=c++11)

if(USE_MPI)
	add_definitions(-DUSE_MPI)
endif()

set(lib_objects ${CMAKE_CURRENT_SOURCE_DIR}/kittie.cpp)
add_library(kittie ${lib_objects})
target_link_libraries(kittie PRIVATE ${libadios2} ${libyamlcpp})
install(TARGETS kittie DESTINATION ${CMAKE_INSTALL_PREFIX}/lib)
install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/kittie.h DESTINATION ${CMAKE_INSTALL_PREFIX}/include)

