# Changelog

Notable user-visible changes are recorded here.

## Unreleased

### Changed

- Break reminders now request a native notification timeout matching the
  configured activity duration. Combined reminders request the longest
  included duration; the operating system still controls actual lifetime and
  placement.
