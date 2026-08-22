# Analisi del testo delle chat

Progetto autonomo: estrae dalle conversazioni dell'esperimento i **topic** (con
TopicGPT, Pham et al. 2024) e le **misure del linguaggio** — volume, tono
emotivo, sentiment, pensiero analitico, Clout, Authenticity — a livello di
coppia e di gruppo, e le innesta sui dataset delle scelte.

Non dipende dal codice dell'esperimento: si può copiare altrove e continua a
funzionare. Gli unici legami sono i due CSV in `input/`.

```
text_analysis/
├── Makefile          i comandi principali
├── run.py            il punto di ingresso vero e proprio
├── input/            i CSV esportati da oTree  ← metti qui i dati
├── output/           tutto ciò che viene prodotto
├── src/              il codice dei passi di analisi
├── tests/            verifica degli strumenti
├── .env              le chiavi API (mai sotto controllo di versione)
└── requirements.txt
```

## Le due cose da sapere

**I file di input non si passano da riga di comando.** Si mettono in `input/` e
vengono riconosciuti dal nome. Per questo la procedura si riduce a un comando.

**Tutto quello che serve sta in questa cartella**, chiavi comprese: `input/` e
`output/` sono esclusi dal controllo di versione perché contengono ID Prolific e
testi di chat.

```bash
make setup    # una volta sola: crea l'ambiente e installa le dipendenze
make all      # unisce i dati ed esegue l'analisi
```

`make` da solo elenca tutti i comandi. I principali:

| Comando | Cosa fa | Chiave API |
|---|---|---|
| `make setup` | prepara l'ambiente virtuale del progetto | — |
| `make keys` | configura le chiavi API, guidato | — |
| `make all` | unione + misure automatiche, pochi secondi | **no** |
| `make merge` / `make analyze` | i due passi separati | no |
| `make llm` | misure + rubrica di validazione | sì |
| `make topics` | misure + topic con TopicGPT | sì |
| `make full` | come `all`, più rubrica e topic | sì |
| `make report` | rigenera il riassunto leggibile e lo apre | — |
| `make runs` | elenca le esecuzioni archiviate | — |
| `make status` | cosa c'è in input, in output e fra le chiavi | — |
| `make test` / `make check` | verifica gli strumenti | — |
| `make clean` | svuota l'ultimo risultato; archivio e cache restano | — |

**`all` e `full` non sono sinonimi.** `all` vuol dire «entrambi i *passi*» —
unione più analisi — in contrapposizione a `merge` e `analyze` presi
singolarmente: esegue solo le misure automatiche, non richiede alcuna chiave e
dura pochi secondi. `full` fa le stesse cose e in più la rubrica di validazione
e i topic, quindi richiede una chiave e impiega molto più tempo. Si comincia da
`all`; a `full` si passa quando le chiavi ci sono.

Per le opzioni meno comuni: `make analyze ARGS="--llm-replicates 3"`.

**Senza make** — su Windows, o per preferenza — gli stessi comandi sono
`python run.py <comando>`: `run.py all`, `run.py keys`, `run.py status` e così
via. Il Makefile non fa altro che chiamarli, dopo essersi assicurato che
l'ambiente esista.

## Indice

1. [Cosa fa, in breve](#1-cosa-fa-in-breve)
2. [Installazione](#2-installazione)
3. [Chiavi API](#3-chiavi-api)
4. [La procedura di analisi](#4-la-procedura-di-analisi)
5. [I file prodotti](#5-i-file-prodotti)
6. [Prima di analizzare: tre filtri](#6-prima-di-analizzare-tre-filtri)
7. [Come sono costruite le misure](#7-come-sono-costruite-le-misure)
8. [TopicGPT](#8-topicgpt)
9. [Costi e volumi](#9-costi-e-volumi)
10. [Se qualcosa non torna](#10-se-qualcosa-non-torna)
11. [Verifica degli strumenti](#11-verifica-degli-strumenti)
12. [Risultati sul pilota](#12-risultati-sul-pilota)

---

## 1. Cosa fa, in breve

Tre stadi indipendenti, attivabili separatamente.

| Stadio | Opzione | Serve una credenziale? |
|---|---|---|
| Misure testuali deterministiche | (sempre attivo) | **no** |
| Rubrica di validazione | `--llm` | una a scelta fra OpenAI, Anthropic o un modello locale |
| TopicGPT | `--topics` | dipende dal backend |

Il primo stadio gira con la sola libreria standard di Python: si può eseguire
subito, senza procurarsi nulla. Gli altri due servono rispettivamente a
validare le misure e a estrarre i topic.

**Serve una sola chiave in tutto.** La rubrica di validazione non è legata a un
fornitore specifico: se si usa già OpenAI per TopicGPT, la stessa chiave copre
anche quello stadio.

Tutto il codice dei passi di analisi sta in `src/`; il punto di ingresso è
`run.py`.

---

## 2. Installazione

Dalla cartella del progetto, una volta sola:

```bash
make setup
```

Crea l'ambiente virtuale in `.venv/` e installa le dipendenze. Non serve
attivarlo: se ne occupa il Makefile. Senza make: `pip install -r
requirements.txt`.

Installa il necessario per il sentiment e per i client delle API. Le misure
deterministiche funzionerebbero anche senza, ma il sentiment ripiegherebbe su
una versione più povera, dichiarandolo nella colonna `sentiment_backend`.

**Solo se servono i topic**, va anche clonato il repository di TopicGPT:

```bash
make topicgpt
```

Clona il repository in `~/src/topicGPT` e lo installa; con
`make topicgpt TOPICGPT_REPO=<percorso>` si sceglie dove.

Due avvertenze sul perché si installa dal repository e non da PyPI: i file di
prompt fanno parte del metodo e **non sono dentro il pacchetto pubblicato**; e
la release 0.2.7 su PyPI importa vLLM al primo livello, dipendenza che su macOS
senza GPU non si installa, mentre il ramo `main` l'ha già resa opzionale.

---

## 3. Chiavi API

| Chiave | A cosa serve | Obbligatoria? |
|---|---|---|
| `OPENAI_API_KEY` | TopicGPT **e**, volendo, la rubrica di validazione | solo per i topic con OpenAI |
| `ANTHROPIC_API_KEY` | la rubrica di validazione, in alternativa a OpenAI | **no, facoltativa** |

### Configurarle

Un solo comando, identico su macOS, Windows e Linux:

```bash
python run.py keys
```

Chiede le chiavi una per una. Mentre le incolli **il testo non compare a
schermo**: è normale, non è il terminale bloccato. Invio dopo ognuna; invio a
vuoto salta quella chiave o lascia invariata quella già presente.

Al termine lo script fa tre cose da solo:

1. salva le chiavi in `.env` nella cartella del progetto;
2. verifica che git lo stia davvero ignorando, e se non lo fa si offre di
   sistemare `.gitignore` **prima** di scrivere qualsiasi cosa;
3. contatta i servizi per confermare che le chiavi funzionino, così un errore
   di copia-incolla emerge subito e non tre giorni dopo.

Esito corretto:

```
Salvato in /.../.env
Permessi ristretti al solo proprietario (600).

Verifica delle chiavi:
  OK   OpenAI: chiave valida, 87 modelli disponibili
```

Se una chiave è sbagliata lo dice senza ambiguità: `FAIL OpenAI: chiave
rifiutata (HTTP 401)`.

Fatto questo non serve altro: la pipeline le carica da sola a ogni esecuzione.

### Comandi di controllo

```bash
python run.py status        # cosa è configurato, senza toccare nulla
python run.py keys          # riconfigura o verifica le chiavi
```

`run.py status` non stampa mai le chiavi, solo se ci sono.

### Quale fornitore viene usato

La pipeline sceglie da sola in base a quello che trova, e lo dichiara prima di
partire:

```
Rubrica LLM...
  fornitore: OpenAI
```

Per forzare la scelta: `--llm-provider openai|anthropic|ollama`.

### Due avvertenze

**`.env` non va mai messo sotto controllo di versione.** Il repository
di questo progetto è pubblico. Lo script lo verifica prima di scrivere, ma vale
la pena saperlo: non aggiungerlo mai a mano a un commit, e non mandare le
chiavi via chat o email.

**Una variabile d'ambiente già impostata ha sempre la precedenza sul file**, per
chi preferisce gestirle a modo proprio. Per rimuovere tutto basta cancellare
`.env`: nessuna impostazione di sistema viene toccata.

### Un'alternativa gratuita

TopicGPT e la rubrica accettano anche modelli eseguiti in locale, che non
richiedono alcuna chiave:

```bash
ollama pull llama3
```

Poi si aggiunge `--topicgpt-api ollama --topicgpt-model llama3` oppure
`--llm-provider ollama`. Il rovescio della medaglia: TopicGPT vive della
qualità delle etichette che il modello produce, e il paper usa GPT-4. Con un
modello locale di piccola taglia la pipeline gira lo stesso, ma i topic
risultano più poveri. È la strada giusta per un collaudo, non per i risultati
da pubblicare.

---

## 4. La procedura di analisi

### Passo 1 — Scaricare gli export da oTree

Dall'interfaccia di amministrazione, sezione **Data**, servono due file:

| Export | Nome tipico |
|---|---|
| All apps — wide | `all_apps_wide_<data>.csv` |
| Chat messages | `ChatMessages_<data>.csv` |

Vanno scaricati anche i due export custom della randomizzazione (**RCT slots** e
**RCT assignments**): non servono a questa procedura, ma non sono ricostruibili
a posteriori e vanno conservati insieme agli altri.

### Passo 2 — Unire scelte e chat

```bash
python run.py merge
```

Qui vengono già costruite le variabili dell'esperimento: persuasione, coerenza
segnale-scelta, inganno strategico, payoff di gruppo e i flag di validità delle
triadi.

**Chi entra nell'analisi.** Vengono tenuti i partecipanti che soddisfano due
condizioni:

- hanno un identificativo Prolific valido in `participant.label`, il che
  scarta le sessioni di collaudo interne;
- hanno fatto parte di una triade, il che tiene solo chi ha potuto comunicare.

Chi è stato poi **escluso per inattività resta nel dataset**: ha comunicato, e
la sua esclusione dalle analisi principali si governa con `group_valid`, non
togliendolo dai dati. Con `--keep-all` non si filtra nulla, per ispezionare
l'export grezzo.

**Cosa controllare nel riepilogo a schermo.** Il comando stampa quanti
partecipanti c'erano nell'export, quanti ne ha esclusi e per quale motivo,
quante triadi ha ricostruito e quanti messaggi ha analizzato. Il conto dei
messaggi deve tornare: quelli di partecipanti esclusi più quelli analizzati
fanno il totale dell'export. Se non torna, in coda compaiono righe di avviso
che spiegano quali non sono stati ricondotti a un partecipante.

### Passo 3 — Analisi del testo

**Solo misure automatiche** — nessuna chiave necessaria, pochi secondi:

```bash
python run.py analyze
```

**Con la rubrica di validazione:**

```bash
python run.py analyze --llm --llm-replicates 2
```

`--llm-replicates 2` fa valutare ogni testo due volte in chiamate indipendenti,
così la dispersione fra le due finisce nel dataset come stima dell'errore di
misura.

**Con i topic:**

```bash
python run.py analyze --topics --topicgpt-repo ~/src/topicGPT
```

**Tutto insieme:** si combinano le opzioni dei due comandi precedenti.

---

## 5. I file prodotti

Tutto sotto `output/`.

### Cosa succede rilanciando

`output/` contiene sempre **l'ultima** esecuzione, a percorsi fissi: è quello
che si apre e che si porta in Stata. Ogni esecuzione viene però anche copiata in
`output/runs/<data_ora>/`, con i due dataset, il rapporto, l'elenco dei topic
usati e un `run.json` con i parametri.

Serve perché due esecuzioni non producono gli stessi file: una senza `--llm`
riscrive i dataset **senza** le colonne della rubrica, e senza archivio quel
lavoro sparirebbe dai file finali pur restando in cache.

```bash
make runs      # elenca le esecuzioni, con gli stadi e i parametri di ciascuna
make clean     # svuota l'ultimo risultato; archivio e cache restano
make clean-runs  # cancella l'archivio
```

Le misure intermedie non vengono archiviate: si rigenerano.

### Il riassunto dell'esecuzione

Ogni esecuzione produce `output/<nome>_report.md` e `<nome>_report.html`: una
pagina sola con copertura del campione, esiti del gioco, variabili
comportamentali, misure del linguaggio e — quando gli stadi sono stati
eseguiti — rubrica e topic. Serve a capire com'è andata senza aprire CSV da
trecento colonne. L'HTML è autosufficiente: si apre con un doppio clic e si può
mandare a qualcuno.

Le sezioni degli stadi non eseguiti non compaiono. I confronti fra trattamenti
sono descrittivi per scelta: su numeri come quelli del pilota servono a
verificare che la pipeline produca risultati sensati, non a trarne conclusioni.
Per rigenerarlo senza rifare l'analisi: `make report`.

### Da portare in Stata

| File | Unità di osservazione |
|---|---|
| `..._chat_by_partner_nlp.csv` | coppia ordinata i→j, sei per triade |
| `..._chat_aggregated_nlp.csv` | il partecipante |

Le misure del testo hanno un prefisso che dice a quale conversazione si
riferiscono:

| Prefisso | Contenuto |
|---|---|
| `nlp_sent_*` | i messaggi **inviati** dal soggetto (al partner nel file per coppia, a tutto il gruppo nel file per partecipante) |
| `nlp_recv_*` | quelli **ricevuti** |
| `nlp_dyad_*` | l'intera conversazione della coppia |
| `nlp_group_*` | l'intera conversazione della triade |

La distinzione fra inviato e ricevuto non è cosmetica: nella persuasione conta
il linguaggio di chi parla, quindi le regressioni sulla persuasione vanno fatte
sulle colonne `nlp_sent_*`.

Colonne principali di ciascun blocco: `n_messages`, `wc`,
`mean_words_per_message`, `type_token_ratio`, `duration_seconds`,
`median_gap_seconds`, le terne `analytic_cdi` / `analytic_z` / `analytic_100` e
analoghe per `clout`, `authenticity`, `tone`, più `sentiment_compound_mean` e
le percentuali di categoria (`pct_i`, `pct_we`, `pct_you`, `pct_negate`,
`pct_posemo`, `pct_negemo`, `pct_commitment`, `pct_exclusive`, `pct_social`).

Con gli stadi 2 e 3 attivi si aggiungono `llm_analytic`, `llm_clout`,
`llm_authenticity`, `llm_tone` con i rispettivi `_sd`, i flag
`llm_contains_support_commitment` e `llm_contains_support_request`, e
`nlp_*_topics` / `nlp_*_topic_primary` / `nlp_*_n_topics`.

### Variabili dell'esperimento, costruite al passo 2

| Variabile | Definizione |
|---|---|
| `persuasion_ij` | i promette sostegno a j **e** j sceglie effettivamente i. Sei osservazioni per gioco |
| `C_ij`, `cc_i` | coerenza fra segnale finale e scelta, per coppia e in media: 1, 0.5 o 0 |
| `strategic_deception` | promette sostegno a entrambi, poi non sostiene nessuno |
| `group_valid` | 0 se la triade è interrotta o se anche un solo membro ha fatto scadere un timer |
| `group_total_payoff` | base per Efficiency, nella versione teorica e in quella pagata |

### File intermedi

`..._messages_long.csv` (un messaggio per riga), `..._messages_nlp.csv` (lo
stesso con conteggi e sentiment) e `..._features_<livello>.csv` per i quattro
livelli di aggregazione. Servono ai controlli e alle analisi a livelli diversi;
non servono per Stata.

---

## 6. Prima di analizzare: tre filtri

**`group_valid == 1`** — esclude le triadi interrotte e quelle in cui almeno un
membro ha fatto scadere un timer, come stabilito. Il campione completo resta
disponibile per i controlli di robustezza. La colonna si chiama così in
entrambi i file.

**`low_language_flag == 0`** — esclude il testo che non è lingua. Serve perché
le stringhe di tastiera risultano paradossalmente *massimamente analitiche*:
l'indice sottrae le parole funzionali, e un testo che non ne contiene non
subisce alcuna sottrazione. Sul pilota i gruppi di sole stringhe di prova
avevano punteggio mediano 93 contro 43 dei gruppi veri.

Il flag ha il prefisso del blocco a cui si riferisce, quindi va usato quello
coerente con le misure che si stanno analizzando:
`nlp_sent_low_language_flag`, `nlp_dyad_low_language_flag`,
`nlp_group_low_language_flag`. Su unità molto corte la soglia non scatta,
quindi al livello diadico va letto insieme a `nlp_sent_wc`.

**`nlp_sent_wc > 0`** (o il `wc` del blocco in uso) — le unità senza testo hanno
gli indici **vuoti** per costruzione, non a zero: senza questo filtro
entrerebbero nelle medie come valori mancanti anziché come assenza di
conversazione.

---

## 7. Come sono costruite le misure

Questa sezione serve a chi scrive il paper: dice cosa è replica esatta e cosa è
approssimazione.

### Le misure LIWC senza LIWC

Il punto che rende la cosa possibile: **Analytic, Clout e Authenticity non
dipendono da dizionari di contenuto proprietari.** Si reggono sulle *function
words* — articoli, preposizioni, pronomi, ausiliari, congiunzioni, negazioni —
che in inglese sono classi chiuse e di dominio pubblico. Quello che LIWC vende è
il software e la taratura, non la lingua inglese.

**Analytic è una replica.** Il Categorical-Dynamic Index è pubblicato per esteso
in Pennebaker, Chung, Frazee, Lavergne & Beaver (2014), *PLOS ONE*:

```
CDI = 30 + article + prep − ppron − ipron − auxverb − conj − adverb − negate
```

con ogni termine in percentuale sul totale delle parole. È implementato alla
lettera, e un test ne ricalcola il valore a mano.

**Clout e Authenticity sono indici *in stile* LIWC.** I costrutti sono
pubblicati — Clout su Kacewicz, Pennebaker, Davis, Jeon & Graesser (2014),
Authenticity sull'indice di menzogna di Newman, Pennebaker, Berry & Richards
(2003) — ma i pesi esatti di LIWC-22 non lo sono. Qui sono composti a pesi
uguali, con i segni presi dalla letteratura:

- Clout ↑ con `we`, `you` e riferimenti sociali; ↓ con `I`, negazioni, volgarità;
- Authenticity ↑ con `I` e parole di differenziazione (*but*, *except*,
  *without*); ↓ con emozione negativa e verbi di movimento.

Nel dataset si chiamano `clout_raw` / `clout_z` / `clout_100`, **mai** «LIWC
Clout». In pre-registrazione vanno dichiarati come *LIWC-style measures
computed from published formulas*.

**La validazione convergente.** Lo stadio 2 fa valutare le stesse trascrizioni a
un modello linguistico con una rubrica esplicita, su scala 0-100 per gli stessi
quattro costrutti. Le due strade sono metodologicamente indipendenti — una
conta function words, l'altra legge il testo — quindi la correlazione fra
`clout_100` e `llm_clout` è evidenza di validità convergente. Se divergono, va
riportato: è un risultato, non un guasto.

**Sentiment.** VADER, open source e validato, è la misura principale
(`sentiment_compound`). Senza la libreria il codice ripiega su conteggi da
dizionario e lo dichiara in `sentiment_backend`, così la provenienza resta
tracciata riga per riga.

### Tre decisioni che cambiano i numeri

**Gli indici si calcolano sui conteggi sommati**, non come media di percentuali
per messaggio. I turni di chat sono cortissimi: una percentuale calcolata su
cinque parole assume pochi valori distinti ed è dominata dal rumore, e la media
di quelle percentuali non è la percentuale del testo complessivo. La pipeline
estrae *conteggi* a livello di messaggio e calcola gli *indici* solo sull'unità
di analisi vera. Un test verifica che il CDI di un gruppo coincida con quello
del testo unito dei suoi messaggi.

**Il tono emotivo usa la differenza fra percentuali**, non il rapporto interno
alle parole emotive. La formulazione a rapporto — `(pos − neg) / (pos + neg)` —
salta a ±100 appena il testo contiene una sola parola emotiva, cosa che su
messaggi di chat accade quasi sempre; nella prima stesura il valore mediano di
gruppo era esattamente 100, cioè degenerazione e non segnale. La misura usata è
`pct_posemo − pct_negemo`; il rapporto resta disponibile come `tone_balance`,
da leggere solo dove `has_emotion_words` vale 1.

**La standardizzazione è sul campione.** LIWC restituisce le misure su scala
0-100 perché le standardizza su un corpus di riferimento proprietario. Qui la
standardizzazione avviene sul campione in analisi: i valori sono confrontabili
*fra unità dello stesso studio* — cioè fra trattamenti, che è l'uso previsto —
ma non con punteggi LIWC pubblicati altrove.

---

## 8. TopicGPT

L'adattatore **non riscrive l'algoritmo**: prepara l'input nel formato atteso,
invoca le funzioni ufficiali nell'ordine previsto dal paper — generazione dei
topic di primo livello, raffinamento, assegnazione, correzione — e ricompone
l'output sulle chiavi dell'esperimento.

**Unità di analisi: due, non una.** I topic si **inducono** sulla conversazione
dell'intera triade (`--topicgpt-unit group`), che ha abbastanza testo perché il
modello riconosca qualcosa, e si **assegnano** alle coppie ordinate
(`--topicgpt-assign-unit dyad_directed`), che sono l'unità in cui si gioca la
persuasione. Poi si aggregano a partecipante e a gruppo prendendo l'unione dei
topic delle unità componenti.

La separazione non è un dettaglio: inducendo direttamente sulle coppie ordinate
il modello risponde «None» su ogni documento, perché il prompt del paper
istruisce esplicitamente a farlo quando il documento non contiene un topic
riconoscibile, e uno scambio di due righe non lo contiene.

**Il seed è una scelta di ricerca.** TopicGPT parte da un elenco di topic
iniziali, che nel repository ufficiale riguarda il corpus dimostrativo del paper
— legislazione statunitense, con `[1] Trade` e esempi su dazi e politiche
agricole. Con quel seed, su conversazioni di chat il modello non riconosce
nulla. Il progetto usa quindi `prompts/seed_coalition_formation.md`, con tre
topic pertinenti al gioco. Fornire il seed è un **parametro del metodo**, non
una modifica al codice degli autori: `seed_file` è un argomento di
`generate_topic_lvl1`.

Attenzione però: il seed condiziona l'ontologia risultante. Sul pilota, con 18
conversazioni, non sono emersi topic nuovi oltre ai tre di partenza — il che è
il comportamento previsto dal prompt, che riusa i topic esistenti quando sono
pertinenti. Su un corpus grande ci si aspetta che ne emergano altri. Il
contenuto del seed va rivisto e approvato da chi conduce lo studio prima di
usare i topic in un'analisi.

**Modelli: TopicGPT e la rubrica non accettano gli stessi.** TopicGPT fissa
`temperature` e `top_p` in tutte le fasi, dentro il codice degli autori. I
modelli recenti che ammettono solo la temperatura predefinita — verificato su
`gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.6-sol` — li rifiutano con un errore 400,
e la libreria reagisce riprovando tre volte a un minuto di distanza: senza
controllo, l'incompatibilità emergerebbe dopo due minuti per ogni documento. Il
controllo preliminare la intercetta con una chiamata minima e si ferma subito.

Per i topic conviene quindi restare su `gpt-4o`, che è anche il modello del
paper. La rubrica non manda `temperature` e funziona con tutti: si sceglie con
`--llm-models`.

**Backend.** TopicGPT parla con OpenAI, Azure, Vertex, Gemini, Ollama o vLLM. Il
paper usa OpenAI ed è la scelta più fedele. Per usare Claude ci sono due strade
che non richiedono di modificare il codice degli autori: il backend `vertex`,
che nel repository costruisce un client `AnthropicVertex`, oppure `openai`
puntato a un gateway compatibile tramite `OPENAI_BASE_URL`.

---

## 9. Costi e volumi

Sul dataset finale (~1.557 partecipanti, ~519 triadi) le coppie ordinate saranno
circa 3.100 e i gruppi 519.

**TopicGPT** interroga il modello una volta per documento, in due fasi:
nell'ordine delle 6.500 chiamate su testi brevi.

**La rubrica** con due repliche si aggira sulle 7.200 chiamate. Due accorgimenti
tengono basso il conto: il prompt di sistema, identico a ogni chiamata, è
marcato per la cache, e `--llm-batch` usa la Batches API a metà prezzo (esito
asincrono, id del batch da conservare; disponibile solo con il fornitore
Anthropic).

Sono cifre contenute ma non nulle: conviene impostare un tetto di spesa sul
cruscotto del fornitore prima di lanciare.

---

## 10. Se qualcosa non torna

**«File mancante: ..._messages_long.csv»** — l'unione non è stata eseguita:
`python run.py merge`, oppure direttamente `python run.py all`.

**«Nessun file all_apps_wide*.csv in input/»** — l'export non è stato messo in
`input/`, o ha un nome diverso da quello prodotto da oTree.

**«Più file ChatMessages*.csv in input/»** — `input/` deve contenere un solo
export per tipo, altrimenti non è chiaro quale analizzare: lascia solo quello
che ti serve, o indicalo con `--chat <percorso>`.

**«Manca la chiave OPENAI_API_KEY»** — vedi §3. Con `--topicgpt-api ollama` i
topic girano in locale senza alcuna chiave.

**«Il pacchetto topicgpt_python non è installato»** — vedi §2, seconda parte.

**«Nessuna credenziale disponibile» per la rubrica** — il messaggio elenca le
tre strade: OpenAI, Anthropic o un modello locale.

**Voglio vedere cosa verrebbe inviato, senza spendere.** `--llm-dry-run` mostra
la richiesta della rubrica; `--topicgpt-dry-run` scrive solo il file di input di
TopicGPT. Nessuno dei due contatta alcun servizio.

**Voglio controllare che le chiavi funzionino.** `python run.py keys` le
riverifica contattando i servizi; `python run.py status` dice solo quali sono
presenti, senza uscire in rete.

---

## 11. Verifica degli strumenti

```bash
make test
```

Girano senza rete e senza credenziali. Se entrambi finiscono con `OK`, gli
strumenti sono a posto e un eventuale problema sta nei dati in ingresso.

Il controllo più stringente del primo non è un esempio ma una proprietà: per
**tutti i 27 profili di scelta possibili**, in entrambe le regole di payoff, le
variabili costruite devono risultare coerenti con la funzione di payoff del
gioco. Se la mappatura fra `decision_choice` — che è relativo alla topologia
circolare — e i giocatori assoluti fosse sbagliata anche di una sola rotazione,
il test fallirebbe.

Il secondo copre tokenizzazione delle forme contratte, euristica sugli avverbi
in *-ly*, formula del CDI ricalcolata a mano, direzione attesa dei compositi,
standardizzazione, conservazione di parole e messaggi attraverso i livelli di
aggregazione, asimmetria delle coppie ordinate, innesto sui dataset, parsing del
formato di risposta di TopicGPT, riconoscimento del testo che non è lingua,
caricamento delle chiavi e scelta del fornitore.

---

## 12. Risultati sul pilota

Stadio 1 eseguito su tutti i 311 messaggi del pilota del 18 agosto 2026.

| Livello | Unità |
|---|---|
| coppia ordinata (i→j) | 91 |
| coppia | 48 |
| partecipante nel gruppo | 50 |
| gruppo | 18 |

Sono **18 triadi e 54 partecipanti**: sei per trattamento, dalle tre sessioni
Prolific vere. Le altre sette triadi presenti nell'export venivano da sessioni
di collaudo interne e sono state escluse dal filtro sull'identificativo
Prolific. Dei 311 messaggi dell'export, 28 appartenevano a quelle sessioni e
283 entrano nell'analisi. Le distribuzioni non sono degeneri — a livello di
gruppo `analytic_cdi` va da −30 a +49 con 21 valori distinti su 24 unità — e gli
z-score hanno media 0 e deviazione 1 per costruzione.

**Sul contenuto**: 241 messaggi su 311 contengono inglese riconoscibile,
distribuiti su 20 gruppi; il resto sono stringhe di prova digitate durante i
test interni. C'è materiale realmente strategico — «*If you want to do that, we
can support each other. Unfortunately one person must be left out…*» —
abbastanza per verificare che la pipeline funzioni da capo a fondo, non
abbastanza per un'ontologia di topic stabile. È lo scopo previsto: rodare ora,
produrre risultati sul dataset finale.
