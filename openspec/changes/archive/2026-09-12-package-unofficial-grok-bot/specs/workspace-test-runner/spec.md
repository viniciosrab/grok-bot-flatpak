# Workspace Test Runner Specification

## Purpose

Define the test entry point and fail-closed bootstrap.

## Requirements

### Requirement: Run workspace validation through one entry point

The workspace MUST provide `python3 tools/test.py`. The runner SHALL bootstrap and execute CTest, fail when setup or any test fails, and succeed only when all checks pass. `strict_tdd` MUST remain disabled until usable.

#### Scenario: Tests pass from a clean workspace

- GIVEN test dependencies can be bootstrapped
- WHEN a contributor runs `python3 tools/test.py`
- THEN CTest and checks execute, succeeding only after all pass

#### Scenario: Bootstrap or test fails

- GIVEN dependency setup or a required check fails
- WHEN the runner executes
- THEN it exits unsuccessfully and reports no passing workspace
