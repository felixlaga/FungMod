# FungMod developer and reproduction entry points.
# Run `make help` for a summary.

PYTHON ?= python
PIP ?= $(PYTHON) -m pip

.DEFAULT_GOAL := help

.PHONY: help install install-dev lint type test test-cov docs docs-serve \
        build package-check reproduce reproduce-quick check clean container

help: ## Show this help.
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install the package (runtime dependencies only).
	$(PIP) install .

install-dev: ## Install an editable checkout with dev, docs, and notebook extras.
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev,docs,notebooks]"

lint: ## Run ruff.
	$(PYTHON) -m ruff check src tests

type: ## Run pyright against the active interpreter.
	$(PYTHON) -m pyright --pythonpath "$$($(PYTHON) -c 'import sys; print(sys.executable)')"

test: ## Run the test suite.
	$(PYTHON) -m pytest

test-cov: ## Run the test suite with coverage (enforces the 80% gate).
	$(PYTHON) -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml

docs: ## Build the documentation strictly (fails on warnings).
	$(PYTHON) -m mkdocs build --strict

docs-serve: ## Serve the documentation locally with live reload.
	$(PYTHON) -m mkdocs serve

build: ## Build the wheel and source distribution.
	$(PYTHON) -m build

package-check: build ## Build and verify distribution metadata and resources.
	$(PYTHON) scripts/check_packaged_resources.py
	$(PYTHON) scripts/check_built_distribution_resources.py dist/fungmod-*.whl
	$(PYTHON) -m twine check dist/*

check: lint type test-cov docs ## Run every quality gate (lint, types, tests+coverage, docs).

reproduce: ## Deterministically regenerate the headline scientific artifacts.
	$(PYTHON) scripts/reproduce.py

reproduce-quick: ## Fast smoke reproduction (few samples).
	$(PYTHON) scripts/reproduce.py --quick

container: ## Build the Docker image.
	docker build -t fungmod:latest .

clean: ## Remove build, cache, and reproduction output artifacts.
	rm -rf build dist src/*.egg-info .pytest_cache .ruff_cache site \
	       outputs/reproduction coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
