cmake_minimum_required(VERSION 3.28)

project(grok-bot-flatpak NONE)

option(GROK_BOT_BUILD_COMPANION
  "Build the KF6 tray companion (requires Qt6/KF6; missing deps fail closed)"
  ON
)

if(GROK_BOT_BUILD_COMPANION)
  add_subdirectory(companion)
endif()

enable_testing()

# Wiring test: proves the CTest layer runs instead of being skipped.
# The production companion target above plus its compiled lifecycle and
# watcherless tests extend this layer; missing Qt6/KF6 deps fail closed
# at configure time instead of silently skipping the companion.
add_test(
  NAME bootstrap_ctest_wiring
  COMMAND ${CMAKE_COMMAND} -E echo "bootstrap_ctest_wiring: CTest layer is live"
)
