# Changelog

Notable user-visible changes are recorded here.

## Unreleased

### Fixed

- Settings files written by another Vulture version no longer block startup.
  Unknown entries, such as the experimental notification placement setting, are
  now ignored instead of failing with a validation error.

### Changed

- Break reminders now request a native notification timeout matching the
  configured activity duration. Combined reminders request the longest
  included duration; the operating system still controls actual lifetime and
  placement.
