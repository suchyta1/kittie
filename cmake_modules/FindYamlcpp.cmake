find_file(YAML_H include/yaml-cpp/yaml.h  HINTS "$ENV{YAML_DIR}")
message(STATUS "yaml.h: ${YAML_H}")

if(YAML_H)
	get_filename_component(YAML_CPP    ${YAML_H}   DIRECTORY)
	get_filename_component(YAML_INC    ${YAML_CPP} DIRECTORY)
	get_filename_component(YAML_PREFIX ${YAML_INC} DIRECTORY)
	set(YAML_INCLUDE_DIRS ${YAML_INC}) 
	set(YAML_LIBRARY_DIRS ${YAML_PREFIX}/lib) 
	find_library(libyamlcpp  NAMES yaml-cpp  HINTS ${YAML_LIBRARY_DIRS})
endif(YAML_H)

if(NOT YAML_H)
	unset(YAML_INCLUDE_DIRS)
	unset(libyamlcpp)
endif(NOT YAML_H)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(Yamlcpp REQUIRED_VARS YAML_INCLUDE_DIRS libyamlcpp)

