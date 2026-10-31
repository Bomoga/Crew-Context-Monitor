# Progress

## T0.1 Toolchain probe and branch (done) 2026-10-30
- What: created `build/sim-dashboard`; recorded toolchain. `main` has no commits and the remote is empty, so the plan files could not be "committed on main"; they are committed here as the first commit instead (the "never commit to main" rule wins).
- Toolchain: python 3.11.9 (also 3.13.14 installed), node v24.14.0, npm 11.9.0, git 2.51.0.windows.1, GNU Make 4.4.1 (only via `C:\msys64\usr\bin`, not on PATH by default), gh present and authenticated (Bomoga). Missing: mosquitto, actionlint. Platform: Windows 11 with Git Bash.
- Verify: `git branch --show-current` prints `build/sim-dashboard`.
- Commit: see git log (chore(repo): record toolchain and start build branch)
- Notes: run make with `PATH="/c/msys64/usr/bin:$PATH"`. Windows venv uses `.venv/Scripts`, not `.venv/bin`; the Makefile must handle both (T0.2/T0.3). No mosquitto, so T2.7 will use amqtt or the skip path.
