# Analisi del testo delle chat — comandi principali.
#
#   make            elenco dei comandi
#   make setup      prepara l'ambiente
#   make all        unisce i dati ed esegue l'analisi
#
# Il progetto ha il proprio ambiente virtuale in .venv/: non serve attivarlo,
# ci pensa il Makefile. Su Windows, dove make non c'e', gli stessi comandi si
# eseguono con `python run.py <comando>`.

PYTHON        ?= python3
VENV          := .venv
PY            := $(VENV)/bin/python
PIP           := $(PY) -m pip
TOPICGPT_REPO ?= $(HOME)/src/topicGPT

# Opzioni aggiuntive da passare alla pipeline, es:
#   make analyze ARGS="--llm-replicates 3"
ARGS ?=

.DEFAULT_GOAL := help
.PHONY: help setup keys status check test all merge analyze llm topics full \
        topicgpt clean clean-all

## --- Aiuto -----------------------------------------------------------------

help: ## Elenca i comandi disponibili
	@echo "Analisi del testo delle chat"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Percorso tipico:  make setup  ->  make keys  ->  make all"
	@echo "Opzioni extra:    make analyze ARGS=\"--llm-replicates 3\""

## --- Preparazione ----------------------------------------------------------

# L'ambiente virtuale e' un file-obiettivo: i comandi che ne dipendono lo
# creano da soli la prima volta, senza che serva ricordarsene.
$(PY):
	@echo "==> Creo l'ambiente virtuale in $(VENV)/"
	$(PYTHON) -m venv $(VENV)
	@$(PIP) install --quiet --upgrade pip
	@echo "==> Installo le dipendenze"
	@$(PIP) install --quiet -r requirements.txt
	@echo "==> Ambiente pronto"

setup: $(PY) ## Prepara l'ambiente e installa le dipendenze
	@echo ""
	@echo "Prossimi passi:"
	@echo "  1. metti i due CSV esportati da oTree in input/"
	@echo "  2. make keys     (solo se servono topic o rubrica di validazione)"
	@echo "  3. make all"

keys: $(PY) ## Configura le chiavi API (guidato, verifica che funzionino)
	@$(PY) run.py keys

topicgpt: $(PY) ## Installa TopicGPT dal repository ufficiale
	@test -d "$(TOPICGPT_REPO)" \
	  || git clone https://github.com/chtmp223/topicGPT.git "$(TOPICGPT_REPO)"
	@$(PIP) install --quiet "$(TOPICGPT_REPO)"
	@echo "==> TopicGPT installato da $(TOPICGPT_REPO)"

## --- Diagnostica -----------------------------------------------------------

status: $(PY) ## Mostra input, output e chiavi configurate
	@$(PY) run.py status

test: $(PY) ## Esegue i test (senza rete ne credenziali)
	@$(PY) tests/test_merge.py
	@$(PY) tests/test_analysis.py

check: test status ## Test + stato dell'ambiente

## --- Analisi ---------------------------------------------------------------

all: $(PY) ## Unisce i dati ed esegue l'analisi (il caso normale)
	@$(PY) run.py all $(ARGS)

merge: $(PY) ## Solo unione di scelte e chat
	@$(PY) run.py merge $(ARGS)

analyze: $(PY) ## Solo analisi del testo
	@$(PY) run.py analyze $(ARGS)

llm: $(PY) ## Analisi + rubrica di validazione (richiede una chiave)
	@$(PY) run.py analyze --llm --llm-replicates 2 $(ARGS)

topics: $(PY) ## Analisi + topic con TopicGPT (richiede una chiave)
	@$(PY) run.py analyze --topics --topicgpt-repo "$(TOPICGPT_REPO)" $(ARGS)

full: $(PY) ## Tutto: unione, misure, rubrica e topic
	@$(PY) run.py all --llm --llm-replicates 2 \
	    --topics --topicgpt-repo "$(TOPICGPT_REPO)" $(ARGS)

## --- Pulizia ---------------------------------------------------------------

clean: ## Cancella i risultati prodotti (input e chiavi restano)
	@find output -mindepth 1 ! -name '.gitkeep' -delete
	@find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	@echo "==> output/ svuotato"

clean-all: clean ## Cancella anche l'ambiente virtuale
	@rm -rf $(VENV)
	@echo "==> ambiente virtuale rimosso"
