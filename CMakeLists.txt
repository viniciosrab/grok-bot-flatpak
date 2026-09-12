cmake_minimum_required(VERSION 3.28)

project(grok-bot-flatpak NONE)

option(GROK_BOT_BUILD_COMPANION
  "Build the KF6 tray companion (requires Qt6/KF6; off for the test gate)"
  OFF
)

if(GROK_BOT_BUILD_COMPANION)
  add_subdirectory(companion)
endif()

enable_testing()

# Wiring test: proves the CTest layer runs instead of being skipped.
# Companion tests extend this layer in later work units.
add_test(
  NAME bootstrap_ctest_wiring
  COMMAND ${CMAKE_COMMAND} -E echo "bootstrap_ctest_wiring: CTest layer is live"
)
