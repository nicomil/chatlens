# Piano di miglioramento UI/UX: comprensione e orientamento

17 settembre 2026. Non ripete l'audit di correttezza del 12 settembre.
Affronta un problema diverso: trovare la pagina giusta, capire cosa fa, sapere
che esiste. Ogni punto è stato verificato navigando davvero l'interfaccia
(screenshot reali, `curl`) o leggendo il codice che la genera.

> **Stato (aggiornato lo stesso giorno).** Implementati e verificati: A1, A2,
> A3, B (con la scelta B2), e la scorciatoia economica di C — vedi in fondo a
> ogni fase. D resta aperto.

---

## Cosa succede oggi, verificato

### 1. Il registro si riordina da solo pochi istanti dopo il caricamento

`web/ui.py:register()` ordinava le voci per verdetto prima che per logica
narrativa: `{YES: 0, NO: 1, OPEN: 2, UNAVAILABLE: 3}`, poi per `order`
all'interno dello stesso verdetto. Il primo render (`views_findings.page()`)
mostra le voci nell'ordine narrativo corretto perché i verdetti non sono
ancora noti — ma la barra laterale fa subito `hx-get
.../findings/register?on=... hx-trigger="load"` per prendere i verdetti veri,
e a quel punto si riordinava. Su uno studio dove Words ed Emotions risultano
"non aggiungono nulla" (verdetto NO), quelle due voci saltavano in cima, sopra
"What was said" e "Who spoke to whom" — le pagine di orientamento che un nuovo
arrivato dovrebbe vedere per prime.

Verificato con screenshot reale (`example-study-synthetic`): la barra laterale
mostrava "The words ✕" e "The emotions ✕" come prime due voci, "What was
said" terza. Il segno ✕ in cima, al primo sguardo, legge come "qualcosa è
rotto" più che "due risultati negativi ma informativi".

### 2. Nessun ponte fra il nome del metodo e il nome della pagina

Inventario di ogni titolo (`ui.finding()`, primo argomento) nel codice:

| Voce nel registro | Titolo (H1) mostrato | Metodo che nasconde |
|---|---|---|
| What was said | "What was said?" | statistiche del corpus |
| Who spoke to whom | "Who spoke to whom, and who did not?" | matrice di partecipazione |
| Which representation to trust | "Which representation of the text is worth using?" | confronto a modelli annidati, AUC, B8/B9 |
| The words | "Which words go with {esito}?" | **bag of words**, regressione logistica penalizzata |
| The relations | "Read as who does what to whom…" | RELATIO, estrazione SVO |
| The emotions | "What emotional content is in these conversations?" | lessico NRC |

Nessun titolo conteneva mai il nome tecnico del metodo. È una scelta di design
deliberata e giusta per chi non sa cosa cerca — ma è il motivo esatto per cui,
chiedendo "posso fare una bag of words?", quel termine non compariva da
nessuna parte nell'interfaccia. Confermato anche nel pannello "How to read
this" della pagina Words: spiegava "a penalised regression" ma non usava mai
la frase "bag of words".

### 3. Rubric e Topics non hanno una pagina nel dashboard (U4/U5)

`web/views_findings.py:BODIES` ha sei voci: `corpus, participation, compare,
words, narratives, emotions`. Nessuna voce `rubric` o `topics`. I risultati
della rubric LLM e di TopicGPT — le due fasi a pagamento — esistono solo nel
report statico (`core/report.py`, generato una volta per run), mai nel
registro dinamico del dashboard.

### 4. La guida illustrata era invisibile dall'app in esecuzione

`GUIDE.md` (con screenshot di ogni pagina, pubblicata su
`https://nicomil.github.io/chatlens/guide/`) non era linkata da nessun punto
del dashboard: `grep -rn "glossary|handbook|guide|GUIDE.md" src/chatlens/web/*.py`
dava zero risultati.

### 5. L'aiuto in-app esiste ma è usato una volta sola

`views._help()` disegna un punto interrogativo con tooltip accessibile
(`data-tip` + `aria-describedby`). Componente pronto, usato solo sui campi del
form di Run.

---

## Piano, per costo crescente

### Fase A — Additiva, a rischio quasi zero

1. **Un sottotitolo col nome tecnico sotto ogni H1.** `ui.finding()` ha ora un
   parametro `method: str = ''`, reso come `<p class="method-tag muted">`
   subito sotto l'`<h1>`. Applicato a Words ("Bag of words: unigrams and
   bigrams, penalised logistic regression"), Narratives ("RELATIO:
   subject-verb-object extraction"), Emotions ("NRC Emotion Lexicon"), Compare
   ("Nested models, paired AUC, Nadeau-Bengio correction").
   **Fatto** — `src/chatlens/web/ui.py`, `views_words.py`,
   `views_narratives.py`, `views_emotions.py`, `views_compare.py`,
   `static/style.css` (`.method-tag`).
2. **Un indice dei metodi.** `ui._glossary()`, una `disclosure()` sempre in
   fondo al registro (non solo sulla pagina di export, così è visibile da ogni
   pagina): bag of words → The words, RELATIO → The relations, NRC → The
   emotions, modelli annidati → Which representation to trust, rubric/topics →
   il report del run. **Fatto** — `src/chatlens/web/ui.py:register()`.
3. **Link alla guida da dentro l'app.** Un link `Guide` nel masthead, verso
   `https://nicomil.github.io/chatlens/guide/`, già pubblicata via
   `.github/workflows/docs.yml`. **Fatto** — `ui.py:shell()`,
   `static/style.css` (`.guidelink`).

### Fase B — La correzione strutturale

4. **Verdetti NO spostati in fondo insieme a UNAVAILABLE.** Scelta B2 del
   piano: `order = {YES: 0, OPEN: 1, NO: 2, UNAVAILABLE: 3}` invece di
   `{YES: 0, NO: 1, OPEN: 2, UNAVAILABLE: 3}`. Una riga, preserva "le risposte
   prima degli ostacoli" (un sì resta in cima) senza il salto visivo che ha
   confuso la lettura di questa sessione. **Fatto** — `ui.py:register()`.

### Fase C — Colmare lo split report/dashboard

5. **La scorciatoia economica**: l'indice dei metodi (punto 2) porta già,
   per rubric e topics, un link diretto al report del run
   (`/experiment/<slug>/report.html`) invece di lasciare chi cerca quei
   risultati senza alcuna indicazione. **Fatto**, come parte del punto 2.
   **Non fatto**, e resta una decisione a parte: due pagine vere nel registro
   (con verdetto, tabella, correlazione con gli indici) — costa diversi giorni,
   da pianificare se serve prima dei due paper.

### Fase D — Igiene minore, non ancora affrontata

6. Estendere `views._help()` alle intestazioni delle pagine di finding più
   dense (Compare, Words) per i termini che restano tecnici anche col
   sottotitolo (`AUC`, `Nadeau-Bengio`, `min_df`).
7. La correzione allo stato di U4/U5/U7 nell'audit del 12 settembre è fatta,
   vedi lo status block aggiornato in quel documento.

---

## File toccati

| File | Intervento |
|---|---|
| `src/chatlens/web/ui.py` | `finding(method=...)`, `register()` ordine (B2) e `_glossary()`, `shell()` link guida |
| `src/chatlens/web/views_words.py`, `views_narratives.py`, `views_emotions.py`, `views_compare.py` | costante `METHOD`, passata a ogni `ui.finding(...)` |
| `src/chatlens/web/static/style.css` | `.method-tag`, `.glossary`, `.guidelink` |
| `reviews/2026-09-12-audit-problemi-e-miglioramenti.md` | stato di U4/U5/U7 corretto |

## Verifica

1. `make test` — nessuna regressione.
2. `ruff check .` pulito.
3. Navigazione reale col browser sul demo `example-study-synthetic`: la barra
   laterale non mostra più i verdetti NO come prime voci; "bag of words",
   "RELATIO", "NRC" sono ora letteralmente in pagina, cercabili con Ctrl+F;
   il link Guide apre la guida pubblicata.

## Aperto, da decidere con l'utente

- Se investire in Fase C vera (pagine Rubric/Topics complete) o restare con la
  scorciatoia del link al report, dato il tempo che i due paper richiedono ora.
