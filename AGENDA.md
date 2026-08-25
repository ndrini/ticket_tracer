# Ticket Tracer

Una macchina che trasforma fotografie di scontrini in dati interrogabili: quanto si è speso, in cosa, dove, come cambia nel tempo.
Gli scontrini della spesa 2025 sono il materiale su cui è nata, non il suo confine.

Questo file è il documento d'ingresso: dice **cosa esiste già** (per non riscriverlo) e **a che punto siamo** (per non riaprire fronti chiusi).
Va letto per intero prima di scrivere codice.
Nasce da un episodio concreto: `scripts/` contiene quindici file di cui buona parte morta, e più di una volta è stato scritto uno strumento che c'era già.

---

## ⭐ ADESSO — 2026-08-23

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

**Il kernel.** `notebooks/kaggle_estrai_gpu.py` importa `app/etl/` dal dataset invece di riscrivere l'estrazione: un'unica implementazione, così locale e GPU restano confrontabili.

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
