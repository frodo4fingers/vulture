cmake_minimum_required(VERSION 3.24)

project(vulture_vision_worker LANGUAGES CXX)

add_executable(vulture-vision-worker src/main.cpp)
target_compile_features(vulture-vision-worker PRIVATE cxx_std_20)

if(MSVC)
    target_compile_options(
        vulture-vision-worker
        PRIVATE
        /W4
        /WX
        /permissive-
    )
else()
    target_compile_options(
        vulture-vision-worker
        PRIVATE
        -Wall
        -Wextra
        -Wconversion
        -Werror
        -Wpedantic
    )
endif()
