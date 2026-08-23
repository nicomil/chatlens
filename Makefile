# Chat text analysis — main commands.
#
#   make            list the commands
#   make setup      prepare the environment
#   make all        merge the data and run the analysis
#
# The project has its own virtual environment in .venv/: there is no need to
# activate it, the Makefile takes care of that. On Windows, where make is
# absent, the same commands run as `python run.py <command>`.

PYTHON        ?= python3
VENV          := .venv
PY            := $(VENV)/bin/python
PIP           := $(PY) -m pip
TOPICGPT_REPO ?= $(HOME)/src/topicGPT

# Witness of the installation: it depends on requirements.txt, so if the list
# of dependencies changes the next command updates them on its own. Tying the
# commands to the interpreter alone would not do: the environment would already
# exist and an added dependency would never arrive, making the pipeline fail
# with an import error that does not explain the cause.
DEPS := $(VENV)/.deps-installed

# Extra options to pass to the pipeline, e.g.:
#   make analyze ARGS="--llm-replicates 3"
ARGS ?=

.DEFAULT_GOAL := help
.PHONY: help setup keys status check test all merge analyze llm topics full \
        topicgpt report runs prune dashboard clean clean-runs clean-all

## --- Help ------------------------------------------------------------------

help: ## List the available commands
	@echo "Chat text analysis"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  [KEY] = needs an API key configured with: make keys"
	@echo ""
	@echo "Which one do I use?"
	@echo "  make all    merge + automatic measures. No key needed, takes a"
	@echo "              few seconds. It is the starting point."
	@echo "  make full   the same plus the validation rubric and the topics."
	@echo "              Needs a key and takes far longer."
	@echo ""
	@echo "Typical path:  make setup  ->  make all  ->  (make keys  ->  make full)"
	@echo "Extra options: make analyze ARGS=\"--llm-replicates 3\""

## --- Preparation -----------------------------------------------------------

# The commands depend on $(DEPS): the environment is created and updated on its
# own at the first run and every time requirements.txt changes.
$(DEPS): requirements.txt
	@test -d $(VENV) || { \
	    echo "==> Creating the virtual environment in $(VENV)/"; \
	    $(PYTHON) -m venv $(VENV); \
	    $(PIP) install --quiet --upgrade pip; \
	}
	@echo "==> Installing the dependencies"
	@$(PIP) install --quiet -r requirements.txt
	@touch $(DEPS)

setup: $(DEPS) ## Prepare the environment and install the dependencies
	@echo ""
	@echo "Environment ready"
	@echo "  $$($(PY) --version) in $(VENV)/"
	@echo "  $$($(PIP) list --format=freeze 2>/dev/null | wc -l | tr -d ' ') packages installed"
	@echo ""
	@echo "Next steps:"
	@if [ -z "$$(ls input/*.csv 2>/dev/null)" ]; then \
	    echo "  1. put the two CSVs exported from oTree in input/"; \
	    echo "     (all_apps_wide_*.csv and ChatMessages_*.csv)"; \
	    echo "  2. make keys   only if you need the topics or the rubric"; \
	    echo "  3. make all"; \
	else \
	    echo "  the data in input/ is already there: you can run  make all"; \
	    echo "  (make keys   only if you need the topics or the rubric)"; \
	fi

keys: $(DEPS) ## Configure the API keys (guided, checks that they work)
	@$(PY) run.py keys

topicgpt: $(DEPS) ## Install TopicGPT from the official repository
	@test -d "$(TOPICGPT_REPO)" \
	  || git clone https://github.com/chtmp223/topicGPT.git "$(TOPICGPT_REPO)"
	@echo "==> Installing TopicGPT (heavy dependencies, may take minutes)"
	@echo "    The warning about google-cloud-aiplatform and the 'all' extra is harmless."
	$(PIP) install "$(TOPICGPT_REPO)"
	@$(PY) -c "import topicgpt_python" \
	  || { echo "ERROR: installation failed, see the messages above"; exit 1; }
	@test -f "$(TOPICGPT_REPO)/prompt/generation_1.txt" \
	  || { echo "ERROR: prompt files missing in $(TOPICGPT_REPO)/prompt/"; exit 1; }
	@echo "==> TopicGPT installed and verified ($(TOPICGPT_REPO))"

## --- Diagnostics -----------------------------------------------------------

report: $(DEPS) ## Regenerate the readable summary (md + html) and open it
	@$(PY) run.py report
	@command -v open >/dev/null && open output/*_report.html || true

dashboard: $(DEPS) ## Open the dashboard to launch runs from the browser
	@$(PY) run.py dashboard

runs: $(DEPS) ## List the archived runs
	@$(PY) run.py runs

status: $(DEPS) ## Show input, output and configured keys
	@$(PY) run.py status

test: $(DEPS) ## Run the tests (no network, no credentials)
	@$(PY) tests/test_merge.py
	@$(PY) tests/test_analysis.py
	@$(PY) tests/test_dashboard.py

check: test status ## Tests + state of the environment

## --- Analysis --------------------------------------------------------------

all: $(DEPS) ## Merge + automatic measures  [no key, seconds]
	@$(PY) run.py all $(ARGS)

merge: $(DEPS) ## Merge of choices and chat only
	@$(PY) run.py merge $(ARGS)

analyze: $(DEPS) ## Automatic measures only, on the data already merged
	@$(PY) run.py analyze $(ARGS)

llm: $(DEPS) ## Measures + validation rubric  [KEY]
	@$(PY) run.py analyze --llm --llm-replicates 2 $(ARGS)

topics: $(DEPS) ## Measures + topics with TopicGPT  [KEY]
	@$(PY) run.py analyze --topics --topicgpt-repo "$(TOPICGPT_REPO)" $(ARGS)

full: $(DEPS) ## Like all, plus rubric and topics  [KEY, slow]
	@$(PY) run.py all --llm --llm-replicates 2 \
	    --topics --topicgpt-repo "$(TOPICGPT_REPO)" $(ARGS)

## --- Cleaning --------------------------------------------------------------

clean: ## Delete the latest result (archive, input and keys are kept)
	@find output -mindepth 1 -maxdepth 1 ! -name '.gitkeep' ! -name 'runs' \
	   ! -name 'cache' -exec rm -rf {} +
	@find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	@echo "==> output/ emptied (runs/ and cache/ kept)"

KEEP ?= 2

prune: $(DEPS) ## Keep the last runs and delete the others (KEEP=2)
	@$(PY) run.py runs --prune $(KEEP)

clean-runs: ## Delete the whole archive of runs
	@rm -rf output/runs
	@echo "==> archive of runs removed"

clean-all: clean ## Also delete the virtual environment
	@rm -rf $(VENV)
	@echo "==> virtual environment removed"
