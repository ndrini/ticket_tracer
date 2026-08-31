# Ticket Tracer

Una macchina che trasforma fotografie di scontrini in dati interrogabili: quanto si è speso, in cosa, dove, come cambia nel tempo.
Gli scontrini della spesa 2025 sono il materiale su cui è nata, non il suo confine.

Questo file è il documento d'ingresso: dice **cosa esiste già** (per non riscriverlo) e **a che punto siamo** (per non riaprire fronti chiusi).
Va letto per intero prima di scrivere codice.
Nasce da un episodio concreto: `scripts/` contiene quindici file di cui buona parte morta, e più di una volta è stato scritto uno strumento che c'era già.

---

## ⭐ ADESSO — 2026-08-30

Ramo `feat_UI_for_review`. Costruita un'**interfaccia di revisione umana**
(`scripts/revisione_umana.py`, porta 8098): foto d'origine orientata, ritaglio,
righe estratte, e due domande separate — il taglio e' buono? i dati sono giusti?
Registra un giudizio in `manual_review_queue`, non corregge nulla.
Quando una foto ha prodotto piu' ritagli, delle schede in cima li mostrano tutti
e la coda li tiene consecutivi (prima distavano 78 posizioni in mediana).

Ingerite le 24 foto del 2026: 14 nuove, 39 scontrini. Dieci erano duplicati
riconosciuti dall'hash percettivo, quattro dei quali duplicavano foto del 2025.
Sono a meta' pipeline: hanno ritagli e OCR, non sono nel database.

### Cosa dicono i 33 giudizi umani

| misura | valore |
| --- | --- |
| ritaglio giudicato buono | 28/33, **85%** |
| scontrini con dati giusti | **0/33** |
| righe scartate al caricamento perche' senza nome | 237/1752, **14%** |
| **valore economico che non entra nel database** | **2054 EUR su 6133, 33%** |
| righe nel database il cui nome NON e' un prodotto | 98/1556, 6% |
| totale stampato letto male (dichiarato dall'umano) | 7/28, 25% |

**Il collo di bottiglia non e' ne' il ritaglio ne' l'OCR: e' l'ASSOCIAZIONE
nome/prezzo.** Sullo scontrino #137 PaddleOCR produce 91 righe di testo coi nomi
catalani corretti (`Alberginia`, `Cogombre`, `Pastanaga`) e nel database ne
arrivano 3. L'OCR restituisce ogni parola separata: nome e prezzo non sono mai
sulla stessa riga, e il collegamento va ricostruito per coordinate.

**Il 33% del valore sparisce in silenzio.** L'estrattore geometrico trova il
PREZZO e lascia il NOME vuoto (in uno scontrino, 9 righe su 12); poi
`fase_d_carica_db.py` chiama `trova_o_crea_prodotto()`, che restituisce `None`
sul nome vuoto, e salta la riga con un `continue` senza lasciare traccia. Uno
scontrino da 849,64 EUR perde il 100% del proprio valore.

### Il VLM e' stato provato e scartato

Confronto dichiarato prima di misurare (`docs/122_metrica_confronto_vlm.md`),
LLaVA 1.5 7B su 28 ritagli col taglio buono, su T4 di Kaggle e in locale:
**geometrico 0/28, VLM 0/28**, e sconfitta netta sulle guardie (23 risposte su
28 illeggibili). Il VLM **inventa prodotti plausibili**: `MATTRESS 399,00 EUR`
su uno scontrino IKEA da 16,00 EUR, il nome del negozio preso per un prodotto,
e una risposta che ha ricopiato l'esempio del prompt. Su uno scontrino la sua
somma era 30,10 contro 30,47 stampati — quasi perfetta grazie a una riga
inventata da 21,90: senza le metriche di guardia sarebbe sembrata una vittoria.

Il geometrico sbaglia in modo VERIFICABILE, il VLM no. Motivazione corretta per
lo scarto: senza GPU stabile e con necessita' di verificabilita' automatica, un
VLM generico aggiunge complessita' senza beneficio misurato.

### ⚠️ Il pezzo dimenticato

`app/etl/righe_logiche.py` ricompone i frammenti OCR nelle righe fisiche
**seguendo la pendenza del testo**, e' testato e misurato. Lo importano
`fase_c_estrazione.py` (ramo LLM) e i test.

**`scripts/fase_c_geometrica.py` NON lo importa** — e ha prodotto 287 scontrini
su 306. Usa `abs(y - y_addendo) >= 0.5 * altezza`, confronto orizzontale che
ignora l'inclinazione. Misurato: mediana 0 gradi (la maggior parte e' dritta),
ma il 10% peggiore sta a 2,1 gradi e il massimo a 4,2 — 15-30 px di dislivello
su righe alte ~30 px. Trovato da Gemini leggendo il codice, non dalle misure.

### Il prossimo passo, col consenso di Perplexity e Gemini (Vibe non ha risposto)

1. **Collegare `righe_logiche.py` al ramo geometrico.** Codice gia' scritto e
   testato; i 33 giudizi fanno da metro. ← in corso
2. **Smettere di scartare le righe senza nome.** Salvarle marcate incomplete,
   **fuori dal catalogo prodotti** (entrambi gli agenti insistono su questo:
   nei report come "spesa non classificata", mai come categoria). Da' anche lo
   strumento per misurare quanto il punto 1 migliora le cose.
3. **Rendere esplicito il dubbio sul totale stampato** invece di trattarlo come
   verita': serve un campo di affidabilita', o separare il contante dal totale.
4. **TODO — template per catena.** Idea dell'utente: marcare a mano in una
   interfaccia dove stanno il nome della catena, la struttura delle righe, il
   totale e lo sconto; poi riconoscere lo scontrino e applicare il template, con
   ripiego sul metodo generico per i mai visti. Misurato a supporto: 5 formati
   coprono il 44% del corpus, 10 il 57%, e il layout e' stabile dentro la catena
   (colonna prezzi al 89% della larghezza da Consum, 96% da Mercadona, dev.st
   6-7 punti). Da sottoporre agli agenti prima di implementare.

⚠️ Questi numeri sui formati **contraddicono in parte** la nota in fondo a
questo file ("quattro catene coprono il 22,5%, il 47% viene da negozi visti una
volta sola"). La differenza e' il metodo: qui il raggruppamento e' per firma
dell'intestazione OCR con fusione delle varianti (`MERCADONA`/`MERCADUNA`,
`CONSUM`/`ONSUM`), non per il nome del negozio nel database — che e'
inaffidabile, come mostra la tabella sopra. Va rifatto per bene prima di
decidere sui template.

### Critiche degli agenti da tenere presenti

Perplexity ha smontato tre conclusioni piu' forti dei dati: "l'OCR non e' il
collo di bottiglia" viene da UN scontrino; "il ritaglio funziona" da 33 su 287;
il rifiuto del VLM vale per quel setup, non in generale. E ha colto il buco
vero: **non era mai stata misurata la correttezza delle righe che ENTRANO** nel
database — solo quelle perse. Misurato poi: il 6% dei nomi non sono prodotti
(`%`, `a iva`, `art. total a pagar`, `kg 0,70 EUR/kg`).

---

## Passato — 2026-08-23


Ramo `feat_step_A`. Ultimo commit `8239bc0`, estrazione su GPU Kaggle.

Le fasi **A** (ingestione), **B** (verifica sul totale), **C** (estrazione), **D** (caricamento) sono scritte e girano.
317 scontrini estratti dalle 96 foto, 218 strutturati, caricati in `data/spese.db`.

I numeri di oggi, misurati sui 218 scontrini in `data/strutturati/`, non stimati:

| misura | valore |
| --- | --- |
| estrazione su GPU T4 di Kaggle | **2,20 s/scontrino** |
| estrazione in locale, senza GPU | 40-75 s/scontrino |
| preparazione fissa del kernel (vLLM + pesi + compilazione) | ~120 s per esecuzione |
| totale letto per coordinate | 169/218, **78%** |
| **scontrini che quadrano** (somma righe == totale) | **62/218, 28%** |

Il problema aperto è quel 28%. Lo scarto sta su **entrambi i lati** del confronto — 70 scontrini con la somma in difetto, 23 in eccesso, 57 senza nessun prodotto — e non sappiamo caso per caso se a sbagliare sia il totale o l'elenco.

⚠️ **25 totali su 218 sono inventati.** Quando la lettura geometrica fallisce, il modello viene interrogato e riporta un numero che nell'OCR non compare da nessuna parte. Il caso `0260bfd2f37f` ha `total = 15.90` e non è nemmeno uno scontrino: è un buono sconto Milbby. Il danno non resta lì, perché `prodotti()` usa il totale per scartare le righe troppo care: un totale gonfiato non filtra più niente, uno troppo basso scarta prodotti veri.

### Il prossimo passo

In ordine. Prima ciò che costa solo tempo macchina, poi ciò che costa tempo umano.

1. **Congelare un insieme di regressione sulla quadratura.** Non esiste: `data/verita_riferimento.json` copre la segmentazione (riquadri su 6 foto), non l'estrazione. Senza, le metriche di guardia dei due passi seguenti si misurano su un materiale che cresce, e un confronto prima/dopo non è più un confronto. Costa zero crediti — il giudice aritmetico è già scritto in `app/etl/verifica.py` e `app/etl/totale.py` — e va fatto **prima** di toccare il codice, non dopo.
2. **Togliere il ripiego al modello per il totale.** In `EstrattoreScontrino.totale()`, via il ramo che interroga qwen2.5:3b; totale non leggibile ⇒ `None`, esito `TOTALE_ASSENTE`. Si passa da 212 a 169 scontrini col totale: è la stessa informazione, senza 25 numeri falsi. Deciso col consenso degli agenti; la misura che ha sciolto il disaccordo è che i 18 casi da salvare quadrano al 22%, peggio del 34% delle coordinate. La pipeline lo regge già, 6 scontrini hanno `total = None` oggi.
3. **Insegnare al lettore le etichette italiane.** `ETICHETTA_TOTALE` in `app/etl/totale.py` conosce solo spagnolo e catalano: `\btotal\b` non aggancia `TOTALE`. Recupera fino a 21 dei 75 fallimenti, in modo deterministico. Attenzione a `Subtotal`, che non è un totale e va escluso. Metrica di guardia dichiarata prima: nessuno dei 169 totali già corretti deve cambiare, e i recuperati devono quadrare almeno quanto la media, 34%.
4. **Invertire l'ordine del prompt**, da `[DOMANDA][SCONTRINO]` a `[SCONTRINO][DOMANDA]`, con delimitatori espliciti. Vale ~27 s per scontrino in locale (prefill della seconda chiamata: 28,0 s contro 0,8 s), misurato A/B/A/B su quattro cicli. Serve solo finché si gira in locale: su GPU il prefill è sotto il secondo.
5. **~~Capire i 57 `PRODOTTI_ASSENTI`~~ — INDAGATI il 2026-08-24.** Non sono un fallimento del modello: su otto scontrini riletti a mano dall'immagine, **nessuno** lo era. Quattro meccanismi distinti, tutti a monte dell'LLM o nelle assunzioni del codice a valle:
   - **Layout a piu' righe per prodotto** (nome su una riga, importo su quella dopo, alla IKEA e Cal Fruitos). Misurato: domina il **28%** dei `PRODOTTI_ASSENTI` contro il **5%** dei `VALIDO`. `_e_riga_prodotto` pretende nome e importo sulla STESSA riga e li scarta entrambi. E' il meccanismo piu' frequente, ed e' un'assunzione sbagliata nel codice, non un difetto dell'OCR.
   - **Ritagli con piu' scontrini dentro.** Casi `8b760724d949` (Decathlon+Pepco), `989d19fad56a` (tre scontrini), `325c72d0d73c` (Decathlon con due strisce ai bordi). La ricomposizione incolla orizzontalmente colonne di scontrini diversi. Il divario orizzontale fra i frammenti OCR li rivela: 18% dei `PRODOTTI_ASSENTI` contro 3% dei `VALIDO`.
   - **Documenti che prodotti non ne hanno.** `3d6f44d1de1b` e' l'intestazione di una fattura IKEA con due paragrafi di informativa privacy, nient'altro. `PRODOTTI_ASSENTI` e' l'esito CORRETTO; il totale 129,50 e' inventato. Vanno riconosciuti e marcati, non estratti meglio — probabilmente esiste lo scontrino gemello con la stessa data.
   - **Resi.** `11b9b668a333` (IKEA, `Anul.la el tiquet`, tre `Devolucio`, pagamento −58,98) e `325c72d0d73c` (Decathlon, quantita' −1, −6,99) non sono acquisti. Trattarli come tali falsa i conti a monte di qualunque estrazione.

   Nessuno dei quattro agenti consultati aveva previsto i resi ne' i documenti senza prodotti; li ha trovati la rilettura a mano. Il campione, con i quattro meccanismi e le misure, sta in [docs/46_campione_validato_a_mano.md](docs/46_campione_validato_a_mano.md). I casi validati dall'utente sono A `8b760724d949`, B `989d19fad56a`, C `0ba230e1ebee`, D `3d6f44d1de1b`, E `20e8047e9163` (totale vero **40,58**, letto 24,09), F `11b9b668a333`, G `152cf78ab94f`, H `325c72d0d73c`.

   ⚠️ **Il «16/16» della segmentazione e' misurato su 6 foto di riferimento e non descrive il materiale reale**: su otto ritagli, tre contengono piu' scontrini o tagliano via i prodotti.
6. **Normalizzare i nomi dei negozi.** `MERCADONA`, `MERCADUNA` e `Mercadona` sono tre commercianti distinti nel database. Unendo le varianti, Mercadona passa da 18 a 32 scontrini.
7. **Fase E** — catalogo prodotti e alias, poi **F** — categorizzazione, poi **G** — report. In quest'ordine: categorizzare nomi non ancora fusi significa rispondere più volte alla stessa domanda.

---

## ⛔️ Cosa NON si fa adesso, e perché

Ognuna di queste è stata valutata e sospesa. Riproporla senza un dato nuovo è lavoro sprecato.

**Ripiego deterministico sul totale**, cioè una regex sul testo piatto invece delle coordinate. Misurato: allargando la regex a una cifra decimale si recuperano 7 totali ma se ne rompono 9 già corretti, bilancio −2. Limitandolo al secondo tentativo non rompe nulla, ma nessuno dei 7 recuperati quadra: sono importi troncati dall'OCR, `13,50` contro una somma di `13,55`. È lo stesso numero inventato del ripiego al modello, prodotto da una regex invece che da un LLM.

**Template di scontrino per negozio.** Il difetto sta prima di sapere di che negozio si tratta, il costo è ricorrente e silenzioso quando la catena cambia layout, e si perde il caso che conta di più: il bar, il negozio in vacanza. L'alternativa che tiene il vantaggio senza la rigidità sono profili **appresi** dagli scontrini che quadrano — ma richiede il controllo somma/totale funzionante, quindi non è una scorciatoia per il problema di oggi. Ragionamento esteso in [private/decisioni.md](private/decisioni.md).

**LLM multimodale sull'immagine.** Serviva a sostituire segmentazione e OCR quando la segmentazione non funzionava. L'OCR legge — verificato a mano su otto scontrini — e costerebbe API a pagamento o una GPU di fascia alta per rifare un lavoro già fatto. Due argomenti tecnici in più, dagli agenti: gli scontrini sono lunghi e stretti, i VLM riscalano a risoluzioni quadrate e renderebbero le cifre illeggibili; e un VLM rifarebbe il riconoscimento senza toccare il difetto vero, che è il layout a più righe. ⚠️ Il «16/16» della segmentazione **non** è più un argomento valido qui: è misurato su 6 foto di riferimento, e su otto ritagli riletti a mano tre contengono più scontrini o tagliano via i prodotti. Separare i ritagli resta un problema aperto, ma si risolve nella segmentazione, non con un VLM.

**Fondere le chiamate `negozio` e `prodotti`.** Con la cache di prefisso la seconda costa 0,8 s invece di 6 s: non vale il rischio di qualità.

**Ottimizzazioni di Ollama** — `num_thread=4`, `num_ctx=1024`, migrazione a `/api/chat` con sessioni. Stimate al 20-30% da un agente, misurate come nulle: 29,3 s → 28,2 s, dentro la varianza. La quantizzazione era già Q4_K_M.

**Spendere crediti per confrontare modelli di frontiera.** Non perché il dataset cresce, ma perché i passi 1-4 non li richiedono e vengono prima: la baseline è già misurata in locale col giudice aritmetico, e finché il prefill e le etichette non sono sistemati non si sa quanta parte del 28% dipenda davvero dal modello. Se ne riparla dopo, sull'insieme congelato. Le stime di costo circolate finora — «~130 inferenze con 10 $ al giorno» — vengono da un prezzo per token inventato sul momento: sono un ordine di grandezza, non un dato, e il listino non l'ha letto nessuno.

**Cercare il sottoinsieme di prodotti che somma al totale.** Scartata per principio: produrrebbe una quadratura apparente su dati sbagliati. Meglio un buco dichiarato che un numero inventato.

---

## Da dove si comincia

Tre puntatori, per le domande che tornano più spesso.

- **Come si lavora qui, e perché così** — [docs/20_analisi_e_strategie_sviluppo.md](docs/20_analisi_e_strategie_sviluppo.md), sezione 0. Il metodo, con gli episodi che l'hanno generato. La sezione 9 è il registro delle decisioni condivise.
- **Come si passa da una foto con tre scontrini ai tre scontrini** — [docs/30_estrazione_singole_immagini.md](docs/30_estrazione_singole_immagini.md), incluso cos'è l'IoU e perché si misura così.
- **Come si passa dal testo OCR ai campi** — [docs/40_dal_testo_ai_dati.md](docs/40_dal_testo_ai_dati.md), con la sezione 5-bis sul taglio della coda, che è la correzione che ha portato più guadagno.

Poi: [docs/50_guida_kaggle.md](docs/50_guida_kaggle.md) per la GPU gratuita, [docs/45_groq_come_fornitore.md](docs/45_groq_come_fornitore.md) per le seconde opinioni via API, [private/decisioni.md](private/decisioni.md) per le scelte vincolanti, [private/BACKLOG.md](private/BACKLOG.md) per le milestone lontane.

---

## ⭐ I tre vincoli che non si negoziano

**Tutto in locale.** Nessuna immagine esce dalla macchina. Gli scontrini dicono dove sei stato, quando, cosa mangi e quanto guadagni: sono dati personali densi. Su Kaggle sale **solo il testo OCR**, 5,4 MB invece di 36 MB, con `foto_origine` rimosso da un controllo scritto separato dalla scrittura, che blocca l'upload se il campo sopravvive. La conseguenza accettata è la rinuncia all'accuratezza dei servizi cloud.

**Il lavoro sporco resta su file rifacibili.** I livelli grezzo ed estratto stanno su disco, non in tabelle relazionali. Correggere significa cancellare un file e rilanciare un passo, non fare UPDATE incrociati. La scelta si è già ripagata tre volte: i 317 scontrini sono stati rielaborati per le foto capovolte, per i ritagli sbagliati e per il filtro sulla coda.

**Si segnala, non si corregge d'ufficio.** Un controllo che non è certo produce un avviso, non una modifica. Un dato marcato come dubbio resta verificabile; uno corretto in silenzio no. Ogni stato di dubbio deve però avere una via d'uscita, altrimenti la marcatura diventa un alibi.

---

## Gli esiti della verifica

Sono un contratto: il codice, il database e i report li usano per nome.

| esito | significato | quanti oggi |
| --- | --- | --- |
| `VALIDO` | la somma delle righe corrisponde al totale stampato | 62 (28%) |
| `SOMMA_IN_DIFETTO` | righe perse dall'estrazione | 70 (32%) |
| `SOMMA_IN_ECCESSO` | righe di troppo, spesso la coda di pagamento | 23 (11%) |
| `PRODOTTI_ASSENTI` | nessuna riga prodotto estratta | 57 (26%) |
| `TOTALE_ASSENTE` | il totale non è leggibile | 6 (3%) |

I due versi dello scarto sono nomi distinti apposta: sono difetti diversi, con cause diverse, e vanno aggrediti separatamente.

---

## Dove sta cosa

**I dati.** `data/2025_scontrini/` le 96 foto in ingresso; `data/ritagli/` i 317 ritagli, uno per scontrino, identificati dall'hash SHA-256; `data/estratti/` il testo OCR con le coordinate; `data/strutturati/` i 218 JSON per scontrino; `data/spese.db` il database SQLite, `data/test_spese.db` quello dei test; `data/verita_riferimento.json` la verità di riferimento per la metrica IoU; `data/foto_viste.json` il registro delle foto già lavorate.

**I moduli.** In `app/etl/`: `segmenter.py` separa gli scontrini nella foto, `etl_engine.py` l'OCR, `righe_logiche.py` ricompone i frammenti in righe stampate, `riduci_testo.py` accorcia il testo prima di interrogare il modello, `coda.py` taglia la parte sotto il totale, `totale.py` legge il totale per coordinate, `estrattore.py` interroga l'LLM, `plausibilita.py` segnala i prezzi impossibili, `verifica.py` confronta somma e totale. In `app/db/`: `db_manager.py` e `inserter.py`. In `app/stat/`: tre query fisse.

**Gli script.** Quelli vivi: `fase_a_ingestione.py`, `fase_c_estrazione.py`, `fase_d_carica_db.py`, `kaggle_carica_dataset.py`, `kaggle_lancia_kernel.py`, `confronta_gpu_locale.py`, `metrica_iou.py`, `segmenta_detector.py`. Gli altri sono residui: si estende ciò che c'è, non si aggiunge accanto.

**Il kernel.** `notebooks/kaggle_estrai_gpu.py` importa `app/etl/` dal dataset invece di riscrivere l'estrazione: un'unica implementazione dei parser.

⚠️ **Ma locale e GPU NON danno gli stessi risultati, e il codice condiviso non basta a garantirlo.** Sotto girano due motori diversi — Ollama con il modello quantizzato Q4, vLLM con lo stesso modello in float16 — e rispondono in modo diverso alla stessa domanda. Misurato il 2026-08-25 su 316 scontrini: l'84% delle risposte GPU ripeteva l'intera lista dei prodotti dopo un commento («Ho riportato le righe come richiesto:»), e la somma usciva esattamente doppia; molte altre riorganizzavano nomi e prezzi in elenchi separati, e il filtro le scartava tutte. Gli scontrini che quadrano sono crollati **dal 28% al 3%**, senza che il codice avesse un difetto. La stessa passata rifatta in locale su un campione di 12 scontrini che quadravano: **12/12 quadrano ancora**.

La lezione non riguarda la GPU ma il metodo: **chiedere a un modello di copiare del testo e interpretare la risposta con espressioni regolari è fragile**, perché il formato della risposta dipende dal motore. La cura è imporre lo schema al decoder invece di sperarci — vedi `app/etl/schema_risposta.py`. E una baseline prodotta con un motore non vale come termine di paragone per l'altro.

---

## Il ciclo di lavoro

```
 foto ──▶ [1] GREZZO ──▶ [2] ESTRATTO ──▶ [3] NORMALIZZATO ──▶ [4] CATEGORIZZATO ──▶ [5] REPORT
          ritagli +       JSON per         prodotti            categoria per          mese
          testo OCR       scontrino        canonici + alias    prodotto canonico      anno

          fase A          fasi B, C, D     fase E              fase F                 fase G
          FATTA           FATTE            da fare             da fare                da fare
                          ⭐ qui si vince
```

Il vantaggio della separazione è concreto: cambiando la tassonomia al livello 4 non si riesegue nulla dei livelli 1-3, che sono i costosi.
Il collo di bottiglia della qualità sta al livello 2, ed è lì che vanno i prossimi tre passi.

---

## Avvio

```bash
uv run python scripts/fase_a_ingestione.py     # foto → ritagli → testo OCR
uv run python scripts/fase_c_estrazione.py     # testo → campi strutturati
uv run python scripts/fase_d_carica_db.py      # strutturati → database
```

Su GPU, quando gli scontrini sono molti:

```bash
uv run python scripts/kaggle_carica_dataset.py              # prova a vuoto, non carica niente
uv run python scripts/kaggle_carica_dataset.py --esegui --limite 10
uv run python scripts/kaggle_lancia_kernel.py --esegui
uv run python scripts/kaggle_lancia_kernel.py --stato
uv run python scripts/kaggle_lancia_kernel.py --scarica
uv run python scripts/confronta_gpu_locale.py               # metriche di guardia
```

Test: `uv run pytest -q` per i moduli, `uv run pytest -m integration` per ciò che richiede Ollama o immagini reali.

---

## ⚠️ Cose da sapere che non si deducono dal codice

**Ogni passo è idempotente, e va tenuto tale.** Rilanciare non duplica: l'identità di uno scontrino è l'hash del suo ritaglio, e `receipts.image_sha256` è UNIQUE. Le foto duplicate arrivate da fonti diverse — backup, WhatsApp — sono riconosciute con un hash percettivo. Il materiale crescerà a lotti, quindi l'idempotenza non è una comodità ma un requisito.

**Il dataset non è chiuso.** Le 96 foto sono una frazione di quelle disponibili. Ogni soluzione va valutata su come regge al volume, non su quanto migliora i 218 scontrini di oggi. La prima stesura del documento 20 assumeva un archivio storico e chiuso, e ne traeva conseguenze architetturali sbagliate.

**Il collo di bottiglia locale è la lettura del prompt, non la generazione**: vale il 72-95% del tempo. È per questo che l'ordine del prompt conta più di qualunque impostazione di Ollama.

**Su Kaggle serve `NvidiaTeslaT4` con la maiuscola esatta.** `nvidiaTeslaT4` viene accettato senza errore e ignorato: arriva una P100, capability `sm_60`, incompatibile col PyTorch preinstallato. Il modello si carica, scarica i pesi e muore alla prima inferenza. L'avviso c'è nel log ma non ferma l'esecuzione. Altre trappole già pagate: lo slug del kernel deve corrispondere al titolo, `isPrivate` è annidato sotto `info` nel metadata scaricato, e `kaggle kernels output` salta il download se trova una copia locale più recente — serve `--force`.

**Smoke test su una sola immagine prima di ogni kernel nuovo.** I fallimenti sopra si manifestano tutti nei primi trenta secondi, ma solo se si guarda dopo trenta secondi invece che dopo l'ora. E mai oltre l'ora di GPU per esperimento: il budget settimanale è finito, e un lavoro lungo che fallisce alla fine ha bruciato un ottavo della settimana per non dire niente.

**L'ipotesi "quattro catene coprono il 70% dei casi" è falsa.** Mercadona, Consum, Bonpreu e Lidl coprono il **22,5%**. Il dato che conta per la strategia: **103 scontrini su 218, il 47%, vengono da negozi visti una volta sola**. Va rifatto dopo la normalizzazione dei nomi, che oggi falsa il conteggio.

**CAA = cerca accordo con gli altri**: sottoporre il proprio piano a Gemini, Vibe e Perplexity prima di decidere. Serve per le scelte irreversibili o che toccano la semantica dei dati — schema, tassonomia, regole di fusione. Non per soglie e regex, dove bastano la misura e i test. Il criterio non è la difficoltà tecnica ma quanto costa accorgersi tardi dell'errore. E il consenso non è una prova: gli agenti si sono già sbagliati, e una misura li ha corretti.

**RISOLTO il 2026-08-30.** `parse_raw_data()` aveva due tipi di ritorno: sul
ramo normale `list[str]` (le righe ricostruite, cio' che il chiamante aspetta),
sul ramo "OCR vuoto" un `dict` `{"shop_name": "Unknown", ...}`, residuo di un
contratto precedente. Ora il ramo vuoto restituisce `[]`.

`tests/test_ocr.py` e' stato riscritto sul contratto vero: asseriva
`"shop_name" in parsed_data`, che su una lista cerca un ELEMENTO — passava per
la ragione sbagliata e nascondeva il difetto invece di rivelarlo. Quattro test
al suo posto, compreso il ramo vuoto che nessuno provava.

**Una diagnosi mia sbagliata, corretta misurando.** Avevo attribuito allo stesso
difetto anche `tests/repro/test_dia_20_88.py`, perche' produceva gli stessi
dizionari `{"shop_name": "Unknown", ...}`. La causa e' un'altra: il test chiede
`llama3.1:latest`, che non e' installato (ci sono qwen2.5, llava, moondream,
granite). `OllamaProcessor` cattura l'errore e restituisce quel dizionario di
ripiego, cosi' il sintomo si somiglia. Ora il test verifica il modello PRIMA,
come gia' faceva con l'immagine, e salta dicendo la causa vera invece di
fallire su "DIA non trovato" mandando a cercare un difetto nell'estrazione.

## Lo sfasamento nome/prezzo sui formati a peso

Misurato il 2026-08-30 su tutti i 325 strutturati, partendo da un caso segnalato
dall'utente (`5c9a9ede1206e1bb4e0ec35188e6aa34065399ee372c3a0999306ecd8ae0c314`,
fruttivendolo "Cal Fruitos"). Confrontando la miniatura col JSON, **ogni prezzo
e' attaccato al prodotto sbagliato**, sfasato di una riga:

| sulla carta | nel JSON |
|---|---|
| Poma Royal Gala 1,45 | Taronja -> 1,45 |
| Taronja 1,62 | "" -> 1,62 |
| Alvocat 4,00 | Alvocat -> 4,00 |
| Ous Ecologics 5,90 | "" -> 5,90 |

Causa: su questi formati il nome sta su una riga e quantita'/prezzo unitario su
quella sotto. L'estrattore le allinea male — a volte le fonde (nome sporco), a
volte le sfasa (prezzo sul prodotto sbagliato).

**Perche' e' grave: l'aritmetica non puo' accorgersene.** I prezzi sono tutti
quelli giusti, solo appaiati male, quindi la somma quadra al centesimo (12,97,
`scarto: 0.0`, `esito: VALIDO`). Questo caso si salva solo perche' ha due nomi
vuoti e `esamina()` lo ferma per `nomi_mancanti` — motivo giusto, ragione
sbagliata. Se i nomi fossero stati tutti pieni sarebbe passato per **chiuso** e
finito nel DB certificato come buono.

### I numeri

    quadra, tutti i nomi        178   <- passerebbero per chiusi
    non quadra, tutti i nomi     83
    non quadra, con nomi vuoti   41
    quadra, con nomi vuoti       23   <- l'aritmetica assolve, il testo accusa

Dei 178 "buoni", **38 (21%) hanno la riga del peso finita dentro il nome del
prodotto** (`"kg 2,90 EUR/kg"` come nome, `"BANANA 0,650 kg 1,55 EUR/kg"`):
stessa causa, altra manifestazione. E' un **limite inferiore**, non una stima:
conta solo i casi con una traccia testuale. Lo sfasamento pulito non lascia
firma nel JSON e si vede solo contro l'immagine.

Non e' una catena sola: fra i 178 c'e' **un solo** "Cal", e molti hanno
`shop_name` a `None`. E' trasversale ai formati a peso.

### Conseguenza operativa

**La fase D non va eseguita finche' questo non e' risolto**: verserebbe nel DB
dati sfasati con lo stato `chiuso` a garantirli. Meglio il buco dichiarato del
numero inventato.

Da fare: un controllo che riconosca la riga-peso e la usi per verificare
l'accoppiamento (prezzo ~= quantita' x prezzo_unitario), invece di fidarsi
della sola somma. Corregge anche il conteggio: oggi non sappiamo quanti dei
178 siano davvero puliti.

### La causa, trovata nel grezzo OCR (2026-08-30)

`data/estratti/<sha>.json` conserva ogni frammento con testo, confidenza e
coordinate. Ricomponendo le righe per centro verticale — come fa la fase
geometrica — si vede il difetto nascere:

     y  conf  testo
   175  0.85  Sdpto 1  13.05 2025  kg  Poma Royal Gala Extra  Caja 1  EUR/kg
   236  0.99  0,418  Taronja Extra Cal Fruitos  3,48  1,45
   272  0.90  0,544  Pza  Alvocat...  Dus Ecologics "M/L"...  2,98  4,00  1,62
   343  1.00  2  2,95  5,90

`Poma Royal Gala` e' risucchiata nell'INTESTAZIONE. La riga 236 porta il nome
`Taronja` ma i numeri della Poma (0,418 x 3,48 = 1,45). La riga 272 fonde TRE
prodotti e QUATTRO numeri. Da qui lo sfasamento di uno nel JSON finale.

**L'OCR non c'entra: confidenza minima 0,85, quasi tutte a 0,99-1,00.** Testo,
decimali e accenti catalani sono letti perfettamente. Il difetto e' solo nella
ricomposizione delle righe.

Causa: il raggruppamento usa il **solo centro verticale**. Sulle righe a peso il
nome e i numeri stanno su due mezze righe sfalsate, e i centri finiscono piu'
vicini fra righe diverse che dentro la stessa.

**Questo rende il difetto piu' riparabile di quanto sembrasse**: l'informazione
mancante e' gia' nel file. Le colonne sono nettissime (0,418 a x~0, 3,48 al
centro, 1,45 a destra) e non vengono usate. Un raggruppamento che consideri
anche la x — o che riconosca la coppia nome-riga/numeri-riga come UNA voce —
ricostruirebbe le righe senza toccare l'OCR.

## Chiuso: la deduplica scartava foto nuove in silenzio (2026-08-30)

Nato da una domanda dell'utente: "se ricarico la stessa foto, la duplico?".
Verificando la risposta (no, viene riconosciuta) e' emerso il rovescio.

**Il difetto.** Il dhash della foto INTERA decideva da solo: sotto soglia 8 ->
`return 0,0,0`, foto ignorata senza un avviso. Ma il dhash guarda la SCENA, non
lo scontrino: ridotte a 8x8 pixel in grigio, due foto di carta chiara sullo
stesso tavolo scuro sono identiche.

Misurato su tutte le 6216 coppie del registro (112 foto):

    distanza minima fra foto DIVERSE: 0     (il commento nel codice diceva 23-31)
    coppie gia' sotto soglia: 112
    anche a soglia 0 restano 3 collisioni

Verifica visiva delle due a distanza 0: Consum+Dia di gennaio contro
Alcampo+Milbby di aprile. Negozi, date e importi diversi. **110 foto nuove su
112 sarebbero state buttate senza lasciare traccia.**

**La correzione** (CAA: Gemini, Vibe e Perplexity concordi, nessuna riserva):
il phash non decide piu', da' solo i SOSPETTI; il verdetto lo da' il testo OCR,
confrontando gli insiemi di parole (Jaccard). Chi non e' certo si elabora
comunque e si marca `sospetto_duplicato_di` nel JSON: e' la regola del progetto
— segnalare, non correggere d'ufficio — applicata dove prima non c'era nemmeno
il buco dichiarato.

Costo nullo nel caso normale: il testo si confronta solo per le poche foto che
collidono nel phash.

**Le soglie, misurate e non indovinate:**

    foto DIVERSE      mediana 7.5%   p95 31.2%   MASSIMO 38.5%
    duplicati VERI    93.6%, 100%

55 punti vuoti in mezzo. Poste a 45%/40% (erano 50%/20% prima di misurare: 20%
segnalava 18 coppie palesemente diverse). Risultato sui dati veri:

    duplicati veri -> scartati    2 / 2
    foto diverse   -> elaborate 110 / 110

**Un caso che il vecchio criterio sbagliava**: `IMG-20250103-WA0001.jpg` e
`2025-01-03 10.22.03.jpg` sono lo stesso scontrino eMISFERO arrivato dal
telefono e da WhatsApp. I ritagli differiscono di 2 pixel, quindi gli sha256
sono diversi e "scontrini in comune" li dava per distinti. Il testo li
riconosce al 93,6%. E' il caso che lo sha non sa vedere.

**Chiusa anche la rotazione** (2026-08-30). Gli agenti divergevano, e la
misura ha deciso: funziona, ma non nel modo ovvio.

Comprimere le 4 rotazioni in un hash solo (il minimo) e' la soluzione che viene
in mente per prima ed e' sbagliata: il minimo puo' solo ACCORCIARE le distanze,
e su 58 foto portava le coppie sotto soglia da 0 a 10, cioe' peggiorava proprio
il difetto appena chiuso. Costo +10,6x (44 -> 470 ms).

Si ruota invece la foto NUOVA e si confronta coi 4 orientamenti, tenendo UN hash
per foto nel registro. Le distanze fra le foto archiviate restano identiche
(112 coppie sotto soglia, invariato), il formato del registro non cambia, e il
costo si paga una volta sola in ingestione.

Provato sul codice vero: la stessa foto a 0, 90 e 180 gradi -> DUPLICATO al 100%
in tutti e tre i casi. Prima passava per nuova (distanza 29-32).

## Ricostruzione delle righe: metriche dichiarate PRIMA (2026-08-30)

CAA a tre, concordi: soglia relativa all'altezza + centro della banda +
sovrapposizione verticale; accoppiamento nome/numeri verificato dall'aritmetica;
avviso e non correzione quando non torna.

Si scrivono qui PRIMA di misurare, altrimenti la metrica si adatta al risultato.

### Metrica principale

    bande che fondono piu' prodotti     58% degli scontrini  ->  < 10%

### Metriche di guardia (non devono peggiorare)

    coerenza aritmetica righe a peso    92% (169/184)  ->  >= 92%
    frammenti orfani (non assegnati)     0%            ->    0%
    scontrini con somma che quadra     201/325 (62%)   ->  >= 62%

Quest'ultima e' una guardia, NON una prova: quadrava anche col difetto (il caso
Cal Fruitos quadrava al centesimo coi prezzi tutti sul prodotto sbagliato). Serve
solo a scoprire se la nuova ricostruzione rompe cio' che oggi funziona.

### Cosa conta come fallimento

Bande fuse sopra il 20%, oppure una qualunque guardia che peggiora.

### La soluzione ESISTE GIA' nel progetto (2026-08-30)

Avevo cominciato a scrivere un modulo nuovo. **Errore mio: non avevo cercato
prima.** `app/etl/righe_logiche.py` esiste dal 25 agosto, ha 14 test, ed e' piu'
completo di quello che stavo scrivendo — corregge l'INCLINAZIONE della foto
prima di raggruppare (`inclinazione()`), e ricuce le righe spezzate
(`_ricuci_righe_spezzate`), che era esattamente la domanda B del CAA. Il mio
duplicato e' stato cancellato.

Misurato sui 359 scontrini veri, righe che fondono piu' prodotti:

    parse_raw_data()          (15px fissi, in uso in etl_engine)   85   24%
    righe_logiche.ricomponi() (gia' esistente, usato da fase_c)    27    8%

**Tre volte meglio, e c'era gia'.** Sul caso segnalato dall'utente ricostruisce
tutto correttamente:

    0,418  Poma Royal Gala Extra      3,48  1,45     0,418 x 3,48 = 1,45
    0,544  Taronja Extra Cal Fruitos  2,98  1,62     0,544 x 2,98 = 1,62
           Alvocat Extra Cal Fruitos        4,00
    2      Dus Ecologics "M/L"        2,95  5,90     2 x 2,95 = 5,90

### Perche' allora i dati sono sbagliati: la vera causa

`scripts/fase_c_geometrica.py` — che produce `data/strutturati_geometrici/`,
cioe' i file con lo sfasamento — **non usa `righe_logiche`**. Usa
`app/etl/geometria.py`, e accoppia nome e prezzo cosi':

    def nome_per_addendo(righe_ocr, y_addendo, x_addendo, altezza):
        """Il nome che sta a SINISTRA dell'addendo, sulla sua stessa riga."""
        if abs(y - y_addendo) >= 0.5 * altezza:   # STESSA RIGA
            continue

Cerca il nome **sulla stessa riga fisica dell'importo**. Ma sui formati a peso
il nome sta sulla riga SOPRA: non lo trova, e prende quello che capita a
sinistra — che appartiene a un altro prodotto. Da qui i nomi vuoti e lo
sfasamento.

Non e' un difetto di ricostruzione delle righe: e' `fase_c_geometrica` che
presume un layout a una riga. Il pezzo che sa gestire le due righe esiste gia'
e non e' collegato.

### Da fare (non ancora fatto)

Collegare `righe_logiche.ricomponi()` a `fase_c_geometrica`, o portare in
`nome_per_addendo` la ricucitura che `righe_logiche` fa gia'. Poi rielaborare i
359 estratti (costa secondi, i frammenti OCR sono su disco) e rimisurare le
metriche dichiarate sopra. La fase D resta sospesa fino ad allora.


## TODO: due miglioramenti indicati dall'utente (2026-08-31)

Nati guardando lo scontrino #197 nella pagina di revisione: un giustificativo
BBVA da 8,90 EUR, sbiadito, dentro una foto che ne contiene quattro. Stato
SOMMA_IN_DIFETTO, scarto -36,70, confidenza 0%, "nessuna riga estratta".

### a. Riconciliare i pagamenti elettronici con gli scontrini d'acquisto

Il giustificativo della carta NON e' uno scontrino della spesa: non ha prodotti,
ha un solo importo. Oggi finisce fra i "da ripassare" e ci resta per sempre,
perche' non potra' mai quadrare — non c'e' niente da sommare.

Ma non e' rumore: e' la PROVA DI PAGAMENTO dell'acquisto, e con quello condivide
DATA e ORA. Vanno riconciliati, non scartati.

Cosa serve prima di implementare:
  - MISURARE quanti sono. Un primo dato c'e' gia': su 24 foto del 2026-06-21,
    almeno uno (70d579b7..., "VENDA - OPERACIO CONTACTLESS", 24,44 EUR).
    Marcatori riconoscibili nel testo: VENDA/VENTA, CONTACTLESS, TARG.:****,
    AUT, "Visa Credit", ETIQ.APLIC.
  - Verificare che data+ora bastino davvero come chiave. L'ora del pagamento e
    quella di stampa dello scontrino differiscono di poco ma differiscono: serve
    una TOLLERANZA, e va misurata sui casi veri, non scelta a intuito.
  - Attenzione al caso in cui l'importo del pagamento NON coincide col totale
    dell'acquisto (pagamento parziale, contante+carta). Segnalare, non fondere.

E' una decisione sulla SEMANTICA dei dati (introduce un tipo di documento nuovo
e una relazione fra record): vuole il CAA prima di implementare.

### b. Bianco/nero o piu' contrasto prima dell'OCR

Ipotesi dell'utente: gli scontrini sbiaditi (come il BBVA della foto) si
leggerebbero meglio con una binarizzazione o un aumento di contrasto.

Plausibile, ma NON verificato. Prima di toccare la pipeline va misurato, perche'
e' esattamente il tipo di intervento che puo' migliorare una metrica e romperne
un'altra: una soglia troppo aggressiva mangia il testo chiaro sul termico.

Come misurarlo onestamente:
  - metrica principale: righe OCR lette con confidenza >= 0.8
  - guardia: numero di frammenti totali (non deve crollare: sarebbe testo perso)
  - guardia: scontrini che quadrano (non deve calare)
  - campione: gli scontrini oggi ILLEGGIBILI o a confidenza bassa, non quelli
    che gia' funzionano — su quelli il margine di miglioramento e' zero e il
    rischio di peggiorare no.
  - confronto A/B sullo STESSO ritaglio, non su foto diverse.

Da provare in ordine di invasivita': CLAHE (contrasto locale) < scala di grigi
semplice < binarizzazione adattiva (Sauvola/Otsu). PaddleOCR e' addestrato su
immagini a colori: la binarizzazione potrebbe togliergli informazione, non darne.
Va verificato, non assunto.

Nota: il preprocessing andrebbe applicato al RITAGLIO, non alla foto intera —
il fondo (tavolo di legno) ha un contrasto diverso dalla carta e falserebbe
qualunque soglia globale.
