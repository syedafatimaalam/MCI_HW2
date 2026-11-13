cmake_minimum_required(VERSION 3.22)

# Enable C and Assembly
enable_language(C ASM)

# STM32 microcontroller definition
set(MX_Defines_Syms
    STM32F303xC
    $<$<CONFIG:Debug>:DEBUG>
)

# CMSIS include directories
set(MX_Include_Dirs
    ${CMAKE_CURRENT_SOURCE_DIR}/../../Core/Inc
    ${CMAKE_CURRENT_SOURCE_DIR}/../../Drivers/CMSIS/Device/ST/STM32F3xx/Include
    ${CMAKE_CURRENT_SOURCE_DIR}/../../Drivers/CMSIS/Include
)

# Application source files
set(MX_Application_Src
    ${CMAKE_CURRENT_SOURCE_DIR}/../../Core/Src/main.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../../Core/Src/system_stm32f3xx.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../../startup_stm32f303xc.s
)

# CMSIS interface library
add_library(stm32cubemx INTERFACE)

target_include_directories(stm32cubemx INTERFACE
    ${MX_Include_Dirs}
)

target_compile_definitions(stm32cubemx INTERFACE
    ${MX_Defines_Syms}
)

# Add application sources
target_sources(${CMAKE_PROJECT_NAME} PRIVATE
    ${MX_Application_Src}
)

# Link CMSIS configuration
target_link_libraries(${CMAKE_PROJECT_NAME}
    stm32cubemx
    ${TOOLCHAIN_LINK_LIBRARIES}
)