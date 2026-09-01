# chatlens — development commands.
#
# For *using* the tool there is no need for make: install it once with
#
#     uv tool install chatlens          (or: pipx install chatlens)
#
# and then run `chatlens` in the folder holding your data. This Makefile is for
# working on the code: it builds an editable install in .venv/ so that an edit
# is picked up without reinstalling.
#
#   make            list the commands
#   make setup      prepare the development environment
#   make test       run the tests
#
# On Windows, where make is absent, every target below is one command:
#   py -m venv .venv
#   .venv\Scripts\python -m pip install -e ".[llm,topics]"
#   .venv\Scripts\python -m pytest tests   (or: python tests\test_merge.py)

PYTHON ?= python3
VENV   := .venv
PY     := $(VENV)/bin/python
PIP    := $(PY) -m pip

# Witness of the installation: it depends on pyproject.toml, so if the list of
# dependencies changes the next command updates them on its own.
DEPS := $(VENV)/.deps-installed

ARGS ?=

.DEFAULT_GOAL := help
.PHONY: help setup test check lint build clean clean-all dashboard docs \
        docs-serve demo

help: ## List the available commands
	@echo "chatlens — development"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "To use the tool rather than work on it:  uv tool install chatlens"

$(DEPS): pyproject.toml
	@test -d $(VENV) || { \
	    echo "==> Creating the virtual environment in $(VENV)/"; \
	    $(PYTHON) -m venv $(VENV); \
	    $(PIP) install --quiet --upgrade pip; \
	}
	@echo "==> Installing chatlens in editable mode, with every extra"
	@$(PIP) install --quiet -e ".[llm,topics]"
	@touch $(DEPS)

setup: $(DEPS) ## Prepare the development environment
	@echo ""
	@echo "Ready: $$($(PY) --version) in $(VENV)/"
	@echo "  $(VENV)/bin/chatlens --help"

test: $(DEPS) ## Run the tests (no network, no credentials)
	@$(PY) tests/test_merge.py
	@$(PY) tests/test_analysis.py
	@$(PY) tests/test_dashboard.py

check: test ## Tests plus a look at the installed state
	@$(PY) -m chatlens.cli status

dashboard: $(DEPS) ## Open the dashboard on the current folder
	@$(PY) -m chatlens.cli dashboard $(ARGS)

docs: $(DEPS) ## Regenerate docs/ and mkdocs.yml from README.md
	@$(PY) scripts/build_docs.py

docs-serve: docs ## Build the docs and serve them locally
	@$(PIP) install --quiet mkdocs-material
	@$(VENV)/bin/mkdocs serve

demo: $(DEPS) ## Write a synthetic workspace and analyse it
	@$(PY) -m chatlens.cli demo $(ARGS)

build: $(DEPS) ## Build the wheel and the source distribution
	@$(PIP) install --quiet build
	@$(PY) -m build

clean: ## Remove build artefacts and caches
	@rm -rf dist build src/*.egg-info
	@find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	@echo "==> cleaned"

clean-all: clean ## Also delete the virtual environment
	@rm -rf $(VENV)
	@echo "==> virtual environment removed"
