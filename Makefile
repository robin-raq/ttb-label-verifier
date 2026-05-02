.PHONY: install test test-smoke ci-cov-comparators ci-cov-verdict ci-cov-api eval lint format

install:
	pip install -e ".[dev]"

test:
	pytest -q

test-smoke:
	pytest tests/test_smoke.py -q

# Phase B agents extend these per SPEC §7.3
ci-cov-comparators:
	pytest tests/comparators -q --cov=app.comparators --cov-report=term-missing --cov-fail-under=95

ci-cov-verdict:
	pytest tests/test_verdict.py -q --cov=app.verdict --cov-report=term-missing --cov-fail-under=90

ci-cov-api:
	pytest tests/api tests/contract tests/adversarial -q --cov=app.api --cov-report=term-missing --cov-fail-under=80

eval:
	@echo "Eval harness will be added by Phase B agent B2."

lint:
	ruff check app tests

format:
	ruff format app tests
