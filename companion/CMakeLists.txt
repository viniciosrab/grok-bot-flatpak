cmake_minimum_required(VERSION 3.28)

project(grok-bot-companion VERSION 0.47.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 REQUIRED COMPONENTS Widgets DBus)
find_package(KF6StatusNotifierItem REQUIRED)
find_package(KF6WindowSystem REQUIRED)
# Fail-closed: the find_package calls above are REQUIRED on purpose. A host
# without Qt6 Widgets/DBus, KF6StatusNotifierItem, or KF6WindowSystem must
# error out here, never silently skip the production companion target.

add_executable(grok-bot-companion src/main.cpp)

target_link_libraries(grok-bot-companion PRIVATE
  Qt6::Widgets
  Qt6::DBus
  KF6::StatusNotifierItem
)

install(TARGETS grok-bot-companion RUNTIME DESTINATION bin)

# Compiled lifecycle probes around the internal helpers (real temporary
# Unix sockets plus owned child processes with bounded timeouts; no
# fixture adapters). See tests/ for the seam rationale.
add_subdirectory(tests)

# Bounded watcherless startup path for the production binary.
# NEGATIVE TEST ONLY: proves the companion fails closed without a
# StatusNotifierWatcher (exit 1 with StatusNotifierWatcher evidence under
# QT_QPA_PLATFORM=offscreen). This is NOT X3 launch proof; positive
# watcher/tray proof lives exclusively in tools/prove_x3.sh plus the
# automatic hosted x3 workflow.
add_test(
  NAME companion_watcherless_rejects_headless
  COMMAND sh ${CMAKE_CURRENT_SOURCE_DIR}/tests/check_watcherless.sh $<TARGET_FILE:grok-bot-companion>
)
set_tests_properties(companion_watcherless_rejects_headless PROPERTIES
  TIMEOUT 90
  ENVIRONMENT "QT_QPA_PLATFORM=offscreen"
)
