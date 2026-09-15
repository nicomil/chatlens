# Nota metodologica: due studi, due replication package

13 settembre 2026, aggiornata il 14 dopo le risposte dello sperimentatore.
Riferita alla collezione `coalition-formation` e alle due analisi che ne
escono: *baseline vs public* (studio 1) e *baseline vs slacker* (studio 2).

> **Cornice, decisa il 14 settembre.** L'analisi testuale è **esplorativa**: non
> stima effetti causali, fornisce regressori che possono spiegare l'aumento o la
> diminuzione della probabilità che l'esito valga 1 nel logit. La scelta dei
> regressori, la standardizzazione e il LASSO sono dello sperimentatore, in
> Stata. Chatlens consegna tutti i blocchi di misure, grezzi, in un CSV.

Questa nota risponde per iscritto a tre cose decise in chat — i due campioni
separati, la correzione B8, la riformulazione B9 — e a una domanda che era
rimasta aperta: «facciamo sempre approccio unsupervised, data driven, giusto?».
La risposta breve è no, e non per distrazione: le misure di questo strumento
stanno su tre livelli diversi di *quanto* vengono dai dati, e il fatto che la
pagina di confronto esista serve esattamente a non dover scegliere a priori
quale livello funziona meglio.

---

## 1. Che cosa è data-driven e che cosa è a priori

| Misura | Da dove viene la struttura | Dipende dai dati? |
|---|---|---|
| Indici in stile LIWC (`analytic_cdi`, `clout_raw`, `authenticity_raw`, `tone_raw`) | dizionari e formula pubblicati, applicati alla lettera | **no**: categorie e pesi sono fissi. Solo la standardizzazione (`_z`, `_100`) usa media e varianza del campione |
| NRC, otto categorie emotive | lista di parole pubblicata | **no**, per costruzione |
| Sentiment VADER | dizionario più regole | **no** |
| Bag of words (pagina *Words*, blocco «testo» del confronto) | vocabolario indotto dal corpus, coefficienti stimati contro l'esito | **sì**, ma è *supervisionato*: nessuna lista di parole scelta a mano, e la penalizzazione è un controllo che si muove |
| Temi TopicGPT | i temi sono indotti dai documenti | **sì**, completamente non supervisionato (con `--topicgpt-unsupervised` non c'è nemmeno una lista di partenza) |
| Relazioni RELATIO | il raggruppamento delle frasi è automatico, le **entità sono dichiarate** | **in parte**: senza entità dichiarate il metodo mette `i` e `you` nello stesso gruppo e il parlante smette di essere distinguibile da chi ascolta |
| Rubric LLM | le dimensioni del giudizio sono dichiarate a priori, il punteggio è del modello | **no** sulla griglia, **sì** sul singolo giudizio |

Quindi la risposta è che il disegno mescola tre cose volutamente: dizionari a
priori, induzione dai documenti, e un modello supervisionato con vocabolario
indotto. La pagina *Compare* mette tutte queste rappresentazioni contro lo
stesso esito, sulle stesse righe e sulle stesse partizioni, perché è l'unico
modo onesto di dire quale delle tre aggiunge qualcosa su questo corpus invece di
deciderlo in base a quale è di moda.

Una conseguenza pratica per la scrittura: l'unica cosa che va dichiarata come
scelta *a priori* nei due articoli sono le entità di RELATIO (`i`, `you`, `we` e
i colori) e le dimensioni della rubric. Tutto il resto è o un dizionario
pubblicato e citabile, o indotto dai dati.

---

## 2. B8, separazione train/test: come è implementata

Come da tua indicazione, ogni cosa che *impara* qualcosa dai dati sta dentro una
`Pipeline` scikit-learn adattata solo sul training di ciascun fold:

- `GroupKFold` a 5 fold, con i **gruppi interi** tenuti fuori: le sei righe
  diadiche di una triade non possono trovarsi metà in stima e metà in test;
- dentro il fold, e solo sul training: costruzione del vocabolario (`min_df`),
  pesi TF-IDF, standardizzazione, stima del modello;
- il test viene solo trasformato, mai usato per adattare niente.

Un'eccezione dichiarata: la pagina *Words* continua ad adattare il modello su
tutte le righe, e lo dice. Quella lista di coefficienti è una **descrizione del
corpus**, non una stima fuori campione, e la pagina serve a guardare quali
termini sopravvivono alla penalizzazione muovendola. Ogni numero che finisce in
un intervallo di confidenza, invece, passa dalla pipeline dentro il fold.

**Quanto cambiava, in pratica.** Misurato sul corpus vero: la differenza fra il
vecchio codice e questo è sotto il rumore fra fold (dell'ordine di 0,0005 di AUC
contro una dispersione fra fold di 0,015). Il motivo è che i passi che
perdevano informazione — soglia di frequenza minima e standardizzazione — non
guardano l'esito, quindi il vantaggio che davano era quasi nullo. Lo scrivo
esplicitamente perché è il tipo di affermazione che va verificata e non
supposta: la ragione per correggerlo è che un replication package deve essere
difendibile riga per riga, non che il numero si sia mosso.

---

## 3. B9, valore predittivo incrementale: come è implementato

Esattamente lo schema che hai descritto.

- **Baseline**: `esito ~ log(numero di parole + 1)`. È l'ipotesi nulla
  dell'analisi testuale: i documenti lunghi contengono più di tutto.
- **Modello per blocco**: `esito ~ log(parole + 1) + X`, dove X è, uno alla
  volta, il blocco lessicale, il bag of words, le relazioni, le emozioni, i
  temi, i punteggi della rubric.
- **Stesse partizioni** per tutti i modelli, così la differenza è **appaiata**:
  `d_f = AUC(baseline + X) − AUC(baseline)` calcolata fold per fold.
- **Errore standard** con la correzione per la sovrapposizione fra fold di
  Nadeau e Bengio (2003): `sd(d) · sqrt(1/k + n_test/n_train)`. Senza quella
  correzione l'errore standard della media di cinque numeri non indipendenti è
  sottostimato, e l'intervallo risulta più stretto del vero.
- **Intervallo al 95%** con la t a k−1 gradi di libertà.
- **Holm** step-down fra i blocchi, coerente con la sezione 6 del piano di
  analisi.
- **Verdetto a tre stati**: *aggiunge qualcosa* se il limite inferiore supera
  zero e la media supera la differenza minima di interesse; *non aggiunge
  niente* se il limite superiore sta sotto quella soglia; altrimenti **troppo
  vicino per dirlo**. Il terzo stato è il caso più frequente con qualche
  centinaio di gruppi, e prima non c'era modo di scriverlo.

### Un dettaglio che cambiava i numeri, e che vale la pena sapere

La prima versione usava una penalizzazione L1 (lasso) per tutti i modelli del
confronto. Con l'unica colonna del baseline — il logaritmo delle parole — una
L1 abbastanza forte la azzera: il baseline restava a AUC esattamente 0,500 in
ogni fold, e ogni differenza risultava gonfiata di circa mezzo punto con
varianza nulla. Il confronto adesso usa una **ridge (L2)** per tutti i modelli,
e il lasso resta solo dove serve a *selezionare* termini, cioè nella pagina
*Words*. Verificato su dati sintetici con e senza segnale:

| Dati | Differenza | Intervallo 95% |
|---|---|---|
| con segnale | +0,554 | da +0,478 a +0,630 |
| senza segnale | +0,019 | da −0,137 a +0,175 |

Cioè: senza segnale l'intervallo contiene lo zero, che è il comportamento che ci
serve per non pubblicare rumore.

### La soglia, con le numerosità vere

La differenza minima che il disegno riesce a risolvere dipende dalla
numerosità, e separare i due studi la peggiora. Misurata sulla forma vera dei
dati:

| Campione | Gruppi | Errore standard corretto | Differenza minima risolvibile |
|---|---|---|---|
| Studio 1 | 355 | ≈ 0,020 | ≈ 0,040 |
| Studio 2 | 356 | ≈ 0,020 | ≈ 0,040 |
| Collezione unica | 531 | ≈ 0,015 | ≈ 0,030 |

La regola decisa: **un effetto che il disegno e la numerosità non permettono
di osservare non viene considerato.** È implementata così: ogni blocco deve
superare il maggiore fra 0,02 e la *differenza minima osservabile*, cioè la
semiampiezza del suo intervallo al 95%. La pagina di confronto la mostra in una
colonna sua, così la soglia è un numero sulla pagina e non una proprietà del
codice. Con 355 gruppi questo porta la soglia effettiva intorno a 0,04; su un
disegno più preciso resterebbe 0,02.

Nella cornice esplorativa la pagina di confronto è un aiuto descrittivo, non un
test da riportare: i regressori li sceglie lo sperimentatore.

---

## 4. I due campioni, come vengono costruiti

`chatlens studies` riesegue lo stadio delle misure sulle righe di ciascuno
studio. Non è un filtro sul file finale, ed è per questo che va fatto così: le
colonne standardizzate sono z-score sul campione in analisi, e nelle tabelle
finali i valori di un'unità sono ripetuti su più righe (tre per le misure di
gruppo, due per quelle di diade), quindi ricalcolare media e deviazione su
quelle righe peserebbe i gruppi per quante righe hanno.

| | Bracci | Gruppi | Gruppi muti | Messaggi |
|---|---|---|---|---|
| Studio 1 | private 180 + public 175 | 355 | 5 | 5 861 |
| Studio 2 | private 180 + private_no_dwl 176 | 356 | 2 | 5 452 |

I gruppi muti — randomizzati e che non hanno scambiato nulla — **restano nel
file**. Escluderli è l'errore che la pagina *Participation* esiste per
mostrare: ogni misura testuale è calcolata su un campione condizionato
all'avere parlato, e quel condizionamento non appare in nessuna colonna.

Le colonne indipendenti dal campione (i punteggi grezzi, la rubric, i temi) non
vengono ricalcolate né ripagate: sono le stesse, e vengono riportate dal run
sulla collezione intera. Quelle che cambiano sono solo le `_z` e le `_100`.

**L'esempio concreto**, che è la ragione per cui non si possono mescolare i due
file: lo stesso partecipante del braccio baseline ha `clout_raw` 27,27 in
entrambi gli studi, e `clout_100` **59,77 nello studio 1 e 68,87 nello studio
2**. Non è un errore: è che la scala è il campione.

---

## 5. Che cosa contiene ogni cartella

```
output/studies/study1/
├── datasets/     le due tabelle, con i nomi che i do-file si aspettano
├── stata/
│   ├── <stem>_study1_goodshape.csv / .dta   il file per il logit
│   ├── <stem>_study1_complete.csv  / .dta   lo stesso più il bag of words, per il LASSO
│   └── <stem>_study1_codebook.csv           ogni colonna del file completo, con etichetta
└── study.json    quanti gruppi, quanti muti, per braccio
```

**Il file per il logit** (`goodshape`) contiene, dopo le 111 colonne
sperimentali, **tutti i blocchi di misure come valori grezzi**:

- indici e categorie in stile LIWC, sentiment, conteggi e tempi della chat;
- rubric LLM e temi TopicGPT, più **una dummy per tema**;
- emozioni NRC, in percentuale di parole;
- relazioni RELATIO: una dummy per relazione frequente, il loro numero e il
  testo di tutte;
- le versioni **ordinali da 1 a 4** delle quote di parole in una categoria
  (colonne `_lik`): 1 = assente, 2, 3 e 4 = terzo inferiore, medio e superiore
  dei casi in cui la categoria compare. I punti di taglio sono calcolati sullo
  studio e scritti nell'etichetta del codebook. Gli indici compositi (analytic,
  clout, authenticity, tone) e il sentiment non hanno uno zero naturale e
  restano solo grezzi.

Le copie standardizzate (`_z`, `_100`) **non ci sono**: la standardizzazione è
dello sperimentatore. Restano solo nei `datasets/`, per i do-file esistenti.

**Il file completo** (`complete`) è il file per il logit più il **bag of
words**: unigrammi e bigrammi come conteggi grezzi di quanto il partecipante
focale ha scritto al partner, una colonna per termine presente in almeno 10
documenti dello studio. I bigrammi sono presi dentro un messaggio, mai a cavallo
di due. Nessuna scelta guarda l'esito, quindi niente di questo può aver
anticipato quello che il LASSO stimerà.

| | Colonne goodshape | Unigrammi | Bigrammi | Colonne complete |
|---|---|---|---|---|
| Studio 1 | 356 | 407 | 501 | 1 264 |
| Studio 2 | 356 | 350 | 446 | 1 152 |

Con la soglia di 10 documenti il file completo si apre in ogni edizione di Stata,
compresa quella limitata a 2 048 variabili. La soglia si cambia con
`chatlens studies --bow-min-documents N`: a 5 i termini diventano circa 1 900.

Il `.dta` ha le etichette di variabile già dentro e il transcript come `strL`
quando supera i 2 045 byte. Se pandas non c'è, il `.dta` non viene scritto e non
è un errore: il CSV è il file che conta.

Deliberatamente **non** accanto al dataset pooled: `01_prepare.do` trova il suo
input con `dir "*_chat_by_partner_nlp.csv"` ed esce con codice 602 se i match
sono più di uno. Puntando `datasets` alla cartella dello studio i do-file girano
senza modifiche.

### Il file per Stata

Ricostruito dal tuo script, non reinventato: gli stessi 111 nomi di colonna, nel
tuo ordine, con `chat_group_key`, `chat_status`, i tre conteggi di messaggi e
`first_mover_chat` calcolati come li calcoli tu (compresa l'asserzione di
simmetria: i valori 1 devono pareggiare i valori 0). In coda le nostre misure,
con nomi già resi accettabili da Stata (≤ 32 caratteri, nessun punto,
identificatori validi).

**Verificato riga per riga** contro
`all_apps_wide_2026-09-10_chat_by_partner_goodshape_FINAL.csv`, con chiave
`(sessioncode, group_id, focal_player_id, partner_id)`:

- studio 1: 2 130 righe, tutte presenti anche nel tuo file;
- studio 2: 2 136 righe, tutte presenti anche nel tuo file;
- **110 delle 111 colonne identiche su ogni riga** in entrambi gli studi;
- l'unica differenza è `chat_transcript`: tu porti il JSON originale, noi la
  forma leggibile `Yellow->Orange: testo`, che è quella che ogni pagina e ogni
  misura di questo strumento legge. È voluta, non un disallineamento.

`persuasion_ij`, `S_ij`, `A_ji` e `C_ij` **non sono nel file**, come concordato:
le ricostruisci in Stata da `sendsignal_left/right` e `final_decision`. Le
nostre versioni restano in `output/datasets/`, dove i do-file le trovano già.

---

## 6. Il campione: le 12 sessioni

Deciso: le nove triadi senza label Prolific sono rumore, e il campione è fatto
**solo delle triadi generate in queste 12 sessioni**. La regola è dichiarata
nella configurazione dell'esperimento, non dedotta dalla label:

```toml
[sample]
sessions = ["w0k1pp1v", "um435zd7", "z7x47k43", "e3cj2oap", "vwv9fmlo", "sx78hwmu",
            "dblrbrkx", "ctx9bssc", "02b4rmbq", "7ay098t5", "0yqtmcrb", "bwcol55x"]
```

Verificato sul corpus reale: con la lista il merge è **identico byte per byte**
a quello di prima, 531 triadi (180 private, 175 public, 176 private_no_dwl), e
nessun partecipante resta escluso per la label. Le due regole coincidevano; ora
quella scritta nei paper è quella che il codice applica. Un codice di sessione
nella lista che non esiste nell'export ferma il merge, perché sarebbe un refuso
o l'export sbagliato.

Il file `FINAL.csv` dello sperimentatore contiene ancora le sette triadi in più
(538 gruppi): se viene usato come base, va filtrato sulle stesse 12 sessioni.

---

## Riferimenti

- Nadeau, C., Bengio, Y. (2003). *Inference for the Generalization Error*.
  Machine Learning 52, 239–281.
- Holm, S. (1979). *A Simple Sequentially Rejective Multiple Test Procedure*.
  Scandinavian Journal of Statistics 6, 65–70.
- Benjamini, Y., Hochberg, Y. (1995). *Controlling the False Discovery Rate*.
  JRSS B 57, 289–300.
- Pennebaker, J. W., Chung, C. K., Frazee, J., Lavergne, G. M., Beaver, D. I.
  (2014). *When Small Words Foretell Academic Success*. PLoS ONE 9(12), e115844.
- Mohammad, S. M., Turney, P. D. (2013). *Crowdsourcing a Word–Emotion
  Association Lexicon*. Computational Intelligence 29(3), 436–465.
- Ash, E., Gauthier, G., Widmer, P. (2024). *Relatio: Text Semantics Capture
  Political and Economic Narratives*. Political Analysis 32(1), 115–132.
- Pham, C. M., Hoyle, A., Sun, S., Iyyer, M. (2024). *TopicGPT: A Prompt-based
  Topic Modeling Framework*. NAACL 2024.
