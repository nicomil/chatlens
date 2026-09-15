# chatlens — audit del 12 settembre 2026: problemi, rischi e piano di miglioramento

Questo documento è il risultato di una lettura completa del codice (`src/chatlens/`,
29 000 righe fra sorgenti e test), della documentazione (`handbook/`, `PLAN.md`,
`examples/coalition_formation/stata/ANALYSIS_PLAN.md`) e di una serie di verifiche
empiriche eseguite sul workspace sintetico di `chatlens demo`. Non è stato letto
alcun dato di partecipanti reali: tutte le riproduzioni usano il corpus sintetico.

Stato di partenza:

| Voce | Valore |
|---|---|
| Suite di test | 15 file, 596 test, tutti verdi (`.venv`, Python 3.11.9) |
| Extra installati nell'ambiente di sviluppo | words, narratives, stata, llm, topics, RELATIO |
| Versioni rilevanti | scikit-learn 1.9.0, anthropic 0.125.0, openai 1.109.1, htmx 2.0.4 |

Ogni problema riporta la posizione nel codice, la gravità, come è stato verificato
e la correzione suggerita. La sezione finale è un piano ordinato per priorità.

> **Stato delle correzioni (aggiornato il 13 settembre 2026).** Chiusi e coperti
> da test **tutti i bug di questo documento**: B1–B18, più **B19**, che non era
> in questa lista perché è emerso lavorando alle dipendenze (il pin
> `anthropic>=0.40,<1` era più basso della versione che introduce
> `messages.parse`, su cui la rubric è costruita: un ambiente poteva soddisfare
> tutte le dipendenze dichiarate e fallire comunque alla prima chiamata a
> pagamento). Chiusi anche tutti i punti di
> sicurezza affrontabili senza cambiare architettura — S1, S3, S4, S6, S9 —
> tutta la sezione interfaccia (U1–U10) e i miglioramenti M4, M5a, M5b, M5c,
> M6, M7, M9, M10.
>
> B8 e B9 sono stati implementati nella forma decisa dallo sperimentatore:
> pipeline dentro ogni fold di `GroupKFold`, e modelli annidati con differenza
> appaiata, correzione di Nadeau e Bengio, Holm e verdetto a tre stati. La
> specifica e le soglie con le numerosità vere sono in
> `reviews/2026-09-13-nota-metodologica-due-studi.md`.
>
> Restano fuori portata per scelta, e vanno pianificati separatamente: **M1**
> (eliminare lo stato globale in `config`, di cui B10 e B11 erano sintomi ora
> corretti in modo mirato), **M2** e **M3**, che sono il contenuto della
> proposta di analisi nativa e non manutenzione. La suite è a 721 test su 17
> file, tutti verdi, `ruff` pulito, il merge ancora byte-identico al riferimento
> (`test_golden_merge.py`), `chatlens demo` completo da capo a fondo. Il
> dettaglio di ogni correzione è nel `CHANGELOG.md`.

---

## 1. Sintesi

Il progetto è in buono stato: l'architettura adapter/core è pulita, la sicurezza
del server locale è pensata con cura (controllo dell'`Host`, token di sessione in
cookie `SameSite=Strict`, verifica di `Origin`/`Sec-Fetch-Site`, CSP restrittiva,
estrazione dei bundle con controllo dei membri), i test sono numerosi e i commenti
spiegano le decisioni. Le guardie sulla spesa, il cache dei rating pagati e la
verifica delle fasi di TopicGPT sono difese reali che molti strumenti simili non
hanno.

I problemi trovati sono di quattro tipi:

1. **Bug funzionali confermati**, tre dei quali gravi per la modalità libreria
   (più esperimenti nella stessa dashboard): le pagine Words, Compare e
   Narratives servono i risultati dell'esperimento sbagliato; i link ai file dei
   run archiviati rispondono 404; la pagina Compare va in errore 500 con un
   outcome per partecipante codificato 0/1.
2. **Difetti statistici** che non fanno crollare nulla ma cambiano i numeri che
   finiscono in un paper: correzione di Benjamini-Hochberg non monotona,
   vocabolario e standardizzazione calcolati fuori dai fold della cross-validation,
   pronomi di una lettera ("i", "u") invisibili alla bag-of-words, soglia
   "beats length" fissata a 0,02 senza incertezza.
3. **Difetti di interfaccia**: il tema scelto non sopravvive al ricaricamento
   (script inline bloccato dalla CSP scritta dal progetto stesso), un solo runner
   condiviso fra tutti gli esperimenti, righe cliccabili non raggiungibili da
   tastiera, attesa senza limite quando due esperimenti sono aperti in due schede.
4. **Rischi di manutenzione**: liste di modelli duplicate in tre file, tre
   tokenizzatori diversi per lo stesso testo, vincolo `anthropic<1` imposto da
   TopicGPT.

Nessuna vulnerabilità sfruttabile da remoto è emersa. I punti di sicurezza sotto
sono rafforzamenti, non falle.

---

## 2. Bug confermati

### B1 — Le cache delle pagine ignorano quale esperimento è attivo (grave)

**Dove:** `src/chatlens/web/views_words.py:327`, `views_compare.py:279`,
`views_narratives.py:728`.

**Cosa succede.** Le tre pagine tengono in memoria l'ultimo risultato con una
chiave che contiene i parametri, la colonna dell'outcome, l'unità e (per le
relazioni) le entità, ma **non** il nome o il percorso dell'esperimento. In
modalità libreria due studi con la stessa configurazione (`accepted`,
`sender_group`, stesse entità) condividono la cache: il secondo aperto mostra il
modello, le AUC, le nuvole di parole e i verdetti del primo.

**Verifica.** Due copie del workspace demo con outcome invertito: aprendo la
seconda, `words.fit` e `compare.score` non sono stati richiamati (contatore fermo
a 1) e la chiave in cache era identica. Il registro dei verdetti a sinistra
(`study.verdicts`) legge la stessa cache, quindi anche i "✓/✗" sono quelli
dell'altro studio.

**Correzione.** Aggiungere `config.WORKSPACE` (o `library` slug) alla chiave di
ogni cache di pagina, oppure spostare le cache in un dizionario per workspace con
evizione. Test da aggiungere: due workspace con configurazione identica e dati
diversi devono produrre `result()` diversi senza `_CACHE.clear()`.

### B2 — I link ai file dei run archiviati rispondono 404 in modalità libreria (medio)

**Dove:** `src/chatlens/web/views.py:606` (`_run_files`), `:671-673`
(`run_detail`: link "open full page" e `<iframe src>`).

**Cosa succede.** Gli href sono costruiti come `/runs/<run>/<file>` alla radice,
mentre in modalità libreria l'unica rotta che conosce il workspace è
`/experiment/<slug>/runs/...`. Alla radice `config.OUTPUT_DIR` è la cartella da
cui è stato lanciato `chatlens dashboard`, non lo studio.

**Verifica.** Server di test in modalità libreria: `GET
/experiment/demo-study/run/<run>` produce tre link `/runs/...`; i primi due
rispondono 404, la variante `/experiment/demo-study/runs/<run>/report.html`
risponde 200.

**Correzione.** Usare `active.base()` come prefisso (già fatto per `hx-get` nella
stessa funzione). Un test sulla pagina di dettaglio run in modalità libreria che
segua ogni link.

### B3 — La pagina Compare va in errore 500 con un outcome per persona codificato 0/1 (grave)

**Dove:** `src/chatlens/web/views_compare.py:225-240` (`_participation_line`).

**Cosa succede.** La funzione sceglie il file in base all'unità dell'outcome
(`DATASET_OF[unit]`), ma poi indicizza ogni riga con `row['partner_id_in_group']`,
colonna che il file aggregato non ha. Con `unit = sender_group` e valori `0`/`1`
si ottiene `KeyError`, l'handler non lo intercetta e la risposta è una
connessione interrotta con traceback in console.

**Verifica.** Demo con `accepted` ricodificato a 0/1 nel file merged aggregato:
`_participation_line('demo-study')` solleva `KeyError: 'partner_id_in_group'`.

**Correzione.** Restituire `''` quando `outcome['unit'] != 'dyad_directed'` (la
pagina Participation fa già così in `_outcomes`). Inoltre confrontare con
`outcome.as_binary` invece di `raw in ('0','1')`: oggi con `yes`/`no` la riga
sparisce in silenzio (vedi B5).

### B4 — Correzione di Benjamini-Hochberg senza il minimo cumulativo (medio, statistico)

**Dove:** `src/chatlens/core/narratives.py:437-440`.

**Cosa succede.** `q = p * m / rank` senza il passo `q_i = min_{j ≥ i} q_j`. I
q-value non sono monotoni e alcuni risultano più alti del dovuto; il conteggio
dei "survivors" può sottostimare.

**Verifica.** Con p = (0,001; 0,0011; 0,03; 0,04; 0,5) il codice dà q₁ = 0,005,
`statsmodels.multipletests(method='fdr_bh')` dà q₁ = 0,0028.

**Correzione.** Percorrere la lista ordinata dall'ultimo al primo tenendo il
minimo, oppure usare `statsmodels.stats.multitest.multipletests` (già
dipendenza dell'extra `narratives`). Test con un vettore di p noto.

### B5 — La riga "prima di tutto: chi ha scritto" legge solo i valori 0/1 (medio)

**Dove:** `views_compare.py:238`.

Il resto del programma accetta `yes/no/true/false/1/0` tramite
`outcome.as_binary`; qui si accettano solo `'0'` e `'1'`. Con il demo (yes/no) la
riga non compare e il lettore non sa che il confronto "chi ha scritto" esiste.
Correzione: `outcome_module.as_binary(...)`.

### B6 — La bag-of-words non vede i pronomi di una lettera (medio, metodologico)

**Dove:** `src/chatlens/core/words.py:104`, `compare.py:873`.

`CountVectorizer` con il `token_pattern` predefinito `\b\w\w+\b` scarta i token
di un carattere. In un gioco di persuasione "i", "u" (you) e "k" sono parole
chiave; verifica: vocabolario di `["i support you", "u and i"]` = `{and,
support, you}`. Il modulo `text_metrics` invece li conta. Correzione:
`token_pattern=r"(?u)\b\w+\b"` o un tokenizzatore condiviso (vedi M7).

### B7 — `words.clean` taglia il testo prima dei due punti anche dove non c'è il prefisso "Chi->Chi:" (basso)

**Dove:** `words.py:66`; chiamato da `views_words._text_column` (che ripiega su
`text`/`body`), `views_emotions._texts_and_source`, `fulltables._add_emotions`,
`views_narratives.words_of`.

Verifica: `clean("ratio is 2:1 and i think: yes")` → `"1 and i think: yes"`.
Sulle colonne `*_transcript_text` (prefisso presente) è corretto; sulle colonne
`body`/`text` no. Correzione: applicare `clean` solo alle colonne di trascrizione,
o riconoscere il prefisso con un'espressione regolare (`^\S+\s*->\s*\S+:\s`).

### B8 — Selezione del vocabolario e standardizzazione fuori dai fold (medio, metodologico)

**Dove:** `words.py:104-111` e `compare.py:873-876` (il `CountVectorizer` con
`min_df` è adattato su tutte le righe e poi si fa `GroupKFold`); `compare.py:855`
(gli indici `*_100` sono standardizzati sull'intero campione in
`text_metrics.standardize`).

L'informazione sul test set entra nella scelta delle feature. L'effetto su una
`min_df` binaria è piccolo ma sistematicamente ottimista, e il paper dovrà
dichiararlo. Correzione: `sklearn.pipeline.Pipeline([vectorizer, scaler,
model])` valutata con `cross_val_score(..., groups=...)`, così ogni fold
ricostruisce vocabolario e scala sul solo training.

### B9 — La soglia "batte la lunghezza" è un numero fisso (medio, metodologico)

**Dove:** `compare.py:815` (`MEANINGFUL = 0.02`).

La differenza fra AUC di due rappresentazioni sugli stessi fold ha una
variabilità stimabile (le AUC per fold sono già calcolate: `spread`). Un 0,02
fisso è arbitrario e, con cinque fold su qualche centinaio di gruppi, spesso
dentro il rumore. Correzione: test appaiato sulle differenze per fold con la
correzione di Nadeau e Bengio (2003) per la varianza della cross-validation, o
un bootstrap sui gruppi; riportare l'intervallo, non solo "yes/no".

### B10 — Un solo runner per tutti gli esperimenti (medio, UX)

**Dove:** `src/chatlens/web/runner.py:226` (`runner = Runner()`),
`views.log_body`/`log_head`/`form_panel`.

Il registro del run, il pulsante Stop e il "A run is already in progress"
sono globali: avviato un run nello studio A, la pagina Run di B mostra il log di
A e rifiuta di partire. Correzione minima: un `Runner` per workspace in un
dizionario; il log della pagina mostra solo il run del proprio esperimento e
dice "un run di *A* è in corso" quando è un altro a occupare il processo.

### B11 — Attesa senza limite quando si cambia esperimento (medio, UX)

**Dove:** `src/chatlens/web/active.py:86-87`.

Una richiesta per un esperimento diverso aspetta che `_depth` torni a zero; il
poll del log ogni secondo dell'altro esperimento e una pagina che calcola per
minuti (Narratives, Compare) la tengono fuori senza timeout né messaggio. Con
due schede su due studi la seconda sembra morta. Correzione: `_LOCK.wait(timeout)`
con una risposta 503 "lo studio *A* sta calcolando, riprova" oltre i 10 s; in
prospettiva, eliminare lo stato globale in `config` passando un oggetto
`Workspace` alle viste (vedi M1).

### B12 — Il tema chiaro/scuro non sopravvive al ricaricamento (basso, UX; alta confidenza)

**Dove:** `src/chatlens/web/ui.py:200-204` (`THEME_SCRIPT`, script inline nel
`<head>`), `server.py:66` (`script-src 'self'`), `static/app.js` (nessun
`getItem`).

La CSP del progetto vieta gli script inline; l'unico codice che rilegge
`localStorage['chatlens-theme']` al caricamento è proprio quello inline, quindi
è bloccato e la preferenza si perde a ogni pagina. Correzione: spostare la
lettura in `app.js` (accettando un breve flash) oppure aggiungere un nonce alla
CSP e allo script.

### B13 — Righe cliccabili non attivabili da tastiera (basso, accessibilità)

**Dove:** `views.py:585-586` (`<li hx-get ... tabindex="0" role="button">`).

htmx attiva gli elementi non-form solo sul `click`; con `role="button"` il
lettore si aspetta Invio/Spazio. Nessun `keydown` in `app.js`. Correzione:
`hx-trigger="click, keyup[key=='Enter'] "` oppure usare un `<button>`.
La classe `sortable` sulle tabelle (`ui.table`) non ha alcun codice dietro:
va tolta o implementata.

### B14 — Nome esperimento lungo: errore fuorviante (basso)

**Dove:** `src/chatlens/core/library.py:463-475` e `:485-487`.

`slug()` tronca a 64 caratteri **dopo** aver tolto i trattini ai bordi; se il
64° carattere è un trattino, `path_for(slug)` rifiuta lo slug che `create()` ha
appena prodotto ("Not an experiment name"). Verifica: un nome di 63 "a" seguito
da " b more words". Correzione: `strip('-')` dopo il troncamento.

### B15 — `_latest` cerca sempre l'input `wide` (basso)

**Dove:** `src/chatlens/web/views_participation.py:490`.

`config.find_input('wide')` solleva `KeyError` con l'adapter `generic_chat`
(nessun ruolo `wide`), l'eccezione è inghiottita e si ripiega su `mtime`. Il
"file dello stem dichiarato" non funziona mai per gli esperimenti generici.
Correzione: usare il primo ruolo obbligatorio dell'adapter (`cli.dataset_stem`
fa già così).

### B16 — "Nothing to test" quando manca la colonna di testo (basso)

**Dove:** `views_narratives.py:780` (`words_of=... else (lambda r: 0)`).

Con lunghezza costante zero la matrice di disegno è singolare, ogni `Logit`
fallisce ed è saltato in silenzio, e la pagina dice che nessuna relazione era
testabile. Correzione: se non c'è testo, testare senza il controllo di
lunghezza e dirlo, oppure segnalare il motivo.

### B17 — Voci di dizionario irraggiungibili (basso)

**Dove:** `src/chatlens/core/lexicons.py:920-923, 936` (`"'m"`, `"'re"`,
`"n't"`, …) contro `text_metrics.TOKEN_RE` (`[a-z]+(?:'[a-z]+)*`).

Il tokenizzatore non produce mai token che iniziano con apostrofo, quindi quelle
voci non contano. Innocuo (le forme intere come `don't` sono presenti), ma va
rimosso o documentato; e insieme a B6 mostra che ci sono **tre tokenizzatori
diversi** (`text_metrics`, `nrc.TOKEN = [a-z']+`, `CountVectorizer`) per lo
stesso testo (vedi M7).

### B18 — Liste di modelli duplicate (basso, manutenzione)

`runner.ALLOWED['llm_model']`, `views.MODELS_RUBRIC`, `llm_rubric.PROVIDERS` e
`views.MODELS_TOPIC` vanno tenuti allineati a mano. Un modello aggiunto in un
posto solo non compare nel form o viene scartato dal runner senza messaggio.
Correzione: una sola tabella in `llm_rubric` (o in un modulo `models.py`) da cui
derivano sia l'allow-list sia il `<select>`.

### B19 — Il pin dello SDK Anthropic era più basso della versione che serve

`pyproject.toml` dichiarava `anthropic>=0.40,<1`. Quel limite inferiore veniva
da quando il modulo usava `messages.create`; la rubric è invece costruita su
`client.messages.parse(output_format=…)` con `output_config`, che **non esiste**
prima della **0.77.0** (verificato scaricando i wheel: assente in 0.76.0,
presente in 0.77.0, presente ancora in 1.0.0). Un ambiente poteva quindi
soddisfare tutte le dipendenze dichiarate e fallire con un `AttributeError` alla
prima chiamata a pagamento. Nel venv di questo progetto la versione installata è
0.125.0 e funziona; su un secondo interprete della stessa macchina era 0.69.0 e
non funzionava, ed è così che è emerso.

Il limite superiore `<1` invece non era il problema: le versioni da 0.77 a 0.125
soddisfano sia quel vincolo sia la rubric. Il vincolo che pesa davvero viene da
TopicGPT, il cui `requirements.txt` (0.2.8) dichiara `openai>=1.54.3,<2.0.0`,
`anthropic>=0.39.0,<1.0.0` e `numpy>=1.26.2,<2.0.0`: installarlo nello stesso
interprete riporta indietro tutte e tre le librerie, `numpy` compreso, che è
quello che tiene indietro anche scikit-learn.

Correzione applicata: floor a `0.77`, tetto allargato a `<2` dopo aver
verificato che la chiamata c'è anche nella 1.0.0; un extra `topics-legacy`
separato che dichiara i vincoli di TopicGPT, così il downgrade è uno stato
dichiarato e non una sorpresa; `llm_rubric.sdk_problem()` che dice a parole che
cosa manca; il controllo nel preflight, che esiste per fallire *prima* di
spendere; e `chatlens status` che lo riporta quando c'è qualcosa da dire.

---

## 3. Sicurezza: stato e rafforzamenti

La superficie è un server su `127.0.0.1` che avvia processi. Le difese presenti
sono adeguate al modello di minaccia (pagina web malevola aperta nello stesso
browser, DNS rebinding). Punti da rafforzare, in ordine di utilità:

| # | Punto | Dove | Nota |
|---|---|---|---|
| S1 | Estrazione dei bundle senza `filter=` e senza limite di dimensione | `core/bundle.py:448` | I membri sono già controllati (solo file/dir, niente `..`), ma `tarfile.extract` senza `filter='data'` emette `DeprecationWarning` su 3.12/3.13 e il default cambia in 3.14. Aggiungere `filter='data'` dove disponibile e un tetto sulla somma di `member.size` (decompression bomb, anche solo per errore). |
| S2 | Script inline vs CSP | `ui.py:200`, `server.py:66` | Coincide con B12: la CSP è giusta, lo script inline no. Non è una falla, è la CSP che funziona. |
| S3 | Upload sovrascrive file omonimi senza conferma | `server.py:645` | Documentato nella pagina, ma un click sbagliato sostituisce l'export originale. Chiedere conferma come per "remove", o rinominare con suffisso. |
| S4 | Race fra upload e run in corso | `server.py:_upload` | L'upload avviene fuori dal lock (giusto per non bloccare), ma un run che sta leggendo `input/` può vedere un file a metà. Scrivere sempre su nome temporaneo e `replace()` (già fatto) **e** rifiutare l'upload mentre `runner.running`. |
| S5 | Token nella cronologia del browser | `server.py:1035` | `Referrer-Policy: no-referrer` è già impostata; il token resta nella cronologia. Accettabile per un token per-sessione; si può ridirigere subito su `/` dopo aver impostato il cookie (303) così l'URL con `?t=` non resta come pagina corrente. |
| S6 | Nessun `Permissions-Policy`/`Cross-Origin-Opener-Policy` | `_send` | Aggiunta a costo zero. |
| S7 | Chiavi: `load_env` avvisa solo se `.env` è leggibile da altri utenti; `keys.env` scritto 600 | ok | Verificato che `.env` non è tracciato in git. |
| S8 | Dati personali nei bundle | `bundle.py` | `--pseudonymise` copre gli identificatori, non i testi: il manifest lo dichiara. Vedi M9 per una scansione opzionale di PII nei messaggi. |
| S9 | `spend.check` nel sottoprocesso della dashboard non chiede mai conferma (`isatty()` falso) | `spend.py:907` | Sotto 20 000 chiamate procede sempre; l'unico avviso è la stima nel form. Portare la conferma nell'interfaccia: il pulsante "Start run" chiede conferma oltre `CONFIRM_ABOVE`. |

Uso dell'API Anthropic (`core/llm_rubric.py`) verificato contro lo SDK
installato nel venv del progetto (0.125.0): `messages.parse(output_format=…)`,
`thinking={'type': 'adaptive'}`, `output_config={'effort': 'medium'}` e
`cache_control` sul system sono corretti; la gestione di
`stop_reason == 'refusal'` c'è. Resta utile registrare `response._request_id`
nella cache dei rating per tracciare i fallimenti presso il provider.

---

## 4. Interfaccia e usabilità

Oltre a B10–B13:

- **U1. Stato del run per esperimento.** La spina in alto dice "Run: done" appena
  esiste un dataset, anche se l'ultimo run è fallito (`failed_stage`). Mostrare
  "done, with the topics stage failed" leggendo `archive.list_runs()[0]`.
- **U2. Stima delle chiamate prima del primo run.** `estimate_panel` dice "The
  estimate appears after the first run" perché legge i conteggi dagli archivi;
  i conteggi si possono ottenere dal merge (`n_groups`, coppie dirette) senza run.
- **U3. Pagina Words: il controllo "How selective".** Il valore mostrato è `C`
  di scikit-learn (inverso della penalità). L'etichetta e la spiegazione sono
  coerenti fra loro, ma nel CSV scaricato la colonna dovrebbe chiamarsi `C` o
  `inverse_penalty`, non `penalty`, per chi rifà il modello in R o Stata.
- **U4. Nessuna pagina "Rubric".** I rating LLM finiscono nei dataset e nel
  report statico, ma non hanno un finding nel registro (correlazione con gli
  indici, spread fra repliche, tasso di errori). È la validazione convergente
  dichiarata nel README e merita una pagina come le altre.
- **U5. Nessuna pagina "Topics".** Idem: l'unico posto è il report HTML.
- **U6. Messaggi di blocco.** `ui.blocked` propone il comando giusto, ma il
  pulsante "Check again" ricarica la pagina intera con `?checked=1` senza
  invalidare `optional.have` (che usa `find_spec`, quindi va bene) né
  `narratives.forget_route()` (chiamata da nessuna vista: cercarla nel codice
  dà solo la definizione). Dopo `chatlens install-relatio` la pagina continua a
  dire "not installed" fino al riavvio.
- **U7. Report statico e pagine dinamiche raccontano cose diverse.** Il report
  (`core/report.py`) non conosce partecipazione, parole, relazioni, emozioni,
  confronto; l'export dei finding (`views_findings.export`) non conosce
  copertura, outcome di gioco, rubric, topics. Uno solo dei due dovrebbe esistere,
  o l'export dovrebbe includere le sezioni del report.
- **U8. Accessibilità.** Le tabelle hanno `<caption>` solo se passata; i
  suggerimenti `data-tip` compaiono su hover/focus ma non sono letti dagli
  screen reader (usare `aria-describedby`); le nuvole SVG hanno `role="img"`
  senza `<title>`.
- **U9. Mobile.** Il CSS ha un solo breakpoint; la griglia di partecipazione e
  le tabelle dei coefficienti sono in `overflow-x: auto` (bene), ma la spina a
  cinque passi non si comprime.
- **U10. Documentazione.** `handbook/procedure.md` è ancora scritto per
  l'esperimento oTree (Step 1 "download from oTree"); la guida per `generic_chat`
  è in `your-experiment.md`. Un lettore nuovo parte da `procedure.md`.

---

## 5. Miglioramenti e ottimizzazioni

### M1 — Eliminare lo stato globale in `config`

`config.WORKSPACE`, `EXPERIMENT`, `INPUT_PATTERNS` sono attributi di modulo
rilegati per richiesta sotto un lock. È la causa di B1, B10, B11 e del
`_saved` in `active.py`. Un oggetto `Workspace(path, experiment)` passato alle
viste (o messo in `contextvars.ContextVar`) elimina il lock, permette richieste
davvero concorrenti fra esperimenti e rende le cache per-workspace ovvie.
È il refactor più costoso della lista ma sblocca tutto il resto.

### M2 — Statistica del confronto

- Pipeline dentro i fold (B8), test appaiato con correzione Nadeau-Bengio (B9).
- **Stability selection** (Meinshausen e Bühlmann 2010) per la pagina Words: la
  pagina già invita a "muovere la penalità e guardare quali termini restano";
  formalizzarlo (sottocampioni + frequenza di selezione per termine, soglia
  π = 0,6–0,9) dà un insieme di parole con controllo dell'errore invece di una
  lista che cambia con `C`.
- **Fightin' Words** (Monroe, Colaresi e Quinn 2008) come alternativa senza
  modello: log-odds con prior di Dirichlet, robusto alla sparsità, con z-score
  per termine. Nessuna dipendenza oltre numpy.
- **Conditional logit** per l'outcome "j sceglie i": la struttura è una scelta
  fra alternative (i candidati di j) e il modello naturale è quello di McFadden
  (1974), che elimina per costruzione tutto ciò che è del ricevente e del gruppo.
  Il confronto "within receiver" della pagina Participation è il caso a due
  alternative di questo modello; generalizzarlo alle covariate testuali è il
  passo successivo (statsmodels `ConditionalLogit`, Stata `clogit`).
- Riportare AUC **e** un'analisi di calibrazione o un indice interpretabile
  (odds ratio con IC), perché "predice meglio" e "conta" sono domande diverse,
  come la pagina stessa dice.

### M3 — Validazione del rubric LLM

Il rubric non ha un ground truth umano: la correlazione con gli indici LIWC-style
è validazione convergente fra due misure automatiche. La letteratura recente
è unanime: le annotazioni LLM vanno validate su un campione codificato da umani,
per compito (Pangakis, Wolken e Fasching 2023; Törnberg 2024; Ziems et al.
2024), e per usarle in una regressione a valle serve correggere l'errore di
misura con il campione validato (Egami, Hinck, Stewart e Wei 2023, "design-based
supervised learning"; Ludwig, Mullainathan e Rambachan 2024). In economia
sperimentale Çelebi e Penczynski (2026, PLOS ONE) mostrano che un codebook
trascritto nel prompt raggiunge 82–88 % di accordo con gli umani. Da aggiungere
a chatlens:

1. una pagina/flag per codificare a mano un campione stratificato (50–200 unità)
   con lo stesso rubric, e il calcolo di α di Krippendorff / ICC fra umano e
   modello e fra repliche;
2. l'export di quel campione con le etichette, così il paper può riportarlo;
3. la stima DSL (o la semplice correzione per errore di classificazione) nelle
   regressioni che usano i flag `llm_contains_*`.

### M4 — Cache e prestazioni

- Le cache di pagina tengono una sola voce: con la correzione B1 diventano
  per-workspace ma vanno limitate (LRU di 4–8 voci).
- `runner._pump` legge un carattere alla volta in modalità testo: su un run di
  TopicGPT con migliaia di righe di progresso costa CPU; leggere a blocchi e
  spezzare su `\r`/`\n`.
- `study.verdicts()` esegue la cross-validation completa per disegnare il
  registro: con la cache per-workspace è pagata una volta, ma andrebbe resa
  asincrona sul disco (`output/cache/verdicts.json` con fingerprint dei
  dataset), come già fatto per le relazioni.
- `views_participation._read` e `views_words._dataset` rileggono il CSV da
  disco a ogni richiesta; un lettore con `mtime` in chiave evita di rileggere
  16 MB per ogni pannello.

### M5 — Robustezza della pipeline

- `pipeline.run` scrive i dataset **prima** di sapere se TopicGPT è fallito
  (giusto), ma `archive.save` copia il report senza le colonne dei topic e
  `failed_stage` è solo in `run.json`: il report dovrebbe portare un banner.
- `aggregate.aggregate_level`: `median_gap_seconds` usa l'elemento superiore
  con un numero pari di intervalli; `statistics.median` come in `corpus.shape`.
- `text_metrics.standardize` con `n < 2` restituisce `z = 0`, `_100 = 50` per
  ogni riga: un dataset di un gruppo mostra tutti "50" senza avviso.

### M6 — Dipendenze e distribuzione

- Il vincolo `anthropic<1`/`openai<2` viene da TopicGPT. Valutare un fork
  minimale di TopicGPT (i prompt sono nel repository, il codice Python è poco)
  o un extra `topics-legacy` separato, così il rubric può usare lo SDK
  corrente.
- htmx 2.0.4: nessuna advisory nota, ma è vendorizzato senza hash né versione
  nel nome file; aggiungere `htmx-2.0.4.min.js` e un test che confronti l'hash.
- CI: il job `extras` non installa RELATIO, quindi il percorso di estrazione
  reale non è mai eseguito in CI. Un job settimanale con `install-relatio` su
  un corpus sintetico di 200 messaggi basterebbe.

### M7 — Un solo tokenizzatore

Tre moduli tokenizzano diversamente (B6, B17). Un `core/tokens.py` con una
funzione sola, usata da `text_metrics`, `nrc`, `words`/`compare`
(`CountVectorizer(tokenizer=...)`) e `corpus.find`, rende i conteggi
confrontabili fra pagine e apre alla localizzazione (vedi M10).

### M8 — Test da aggiungere

1. Modalità libreria: due esperimenti con configurazione identica → cache
   distinte (B1).
2. Modalità libreria: ogni link nella pagina di un run risponde 200 (B2).
3. Compare con outcome per persona 0/1 e yes/no (B3, B5).
4. BH contro `statsmodels` (B4).
5. Vocabolario contiene "i" (B6).
6. Nome esperimento di 70 caratteri (B14).
7. Pagina Run di B mentre A gira (B10).
8. Un test "documentazione vs codice": ogni comando citato in `handbook/` esiste
   nel parser (`test_docs.py` controlla i link, non i comandi).

### M9 — Dati personali

`--pseudonymise` è ben fatto. Due aggiunte utili per l'approvazione etica:
una scansione opzionale dei testi per nomi propri/e-mail/URL (spaCy `PERSON`
o espressioni regolari) che **segnali** senza modificare, con il conteggio nel
manifest del bundle; e la registrazione nel `run.json` di quale provider ha
ricevuto i testi (già implicito in `rubric.provider`, assente per i topic
quando `api` è un gateway `OPENAI_BASE_URL`).

### M10 — Lingua

`text_metrics` è dichiaratamente solo inglese (`TOKEN_RE = [a-z]+`). Con un
corpus italiano gli indici LIWC-style valgono zero e il tool lo dice solo in un
commento del codice. Serve almeno un rilevatore (quota di token nei dizionari
funzionali < 5 % su tutto il corpus → avviso in pagina), e in prospettiva
dizionari per lingua caricabili dal TOML come già per `commitment`.

---

## 6. Piano per priorità

| Priorità | Voce | Sforzo | Effetto |
|---|---|---|---|
| 1 | B1 cache per workspace; B3 guard su unità; B5 `as_binary` | ore | pagine corrette in libreria; niente 500 |
| 1 | B2 prefisso `active.base()` nei link ai run | minuti | link funzionanti |
| 1 | B4 BH monotona | minuti | q-value corretti nel paper |
| 2 | B6 token di un carattere; B7 `clean` solo su trascrizioni; M7 tokenizzatore unico | 1 giorno | coerenza delle misure |
| 2 | B8 pipeline nei fold; B9 test appaiato; U3 nome colonna `C` | 1–2 giorni | confronto difendibile |
| 2 | B12 tema; B13 tastiera; U6 `forget_route` | ore | UX |
| 3 | B10 runner per esperimento; B11 timeout sul lock | 1–2 giorni | più studi in parallelo |
| 3 | M3 validazione umana del rubric + α/ICC | 2–3 giorni | validità del rubric |
| 3 | M2 stability selection, Fightin' Words, conditional logit | 3–5 giorni | analisi nuove (vedi proposta) |
| 4 | M1 fine dello stato globale | 1 settimana | base per tutto il resto |
| 4 | M6 fork TopicGPT / SDK 1.x; M9 PII; M10 lingua | variabile | distribuzione |

Le voci di priorità 1 sono correzioni a comportamento sbagliato e andrebbero
fatte prima di qualunque uso della dashboard con più di uno studio. Le voci di
priorità 2 cambiano numeri che entrano in un articolo e vanno fatte prima di
generare le tabelle definitive.

---

## 7. Riferimenti citati in questo documento

- Benjamini, Y., Hochberg, Y. (1995). Controlling the false discovery rate.
  *JRSS-B* 57(1), 289–300.
- Çelebi, C., Penczynski, S. P. (2026). Much Ado about Prompting: LLM
  classification of text messages from experiments. *PLOS ONE*.
  https://doi.org/10.1371/journal.pone.0354757
- Egami, N., Hinck, M., Stewart, B. M., Wei, H. (2023). Using Imperfect
  Surrogates for Downstream Inference: Design-based Supervised Learning for
  Social Science Applications of Large Language Models. *NeurIPS 2023*.
  arXiv:2306.04746.
- Ludwig, J., Mullainathan, S., Rambachan, A. (2024). Large Language Models:
  An Applied Econometric Framework. arXiv:2412.07031.
- McFadden, D. (1974). Conditional logit analysis of qualitative choice
  behavior. In P. Zarembka (ed.), *Frontiers in Econometrics*, 105–142.
- Meinshausen, N., Bühlmann, P. (2010). Stability selection. *JRSS-B* 72(4),
  417–473. arXiv:0809.2932.
- Monroe, B. L., Colaresi, M. P., Quinn, K. M. (2008). Fightin' Words: Lexical
  Feature Selection and Evaluation for Identifying the Content of Political
  Conflict. *Political Analysis* 16(4), 372–403.
- Nadeau, C., Bengio, Y. (2003). Inference for the Generalization Error.
  *Machine Learning* 52(3), 239–281.
- Pangakis, N., Wolken, S., Fasching, N. (2023). Automated Annotation with
  Generative AI Requires Validation. arXiv:2306.00176.
- Törnberg, P. (2024). Best Practices for Text Annotation with Large Language
  Models. arXiv:2402.05129; *Sociologica* 18(2).
- Ziems, C., Held, W., Shaikh, O., Chen, J., Zhang, Z., Yang, D. (2024). Can
  Large Language Models Transform Computational Social Science?
  *Computational Linguistics* 50(1), 237–291. arXiv:2305.03514.
