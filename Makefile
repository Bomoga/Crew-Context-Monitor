# Crew Context Monitor dev tasks. On Windows, run with GNU Make from
# C:\msys64\usr\bin on PATH (Git Bash).
.PHONY: check clean

check:
	@echo "check: ok"

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache
