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

# Testimone dell'installazione: dipende da requirements.txt, quindi se l'elenco
# delle dipendenze cambia il prossimo comando le aggiorna da solo. Legare i
# comandi al solo interprete non basterebbe: l'ambiente esisterebbe gia' e una
# dipendenza aggiunta non arriverebbe mai, facendo fallire la pipeline con un
# errore di import che non spiega la causa.
DEPS := $(VENV)/.deps-installed

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
	@echo "  [CHIAVE] = richiede una chiave API configurata con: make keys"
	@echo ""
	@echo "Quale uso?"
	@echo "  make all    unione + misure automatiche. Non serve alcuna chiave,"
	@echo "              dura pochi secondi. E' il punto di partenza."
	@echo "  make full   le stesse cose piu' la rubrica di validazione e i"
	@echo "              topic. Serve una chiave e ci mette molto piu' tempo."
	@echo ""
	@echo "Percorso tipico:  make setup  ->  make all  ->  (make keys  ->  make full)"
	@echo "Opzioni extra:    make analyze ARGS=\"--llm-replicates 3\""

## --- Preparazione ----------------------------------------------------------

# I comandi dipendono da $(DEPS): l'ambiente viene creato e aggiornato da solo
# alla prima esecuzione e ogni volta che requirements.txt cambia.
$(DEPS): requirements.txt
	@test -d $(VENV) || { \
	    echo "==> Creo l'ambiente virtuale in $(VENV)/"; \
	    $(PYTHON) -m venv $(VENV); \
	    $(PIP) install --quiet --upgrade pip; \
	}
	@echo "==> Installo le dipendenze"
	@$(PIP) install --quiet -r requirements.txt
	@touch $(DEPS)

setup: $(DEPS) ## Prepara l'ambiente e installa le dipendenze
	@echo ""
	@echo "Ambiente pronto"
	@echo "  $$($(PY) --version) in $(VENV)/"
	@echo "  $$($(PIP) list --format=freeze 2>/dev/null | wc -l | tr -d ' ') pacchetti installati"
	@echo ""
	@echo "Prossimi passi:"
	@if [ -z "$$(ls input/*.csv 2>/dev/null)" ]; then \
	    echo "  1. metti in input/ i due CSV esportati da oTree"; \
	    echo "     (all_apps_wide_*.csv e ChatMessages_*.csv)"; \
	    echo "  2. make keys   solo se ti servono i topic o la rubrica"; \
	    echo "  3. make all"; \
	else \
	    echo "  i dati in input/ ci sono gia': puoi lanciare  make all"; \
	    echo "  (make keys   solo se ti servono i topic o la rubrica)"; \
	fi

keys: $(DEPS) ## Configura le chiavi API (guidato, verifica che funzionino)
	@$(PY) run.py keys

topicgpt: $(DEPS) ## Installa TopicGPT dal repository ufficiale
	@test -d "$(TOPICGPT_REPO)" \
	  || git clone https://github.com/chtmp223/topicGPT.git "$(TOPICGPT_REPO)"
	@$(PIP) install --quiet "$(TOPICGPT_REPO)"
	@echo "==> TopicGPT installato da $(TOPICGPT_REPO)"

## --- Diagnostica -----------------------------------------------------------

status: $(DEPS) ## Mostra input, output e chiavi configurate
	@$(PY) run.py status

test: $(DEPS) ## Esegue i test (senza rete ne credenziali)
	@$(PY) tests/test_merge.py
	@$(PY) tests/test_analysis.py

check: test status ## Test + stato dell'ambiente

## --- Analisi ---------------------------------------------------------------

all: $(DEPS) ## Unione + misure automatiche  [nessuna chiave, secondi]
	@$(PY) run.py all $(ARGS)

merge: $(DEPS) ## Solo unione di scelte e chat
	@$(PY) run.py merge $(ARGS)

analyze: $(DEPS) ## Solo misure automatiche, sui dati gia' uniti
	@$(PY) run.py analyze $(ARGS)

llm: $(DEPS) ## Misure + rubrica di validazione  [CHIAVE]
	@$(PY) run.py analyze --llm --llm-replicates 2 $(ARGS)

topics: $(DEPS) ## Misure + topic con TopicGPT  [CHIAVE]
	@$(PY) run.py analyze --topics --topicgpt-repo "$(TOPICGPT_REPO)" $(ARGS)

full: $(DEPS) ## Come all, piu' rubrica e topic  [CHIAVE, lento]
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
