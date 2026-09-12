# KDE Tray Companion Specification

## Purpose

Define required KDE tray behavior; ADR 0003 remains authoritative.

## Requirements

### Requirement: Provide a mandatory tray companion

The application MUST ship a separate Qt/KF6 companion providing a KDE StatusNotifierItem and access to `org.kde.StatusNotifierWatcher`. Show MUST relaunch or reveal the window; Quit MUST terminate both processes. A trayless fallback MUST NOT be provided.

#### Scenario: Tray actions control the application

- GIVEN the companion and main application run with a StatusNotifierWatcher
- WHEN the user selects Show and then Quit
- THEN Show relaunches or reveals the window and Quit terminates both

#### Scenario: Tray availability is missing

- GIVEN the KDE tray service or companion cannot be provided
- WHEN packaging or runtime validation runs
- THEN validation fails rather than accepting a trayless application
