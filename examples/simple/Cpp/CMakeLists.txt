execute_process(COMMAND ${PROJECT_SOURCE_DIR}/util/kittie-cpp.py repo ${CMAKE_CURRENT_SOURCE_DIR} --tree-output=${CMAKE_CURRENT_BINARY_DIR})

include_directories(${CMAKE_BINARY_DIR}/src/cpp ${ADIOS2_INCLUDE_DIRS})
add_definitions(-std=c++11 -ffree-line-length-none)

add_executable(writer-cpp ${CMAKE_CURRENT_BINARY_DIR}/writer-kittie.cpp)
#target_link_libraries(writer-cpp kittie ${libadios2})
target_link_libraries(writer-cpp kittie adios2::adios2)
set_target_properties(writer-cpp PROPERTIES OUTPUT_NAME writer)

add_executable(reader-cpp ${CMAKE_CURRENT_BINARY_DIR}/reader-kittie.cpp)
#target_link_libraries(reader-cpp kittie ${libadios2})
target_link_libraries(reader-cpp kittie adios2::adios2)
set_target_properties(reader-cpp PROPERTIES OUTPUT_NAME reader)

install(
	TARGETS writer-cpp
	DESTINATION ${CMAKE_INSTALL_PREFIX}/examples/simple/Cpp
	PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE GROUP_READ GROUP_EXECUTE WORLD_READ WORLD_EXECUTE)
install(
	TARGETS reader-cpp
	DESTINATION ${CMAKE_INSTALL_PREFIX}/examples/simple/Cpp
	PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE GROUP_READ GROUP_EXECUTE WORLD_READ WORLD_EXECUTE)
