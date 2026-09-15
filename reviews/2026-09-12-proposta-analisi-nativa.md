# Una text analysis nostra per le chat degli esperimenti: proposta per uno short paper

*Documento di progetto, 12 settembre 2026. Accompagna l'audit dello stesso giorno.*

## 0. In una pagina

chatlens oggi misura le conversazioni con quattro strumenti presi in prestito —
gli indici LIWC-style ricostruiti da formule pubblicate, il lessico NRC, la
bag-of-words con lasso, RELATIO per le relazioni, TopicGPT per i temi — e li
confronta contro la lunghezza. Il risultato più solido dell'esperimento di
coalizione non è venuto da nessuno di questi: è venuto dalla **struttura**
(chi ha scritto a chi, 357 contro 35) e, dopo il controllo per la lunghezza, solo
le **relazioni dirette** hanno retto. I temi hanno restituito "None" sulla
maggioranza dei documenti, le emozioni sono misurabili su una minoranza di
messaggi, e le parole non battono la lunghezza.

Questo dice che gli strumenti presi in prestito sono nati per un altro tipo di
testo: documenti lunghi, indipendenti, di cui si vuole sapere *di cosa parlano*.
Una chat di un gioco economico è l'opposto: turni di cinque parole, dentro una
conversazione con una struttura di gruppo nota, in cui i partecipanti *fanno
mosse* — promettono, chiedono, accettano, minacciano, mentono — rivolte a
qualcuno, e in cui la sequenza e la reciprocità contano quanto il contenuto.

La proposta è quindi un modulo di analisi disegnato da noi per questo oggetto,
che chiamiamo per ora **mosse conversazionali** (*conversational moves*). Quattro
livelli, ciascuno con un fondamento pubblicato e un'implementazione senza
pacchetti esterni oltre a numpy/scipy (e spaCy dove serve un'analisi
sintattica, che resta un'infrastruttura, non un metodo altrui):


| Livello                        | Cosa produce                                                                                                                                                                                      | Fondamento                                                                                                                                         | Cosa migliora rispetto a oggi                                                                                                              |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| L1 Atti e mosse strategiche    | per ogni messaggio: tipo di mossa (offerta, promessa, richiesta, accettazione, rifiuto, minaccia, domanda, small talk…), **destinatario/beneficiario risolto** contro il roster                   | Stolcke et al. 2000; Houser e Xiao 2011; Charness e Dufwenberg 2006; He et al. 2018; Chawla et al. 2021; Penczynski 2019; Çelebi e Penczynski 2026 | TopicGPT non risponde su messaggi corti; le mosse sì. RELATIO estrae triple grammaticali, non intenzioni; e non sa chi è "you".            |
| L2 Coerenza mossa–azione       | per ogni coppia diretta: promesse fatte, mantenute, tradite; per ogni persona: indice di inganno strategico                                                                                       | Charness e Dufwenberg 2006; Niculae et al. 2015; Peskov et al. 2020                                                                                | Oggi `strategic_deception` esiste solo per l'adapter oTree e solo dai segnali strutturati; qui viene dal testo, per qualunque esperimento. |
| L3 Dinamica e coordinazione    | per ogni coppia diretta e gruppo: chi apre, latenza di risposta, reciprocità, **linguistic style matching** direzionale, accomodamento nel tempo                                                  | Gonzales, Hancock e Pennebaker 2010; Danescu-Niculescu-Mizil et al. 2012; Taylor e Thomas 2008; Ireland e Henderson 2014                           | Tutte le pagine attuali collassano la sequenza in un sacchetto. LSM si calcola dai conteggi di parole funzionali che chatlens ha già.      |
| L4 Inferenza adatta al disegno | conditional logit del ricevente sulle alternative; stability selection per le parole; split-sample per la scoperta; validazione umana con α di Krippendorff e correzione DSL per le etichette LLM | McFadden 1974; Meinshausen e Bühlmann 2010; Egami et al. 2022; Egami et al. 2023; Pangakis et al. 2023                                             | Il confronto attuale usa AUC su righe con cluster; la scelta di j fra i candidati è un modello di scelta discreta.                         |


Il piano di pubblicazione: prima come **appendice** del paper sui risultati di
coalizione (stesso corpus, stesse ipotesi, il modulo come "analisi
supplementare" che spiega perché gli strumenti standard vedono poco), poi come
short paper autonomo su un secondo corpus (il demo sintetico non basta: serve
un esperimento con chat già codificata a mano, ad esempio i dati di Charness e
Dufwenberg o un cheap-talk con codebook esistente) per la validazione esterna.

---



## 1. Perché gli strumenti attuali vedono poco, in termini che il paper può usare

I fatti misurati sul corpus di coalizione (507 gruppi, 8 041 messaggi) e già
documentati in `handbook/`:

1. **TopicGPT**: tasso di "None" a U (82 %, 67 %, 62 %, 83 % per quartile di
  lunghezza). Il prompt chiede *un* tema generalizzabile; una chat di
   negoziazione ne ha molti in sequenza o nessuno. I sottotemi citano i
   documenti 1–10 su 1 383: il grounding non regge.
2. **NRC**: il 73 % dei documenti fino a sette parole non contiene alcuna parola
  del lessico. Le colonne emozionali portano un segnale sulla lunghezza.
3. **Bag-of-words + lasso**: non batte la lunghezza; i pronomi di una lettera
  ("i", "u") non entrano nemmeno nel vocabolario (audit, B6).
4. **RELATIO**: unica rappresentazione che regge il controllo per lunghezza, ma
  (a) richiede 1,6 GB e la dichiarazione manuale delle entità; (b) estrae
   `(agent, verb, patient)` dalla sintassi: "I support you" e "I'll back
   whoever backs me" sono due mosse identiche per il gioco e due triple diverse
   per il parser; (c) non risolve "you" nel partecipante reale, cosa che il
   roster e la coppia diretta permettono.
5. **Il risultato migliore è strutturale**: la presenza stessa di un messaggio.

Questi cinque punti sono la motivazione dell'appendice: non "gli strumenti sono
sbagliati", ma "questo testo non è il testo per cui sono stati costruiti, ed ecco
cosa serve invece".

La letteratura di economia sperimentale su come codificare la comunicazione
libera fornisce la cornice: la classificazione dei messaggi per contenuto è il
problema aperto da Houser e Xiao (2011), che propongono un gioco di
coordinazione fra codificatori; Penczynski (2019) mostra che un classificatore
addestrato su codifiche umane replica i risultati; Tebbe e Wegener (2022)
confrontano classificatori su dati di cheap talk; Andres, Bruttel e Friedrichsen
(2023) usano ML sulle chat di un esperimento di collusione; Bruttel e Nithammer
(2025) danno linee guida per pre-registrare studi con ML su testo; Çelebi e
Penczynski (2026) mostrano che un codebook messo in un prompt LLM raggiunge
82–88 % di accordo con gli umani. Il nostro modulo si colloca qui: un codebook di
**mosse** specifico per la chat pre-gioco, applicato in tre modi (regole,
classificatore, LLM) con validazione umana obbligatoria.

---



## 2. Il modulo: quattro livelli



### 2.1 L1 — Atti conversazionali e mosse strategiche con destinatario risolto

**Oggetto.** Ogni messaggio riceve una o più etichette da un codebook chiuso, più
un **target**: la persona (seat/colore) a cui la mossa si riferisce, risolta
contro il roster del gruppo. Codebook proposto, derivato dagli schemi usati per
le negoziazioni (He et al. 2018: *coarse dialogue acts* come `propose`,
`accept`, `reject`; Chawla et al. 2021: strategie di persuasione annotate;
Stolcke et al. 2000 per gli atti generici) e dalla codifica economica delle
promesse (Charness e Dufwenberg 2006; Cooper e Kühn 2014: promesse, minacce,
rinegoziazione):


| Mossa                  | Esempio                                         | Target               |
| ---------------------- | ----------------------------------------------- | -------------------- |
| `offer` / `counter`    | "60/40", "i'll take a bit less"                 | destinatario         |
| `promise_support`      | "i'll back you", "let's support each other"     | destinatario o terzo |
| `request_support`      | "will you back me?", "seat 3, are you with us?" | destinatario o terzo |
| `accept` / `reject`    | "deal", "no", "not enough"                      | mossa precedente     |
| `threat` / `ultimatum` | "final offer", "or i go with 2"                 | destinatario         |
| `exclude_third`        | "leave 3 out", "just us two"                    | terzo                |
| `question` / `clarify` | "what do you want?"                             | —                    |
| `commit_none`          | "i'm not choosing anyone"                       | sé                   |
| `smalltalk` / `meta`   | "hi", "clock is running"                        | —                    |


Il target è la parte che RELATIO non fa e che rende la mossa una variabile
economica: `promise_support(i→j, beneficiario=j)` e
`promise_support(i→j, beneficiario=k)` sono le due mosse opposte del gioco.

**Tre implementazioni, una sola etichetta finale.**

1. *Regole* (`core/moves.py`, zero dipendenze): pattern lessico-sintattici sul
  tokenizzatore condiviso — verbi di impegno (`support`, `back`, `vote`,
   `go with`) + soggetto in prima persona + oggetto risolto; forme di offerta
   numerica (`\d+/\d+`, `split`, `even`); accettazione/rifiuto da liste corte
   con negazione. È il baseline trasparente e riproducibile senza chiavi.
2. *Classificatore* addestrato sulle codifiche umane (regressione logistica
  multi-etichetta su n-grammi + feature del livello 1: presenza del nome del
   terzo, pronome di seconda persona, numeri), come in Penczynski (2019).
3. *LLM con codebook nel prompt*, con l'infrastruttura del rubric attuale
  (schema pydantic per messaggio, cache, repliche), secondo Çelebi e Penczynski
   (2026): il codebook va trascritto quasi alla lettera.

L'etichetta finale per il paper è quella del metodo con la migliore
concordanza con gli umani sul campione validato (§ 2.4); gli altri due entrano in
appendice come robustezza. Tutte e tre producono le stesse colonne:
`mv_<mossa>` (0/1 per messaggio), `mv_<mossa>_target` (seat), e per unità
(coppia diretta, persona, gruppo) i conteggi e le quote.

**Risoluzione del target.** Dal roster dell'unità: "you" = ricevente del
messaggio; nomi/colori/numeri di seat dalla lista `narratives.entities` del
TOML (già esistente) mappata ai `*_id_in_group`; "the other one", "the third",
"both" = membri restanti. Dove la risoluzione è ambigua il target è vuoto e il
messaggio è contato in `mv_unresolved`, così l'ambiguità è un numero e non un
errore silenzioso. Sui gruppi di tre la risoluzione è quasi sempre univoca.

### 2.2 L2 — Coerenza fra parola e azione: promesse, tradimenti, inganno

**Oggetto.** L'esperimento registra la scelta finale. Incrociando
`promise_support(i→j, beneficiario=j)` con `A_ji` (j ha scelto i) e con
l'azione di i si ottengono, per ogni coppia diretta e senza bisogno dei segnali
strutturati dell'adapter oTree:

- `kept_promise_ij`: i ha promesso a j e poi ha scelto j;
- `broken_promise_ij`: i ha promesso a j e ha scelto altri;
- `promise_persuaded_ij`: i ha promesso a j e j ha scelto i;
- `double_promise_i`: i ha promesso a entrambi i partner (inganno strategico
letto dal testo, generalizzazione di `strategic_deception`);
- `promise_timing_ij`: quando nella conversazione arriva la promessa
(quota della durata), perché Niculae et al. (2015) trovano che il tradimento
è preannunciato da cambiamenti *temporali* del linguaggio — meno cortesia,
più squilibrio nel sentimento positivo, meno pianificazione — e non dal
livello medio.

**Fondamento.** Charness e Dufwenberg (2006) codificano a mano le promesse nei
messaggi liberi e mostrano che spiegano la cooperazione; Niculae et al. (2015)
e Peskov et al. (2020) studiano tradimento e menzogna nelle chat di Diplomacy
con misure computazionali (politeness, sentimento, pianificazione; 17 000
messaggi annotati per veridicità intesa e percepita); Wongkamjan et al. (2025)
mostrano che l'inganno in negoziazione è rilevabile confrontando le parole con
le azioni controfattuali. Il nostro contributo è la stessa idea con il roster
esplicito e la scelta registrata: la verità di una promessa non va annotata,
è nel dataset.

### 2.3 L3 — Dinamica e coordinazione linguistica

**Oggetto.** Misure sulla sequenza dei turni, per coppia diretta e per gruppo,
tutte calcolabili dai conteggi di parole funzionali che `text_metrics` produce
già:

- **LSM direzionale** (Gonzales, Hancock e Pennebaker 2010): per ogni categoria
funzionale c (articoli, preposizioni, pronomi, ausiliari, congiunzioni,
negazioni, avverbi, quantificatori), `LSM_c = 1 − |p_c(i→j) − p_c(j→i)| / (p_c(i→j) + p_c(j→i) + 0,0001)`, media sulle categorie. Predice coesione nei
gruppi (Gonzales et al.), esito nelle negoziazioni (Taylor e Thomas 2008),
e nel caso di Ireland e Henderson (2014) anche l'impasse: l'effetto non è
monotono e va riportato per fasi.
- **Coordinazione turno-per-turno** (Danescu-Niculescu-Mizil, Lee, Pang e
Kleinberg 2012): `C_m(b→a) = P(m ∈ risposta di b | m ∈ turno di a) − P(m ∈ risposta di b)` per ogni marcatore m. È asimmetrica: chi si
accomoda a chi rivela differenze di potere. Nel gioco di coalizione, chi ha
bisogno di supporto dovrebbe accomodarsi di più; è un'ipotesi verificabile.
- **Iniziativa e latenza**: chi apre la conversazione della coppia, tempo alla
prima risposta, quota di turni non risposti (`mv_unanswered`), reciprocità
(rapporto fra messaggi i→j e j→i). Il risultato 357/35 è il caso estremo di
questa famiglia (reciprocità zero).
- **Cortesia** (Danescu-Niculescu-Mizil et al. 2013; Yeomans, Kantor e Tingley
2018): marcatori lessicali e sintattici — ringraziamenti, deferenza,
attenuazioni, indirezione, richieste dirette — implementabili con spaCy e
liste; sono i marcatori che Niculae et al. (2015) trovano predittivi del
tradimento.
- **Traiettoria del tono**: sentimento VADER per finestra di turni e pendenza
nel tempo, non solo la media (Niculae et al. 2015: lo *squilibrio* nel tempo
è il segnale).

Tutte queste misure rispettano la regola del progetto: la lunghezza entra nel
modello, e le misure di coordinazione sono per costruzione condizionate a un
turno precedente, quindi non confondibili con "chi scrive di più".

### 2.4 L4 — Inferenza adatta al disegno, e validazione

- **Conditional logit del ricevente** (McFadden 1974). L'outcome "j sceglie i"
è una scelta fra i candidati di j; le covariate sono le mosse e le misure di
L1–L3 *specifiche dell'alternativa* i (cosa i ha scritto a j, come si è
coordinato). Il modello elimina tutto ciò che è di j, del gruppo e del
trattamento senza doverlo controllare. Il confronto "within receiver" della
pagina Participation è il caso a due alternative con una covariata binaria
("ha scritto"); il modulo lo generalizza (statsmodels `ConditionalLogit`,
Stata `clogit`, con errori standard cluster per gruppo).
- **Stability selection** per le parole (Meinshausen e Bühlmann 2010) e
**Fightin' Words** (Monroe, Colaresi e Quinn 2008) come rappresentazione
lessicale con controllo dell'errore, al posto del lasso singolo.
- **Split-sample** (Egami, Fong, Grimmer, Roberts e Stewart 2022): scoperta
delle mosse/parole su una metà dei gruppi, stima sull'altra, per evitare che
la stessa variazione serva a inventare la misura e a testarla.
- **Validazione umana obbligatoria** (Grimmer e Stewart 2013; Pangakis et al.
2023; Törnberg 2024): campione stratificato di messaggi codificato da due
persone con il codebook di L1; α di Krippendorff fra umani, fra umani e
ciascun metodo, fra repliche LLM. Sotto α = 0,67 l'etichetta non entra nelle
regressioni principali.
- **Correzione per l'errore di misura** delle etichette automatiche nelle
regressioni a valle (design-based supervised learning, Egami, Hinck, Stewart e
Wei 2023; cornice econometrica in Ludwig, Mullainathan e Rambachan 2024):
l'80–90 % di accuratezza non basta a rendere valide le stime senza il campione
validato.
- **Pre-registrazione** secondo Bruttel e Nithammer (2025): il codebook, le
regole, il campione di validazione e le soglie vanno depositati prima di
toccare il corpus completo.

---

