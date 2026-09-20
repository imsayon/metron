.PHONY: test verify lint format-check typecheck secret-scan check

UV ?= uv

test:
	$(UV) run pytest

verify:
	$(UV) run pytest tests/common tests/verify

lint:
	$(UV) run ruff check .

format-check:
	$(UV) run ruff format --check .

typecheck:
	$(UV) run mypy metron/common metron/verify

secret-scan:
	gitleaks detect --source . --no-banner --redact

check: lint format-check typecheck test secret-scan
