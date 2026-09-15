# Compiled lifecycle probes for the Grok Bot tray companion.
#
# These tests exercise the same production lifecycle helper module as the
# companion (bounded nonblocking AF_UNIX probe, SO_PEERCRED peer
# identification, owned process-group graceful shutdown, protocol-URL
# filtering, and the cold-start wait-and-forward loop) using REAL temporary
# Unix sockets and REAL owned child processes with bounded timeouts.
#
# Codebase-design note: lifecycle_helpers is a deep module with a small
# interface. These tests link the same production implementation as the
# companion. There is deliberately NO fixture adapter here: only one
# production implementation exists, so a seam with a fake would be a
# hypothetical seam. Tests use the real syscalls with real resources.
cmake_minimum_required(VERSION 3.28)

add_executable(companion_lifecycle_posix test_lifecycle_posix.cpp)
target_compile_features(companion_lifecycle_posix PRIVATE cxx_std_17)

find_package(Threads REQUIRED)
target_link_libraries(companion_lifecycle_posix PRIVATE
  grok-bot-lifecycle
  Qt6::Core
  Threads::Threads
)

# Behavioral regression at the real executable seam: hold the production
# QLockFile, invoke the production companion, and assert its lost-lock exit
# code for failed URL forwarding and for an invocation without a URL.
add_executable(companion_deep_link_exit test_deep_link_exit.cpp)
target_compile_features(companion_deep_link_exit PRIVATE cxx_std_17)
target_link_libraries(companion_deep_link_exit PRIVATE Qt6::Core)
add_test(
  NAME companion_deep_link_exit
  COMMAND companion_deep_link_exit $<TARGET_FILE:grok-bot-companion>
)
set_tests_properties(companion_deep_link_exit PROPERTIES TIMEOUT 30)

# One CTest per probe so failures point at the exact lifecycle contract.
# Every probe stays bounded internally; the CTest TIMEOUT is the outer
# fail-closed bound. Requires Linux (AF_UNIX, SO_PEERCRED, setsid).
foreach(case_name
    protocol_url_filter
    unix_socket_connect_bounded
    unix_socket_peercred
    owned_process_group_shutdown
    show_quit_decision
    cold_start_forward
)
  add_test(
    NAME companion_lifecycle_${case_name}
    COMMAND companion_lifecycle_posix --case ${case_name}
  )
  set_tests_properties(companion_lifecycle_${case_name} PROPERTIES TIMEOUT 60)
endforeach()
