cmake_minimum_required(VERSION 3.28)

project(grok-bot-companion VERSION 0.47.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 REQUIRED COMPONENTS Widgets DBus)
find_package(KF6StatusNotifierItem REQUIRED)
find_package(KF6WindowSystem REQUIRED)

add_executable(grok-bot-companion src/main.cpp)

target_link_libraries(grok-bot-companion PRIVATE
  Qt6::Widgets
  Qt6::DBus
  KF6::StatusNotifierItem
)

install(TARGETS grok-bot-companion RUNTIME DESTINATION bin)
