# Testing

Workspace command: `python3 tools/test.py`. It runs two layers and fails
closed: a missing dependency, a failing layer, or a layer with zero
discovered tests fails the whole command. Nothing is silently skipped.

| Layer | What runs | Fail-closed rule |
|---|---|---|
| `python` | `python -m unittest discover -s tests` | Nonzero exit or `Ran 0 tests` fails |
| `ctest` | `cmake -S . -B <tmp>`, `cmake --build`, `ctest` | Missing cmake/ctest, any failing step, or `No tests were found` fails |

## Prerequisites

Python 3.12+ (stdlib only), CMake 3.28+, CTest. Later work units add
Qt/KF6, DBus, and dual-arch SDK checks through this same command.

## Focused runs

```bash
python3 tools/test.py                        # full workspace gate
python3 -m unittest discover -s tests -v     # Python layer only
```

## CTest wiring

`CMakeLists.txt` currently defines one wiring test,
`bootstrap_ctest_wiring`. It exists so the CTest layer is exercised
rather than skipped while no product C++ tests exist yet; companion
tests extend it in later work units.

## Evidence labels

Per the distribution-docs spec, label runtime evidence as mock SNI or
real KDE, and build evidence as single-arch or dual-arch. Neither mock
nor single-arch evidence counts as full acceptance.
