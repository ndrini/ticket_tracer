# Strategia complessiva - Ticket Tracer

Dalle fotografie storiche degli scontrini ai report di spesa per **mese**, **anno**
e **tipologia** di prodotto.

Questo e' il documento di indirizzo dell'intero progetto. Il dettaglio della
sola segmentazione (foto con piu' scontrini -> ritagli singoli) sta in
[30_estrazione_singole_immagini.md](30_estrazione_singole_immagini.md).

---

## 1. Obiettivo e materiale

**Obiettivo.** Rispondere a domande come: quanto ho speso in gennaio, quanto in
un anno, quanto per categoria (alimentari freschi, bevande, pulizia casa...),
come varia la spesa nel tempo.

**Materiale.** 96 fotografie del 2025, che contengono **circa 288 scontrini**
(media ~3 per foto). Catene spagnole e catalane (Mercadona, Lidl, Consum, DIA,
Alcampo) e negozi non alimentari (IKEA, Decathlon, Intimissimi). Testo in
spagnolo e catalano.

**Natura del progetto: storico e chiuso, non un flusso continuo.** Le foto
esistono gia' e non aumenteranno. Questo ha una conseguenza precisa sulle
scelte architetturali: conviene privilegiare la **correggibilita'** (poter
tornare indietro e rifare un passo senza rifare tutto) rispetto alle
prestazioni o all'automazione completa. Una revisione manuale di mezz'ora su un
catalogo di poche centinaia di voci vale piu' di qualunque euristica.

---

## 1-bis. Nota terminologica: quale LLM, e a che serve

Nel progetto "LLM" indica **due cose diverse**, e confonderle fa sembrare aperta
una decisione che invece e' chiusa.

| | cosa riceve in ingresso | ruolo nel progetto |
|---|---|---|
| **LLM multimodale** (GPT-4o, Llava, Qwen-VL) | l'**immagine** | **nessuno: scartato** |
| **LLM testuale** (llama3.1, gia' in uso) | il **testo** prodotto dall'OCR | interpretare quel testo |

**Il multimodale e' fuori.** Serviva a sostituire segmentazione e OCR quando la
segmentazione non funzionava. Ora la segmentazione da' 16/16 e l'OCR legge il
testo, quindi non ha piu' ragione di esistere: costerebbe API a pagamento o una
GPU di fascia alta per rifare un lavoro gia' fatto.

**Il testuale resta indispensabile**, e la ragione e' che *l'OCR non dice quali
prodotti ci sono*: restituisce frammenti con delle coordinate. Un esempio reale:

```
"2 PATATES XURRE. CONS"   "1,10"   "2,20"
"4 XOC.70% CACAU LINDT"   "4,49"   "17,96"
"Total factura:"          "20,16"
```

Per arrivare da qui a una riga di database servono decisioni che l'OCR non
prende:

- il `2` iniziale e' una quantita' o parte del nome? E il `70` in `XOC.70%`?
- dei due numeri, quale e' il prezzo unitario e quale il totale di riga?
- `PATATES XURRE. CONS` e' catalano troncato: quale prodotto e', in italiano?
- `Total factura` e' una riga prodotto o il totale dello scontrino?
- delle ~200 righe rilevate, quali sono prodotti e quali IVA, codici fiscali,
  ringraziamenti?

E' **interpretazione semantica di testo**. Nessuna immagine coinvolta.

---

## 2. Stato attuale, verificato

### Funziona
- **Segmentazione foto -> scontrini singoli.** Risolta. Detector di righe di
  testo + taglio sulle colonne senza testo: 6/6 conteggi esatti sulle foto di
  sviluppo, 10/10 su dieci foto mai viste. Ritagli verificati a occhio.
- **Orientamento automatico** della foto: 8.9 s/foto.
- **Metrica IoU** per misurare la qualita' dei ritagli.

### Esiste ma e' grezzo
- **OCR**: PaddleOCR con `lang="es"`.
- **Estrazione dati**: LLM locale (Ollama, llama3.1) con schema Pydantic che
  estrae `shop_name`, `date`, `total`, `items[{name, original_name, price}]`.
- **Database** SQLite: `commerce_type`, `commerces`, `products`, `receipts`,
  `receipt_lines`.
- **Statistiche**: tre query fisse (totale per commercio, totale per prodotto,
  trend mensile).

### Le cinque lacune che bloccano l'obiettivo
1. **La categoria di prodotto non esiste da nessuna parte** — ne' nello schema
   estratto dall'LLM, ne' nella tabella `products` (che ha solo `name` e `aka`).
   Eppure il report per tipologia e' un requisito esplicito.
2. **Nessuna omogeneizzazione dei nomi.** Lo stesso pane compare come
   `PA DE PAGES`, `BARRA DE PA 3 U`, `PANET 11 UN`. Il campo `aka` esiste ma
   nessuna logica lo popola.
3. **Nessuna idempotenza.** Rilanciando la pipeline sulle stesse foto si
   inseriscono duplicati: non c'e' hash dell'immagine ne' vincolo di unicita'.
4. **Nessuna verifica di qualita'**, benche' ogni scontrino **contenga il
   proprio totale stampato** — un'occasione di auto-verifica oggi sprecata.
5. **Il database contiene solo dati di test** (1 scontrino, 2 prodotti).
   Nessun dato reale e' mai stato caricato.

---

## 3. Architettura: cinque livelli, non una pipeline unica

Il principio guida e' **separare il dato osservato dal dato consolidato**. Uno
schema che memorizza solo il risultato finale "gia' capito" costringe a
rifare l'OCR ogni volta che si cambia idea sulla categorizzazione.

```
 foto ──▶ [1] GREZZO ──▶ [2] ESTRATTO ──▶ [3] NORMALIZZATO ──▶ [4] CATEGORIZZATO ──▶ [5] REPORT
          ritagli +       JSON per         prodotti            categoria per          mese
          testo OCR       scontrino        canonici +          prodotto canonico      anno
                                           alias                                      tipologia
```

| livello | cosa contiene | si rifa' se... |
|---|---|---|
| 1 Grezzo | ritagli, testo OCR, output LLM integrale | cambia la segmentazione o l'OCR |
| 2 Estratto | un JSON per scontrino, indicizzato per hash | cambia il prompt o il modello |
| 3 Normalizzato | catalogo prodotti canonici + tabella alias | si corregge una fusione sbagliata |
| 4 Categorizzato | categoria per ciascun prodotto canonico | si cambia la tassonomia |
| 5 Report | aggregazioni per mese, anno, categoria | sempre, e' solo lettura |

Il vantaggio concreto: cambiando la tassonomia (livello 4) non si ri-esegue
nulla dei livelli 1-3, che sono i costosi.

---

## 4. Ordine delle fasi

L'istinto sarebbe "carico subito tutto nel DB, poi sistemo". **E' l'ordine
sbagliato**, e la ragione e' precisa: senza hash e senza catalogo, i dati
sporchi finiscono in tabelle relazionali dove correggerli richiede UPDATE
incrociati. Con i livelli 1-2 su file, invece, correggere significa cancellare
un file e rilanciare un passo.

### Fase A — Ingestione idempotente (livelli 1-2)
1. Per ogni foto: orienta, segmenta, ritaglia.
2. Calcola l'**hash SHA-256 di ogni ritaglio**: e' l'identita' dello scontrino.
3. OCR + LLM, salvando l'esito in `data/estratti/<hash>.json` insieme al testo
   OCR grezzo.
4. Un ritaglio gia' presente viene saltato. Rilanciare la pipeline diventa
   sicuro e incrementale.

**Perche' prima di tutto:** produce il primo dato reale su cui misurare il vero
tasso di errore su 288 scontrini, invece di stimarlo.

### Fase B — Verifica automatica (il totale come quality gate)
Ogni scontrino dichiara il proprio totale. Confrontarlo con la somma delle
righe estratte e' il controllo di qualita' piu' forte disponibile, e **non
costa nulla**: il dato c'e' gia'.

```
delta = |somma(righe) - totale_dichiarato|
```

Con una tolleranza (sconti, sacchetti, arrotondamenti) si assegna a ogni
scontrino uno stato: `VALIDO`, `DELTA_ECCESSIVO`, `PARSING_FALLITO`. Gli
scontrini non validi **vengono caricati comunque ma marcati**, cosi' i report
possono escluderli e si sa sempre quanta parte del totale e' affidabile.

Questo trasforma una domanda vaga ("funziona bene?") in un numero: *quanti
scontrini su 288 quadrano al centesimo*.

### Fase C — Catalogo prodotti e omogeneizzazione (livello 3)
1. Estrai i nomi prodotto **distinti** da tutti i JSON.
2. Mappa ciascuno su un **prodotto canonico** (nome italiano).
3. Salva la corrispondenza in una tabella di alias.

**Ordine di grandezza:** ~288 scontrini producono nomi distinti nell'ordine
delle **centinaia basse**. E' un catalogo che si **rivede a mano in mezz'ora**,
ed e' il motivo per cui questa fase e' praticabile.

**Metodo raccomandato: ibrido, con la revisione umana come autorita' finale.**
- normalizzazione testuale di base (maiuscole, spazi, caratteri spuri);
- LLM in *batch* sul catalogo per proporre nome canonico e traduzione;
- **esportazione in CSV, revisione umana, reimportazione.**

Il fuzzy matching puro (Levenshtein) e' stato scartato per una ragione
concreta: `PA DE PAGES` e `PANE CASERECCIO` sono lo stesso prodotto ma non
hanno alcuna somiglianza sintattica. Il problema qui e' **semantico e
multilingua**, non ortografico. Viceversa l'LLM da solo non e' affidabile per
decidere le fusioni; propone bene, decide male. Da qui l'ibrido.

### Fase D — Categorizzazione (livello 4)
**Sul catalogo dei prodotti canonici, non riga per riga durante l'estrazione.**

La ragione e' la coerenza: chiedendo la categoria a ogni riga di ogni
scontrino, lo stesso pane finisce in "Pane" su uno scontrino e in "Alimentari"
su un altro. Sul catalogo la domanda si pone **una volta per prodotto**, il
risultato e' coerente per costruzione, costa una frazione delle chiamate ed e'
revisionabile in blocco.

Tassonomia proposta, dimensionata su una spesa domestica reale (comprende i
negozi non alimentari presenti nel materiale):

| # | categoria |
|---|---|
| 1 | Alimentari freschi (carne, pesce, frutta, verdura) |
| 2 | Dispensa e confezionati (pasta, riso, conserve, olio, snack) |
| 3 | Latticini, uova e surgelati |
| 4 | Pane e pasticceria |
| 5 | Bevande (incluse alcoliche) |
| 6 | Cura della persona |
| 7 | Pulizia casa e consumabili |
| 8 | Abbigliamento e sport |
| 9 | Casa, arredo e bricolage |
| 10 | Varie e animali |

### Fase E — Report (livello 5)
Aggregazioni per mese, anno e categoria, con l'indicazione della **quota di
spesa proveniente da scontrini validi**: un totale senza quel dato non e'
interpretabile.

---

## 5. Modifiche necessarie al database

Lo schema attuale rappresenta solo il dato finale. Servono:

**In `receipts`:**
- `image_sha256 TEXT UNIQUE` — idempotenza
- `total_declared REAL` — il totale stampato sullo scontrino
- `total_computed REAL` — la somma delle righe
- `validation_status TEXT` — `VALIDO` / `DELTA_ECCESSIVO` / `PARSING_FALLITO`
- `validation_delta REAL`

**In `products`:**
- `category TEXT` — senza questo il report per tipologia e' impossibile
- il campo `aka` va sostituito da una **tabella di alias** vera:
  `product_aliases(raw_text, product_id, lingua)`. Un campo lista non
  interrogabile non risolve nulla.

**In `receipt_lines`:**
- verificare che `quantity` e `unit` vengano effettivamente popolati: oggi lo
  schema dell'LLM **non li estrae** (solo `name`, `original_name`, `price`),
  quindi le colonne restano vuote.

---

## 6. Sequenza operativa consigliata

1. **Integrare la segmentazione in `app/`** — oggi vive in
   `scripts/segmenta_detector.py`, fuori dalla pipeline ETL.
2. **Fase A**: hash, ritagli, OCR, estrazione su file. Nessun DB ancora.
3. **Fase B**: verifica sui totali. Da qui si conosce il tasso di errore reale.
4. **Migrazione dello schema** (sezione 5).
5. **Fase C**: catalogo prodotti + revisione manuale.
6. **Fase D**: categorizzazione + revisione manuale.
7. **Caricamento nel DB** dei dati gia' normalizzati e categorizzati.
8. **Fase E**: report.

Il caricamento nel database avviene **al punto 7**, non prima: e' la scelta
centrale di questa strategia. I dati entrano nelle tabelle relazionali solo
quando sono gia' puliti, mentre tutto il lavoro sporco resta su file
rifacibili.

---

## 7. Rischi noti

| rischio | mitigazione |
|---|---|
| L'LLM locale sbaglia l'estrazione su scontrini rovinati | La verifica sui totali (Fase B) li identifica invece di nasconderli |
| La traduzione catalano/spagnolo -> italiano introduce errori | Revisione umana del catalogo, che e' piccolo |
| I prodotti non alimentari (IKEA, Decathlon) inquinano le statistiche alimentari | Categorie 8-9 dedicate, separabili nei report |
| Scontrini illeggibili o parziali | Stato `PARSING_FALLITO`: contati, non ignorati |
| 288 scontrini restano un campione modesto | I report vanno letti come storia personale, non come statistica inferenziale |

---

## 8. Nota sulle strategie considerate in precedenza

La versione precedente di questo documento proponeva due alternative per la
sola segmentazione: **A) Vision-First** (delegare tutto a un LLM multimodale) e
**B) Deep Engineering** (addestrare YOLO su un dataset etichettato).

**Non e' stata adottata nessuna delle due.** La segmentazione e' stata risolta
con un detector di righe di testo pre-addestrato: nessuna API a pagamento
(Strategia A), nessun dataset da etichettare (Strategia B). Il ragionamento e
le misure sono in [30_estrazione_singole_immagini.md](30_estrazione_singole_immagini.md).

L'idea utile della Strategia A sopravvive nel punto giusto: un modello
linguistico e' impiegato per l'**interpretazione del testo**, dove serve
capacita' semantica, non per la geometria dell'immagine, dove serve precisione
sui pixel.
