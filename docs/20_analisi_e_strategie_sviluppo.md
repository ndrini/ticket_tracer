# Strategia complessiva - Ticket Tracer

Dalle fotografie storiche degli scontrini ai report di spesa per **mese**, **anno**
e **tipologia** di prodotto.

Questo e' il documento di indirizzo dell'intero progetto. Il dettaglio della
sola segmentazione (foto con piu' scontrini -> ritagli singoli) sta in
[30_estrazione_singole_immagini.md](30_estrazione_singole_immagini.md); quello
dal testo OCR ai dati strutturati in
[40_dal_testo_ai_dati.md](40_dal_testo_ai_dati.md).

---

## 0. Come si lavora su questo progetto

Questa sezione viene prima delle altre perche' vale per tutte, e perche' e'
costata piu' errori di qualunque scelta tecnica.

> **Si agisce su piani espliciti, fondati sui dati, recuperabili da qualsiasi
> agente, chiari e criticabili.**

### Il ciclo

| passo | | |
|---|---|---|
| 1 | **Misura** | prima di diagnosticare. L'ipotesi istintiva e' spesso sbagliata |
| 2 | **Scrivi il piano** | esplicito, con le alternative scartate e il perche' |
| 3 | **Sottoponilo** | agli altri agenti, coi dati veri e non con un riassunto |
| 4 | **Consenso?** | si': implementa |
| 5 | | no: riformula la domanda coi dati mancanti, **oppure chiedi all'utente** |
| 6 | **Verifica** | sui dati, anche cio' su cui gli agenti concordano |
| 7 | **Documenta** | accanto alla costante nel codice, e nel documento della fase |

Il punto 5 e' il piu' importante: **senza consenso non si decide da soli**. Il
punto 6 lo bilancia: il consenso non e' una prova. Gli agenti si sono gia'
sbagliati su questo progetto, e a correggerli e' stata una misura, non
un'altra opinione.

### Quando serve il consenso, e quando no

Consultare tre agenti per ogni scelta e' insostenibile, e il metodo perderebbe
credibilita' proprio per eccesso di zelo. La soglia:

| serve il consenso | basta la misura e i test |
|---|---|
| decisioni **irreversibili** o che toccano la **semantica dei dati** | decisioni **locali e reversibili** |
| schema del database, tassonomia delle categorie | una regex, una soglia, un refactoring |
| regole di fusione o esclusione di record | un cambiamento coperto dai test |
| cambi di strategia di una fase | correzioni di difetti evidenti |

Il criterio non e' la difficolta' tecnica ma il **danno di un errore non
scoperto**: quanto costa accorgersene tardi.

### Come si esce dal disaccordo (evitare la paralisi)

Il disaccordo fra agenti puo' essere **strutturale**, non un segnale di errore:
aspettare una convergenza che non arrivera' e' immobilismo. Quindi:

1. **Si riformula**, aggiungendo i dati che mancavano — al massimo **due volte**.
   Una sola sarebbe troppo poco: il disaccordo spesso nasce da assunzioni
   implicite che emergono solo al secondo giro, e portare all'utente un bivio
   acerbo lo costringe a decidere su opzioni non ancora chiare.
2. **Il criterio d'uscita non e' il numero di giri ma il progresso**: se una
   riformulazione non sposta le posizioni ne' porta un argomento nuovo, la
   successiva non lo fara'. Si passa al punto 3 anche prima delle due.
3. Se il disaccordo resta, si **dichiara di che tipo e'** — dato mancante,
   definizione ambigua, compromesso di costo, conflitto fra metriche — e si
   porta all'utente come **bivio secco** (A contro B, con i numeri), non come
   riassunto della discussione.

Non si decide mai in silenzio, ma non ci si blocca nemmeno.

**Un agente che non risponde non blocca il lavoro.** Se uno dei tre va in
timeout ripetutamente, si procede col parere degli altri **dichiarandolo**: il
consenso registrato dice sempre chi ha risposto e chi no.

### La metrica si dichiara PRIMA di misurare

Le regole (a) e (b) piu' avanti dicono che nessuna metrica basta da sola. Preso
alla lettera questo giustificherebbe qualunque scelta a posteriori: se il numero
sale lo si accetta, se scende si racconta che stava sistemando altro. E' una
scappatoia reale, ed e' gia' stata usata su questo progetto — sul filtro della
coda la metrica e' stata cambiata **dopo** aver visto che la prima non premiava.

Il rimedio e' scrivere **prima** del test:

- la **metrica principale**, quella che deve migliorare;
- le **metriche di guardia**, che non devono peggiorare, e di quanto al massimo;
- cosa conta come **fallimento**.

Se il risultato viola quanto dichiarato, l'ipotesi e' respinta, senza racconti.
Se dopo il test si scopre che la metrica scelta era quella sbagliata, si puo'
cambiarla — ma **dicendolo**, e rieseguendo il confronto con la nuova metrica
dichiarata in anticipo per entrambe le versioni. Cambiare metro e' lecito;
cambiarlo di nascosto no.

### Quattro regole imparate sbagliando

**Una metrica che sale non basta ad assolvere.** Va guardato cosa sta rompendo.
Alzando la tolleranza di ricomposizione a 2,5 il punteggio saliva all'80%,
mentre le righe si fondevano da 4280 a 618.

**Una metrica che non sale non basta a bocciare.** Va guardato cosa sta
sistemando. Il filtro sulla coda sembrava inutile (16 scontrini quadrati prima,
15 dopo), ma due dei tre casi "rotti" quadravano solo perche' una riga di resto
pareggiava il conto per caso.

**Meglio un buco dichiarato che un numero inventato.** Un dato marcato come
dubbio resta verificabile; uno corretto d'ufficio in silenzio no.

**Segnalare, non correggere d'ufficio.** I controlli che non sono certi
producono un avviso, non una modifica.

### Un buco dichiarato va poi chiuso

Marcare un dato come dubbio non e' il punto d'arrivo: senza un seguito, il
database resta incompleto a tempo indeterminato e la marcatura diventa un alibi.
Ogni stato di dubbio deve avere una via d'uscita dichiarata:

| stato | come si chiude |
|---|---|
| `SOMMA_IN_ECCESSO` | migliorando il filtro sulla coda; il verso dice dove guardare |
| `SOMMA_IN_DIFETTO` | recuperando le righe perse, o rileggendo il ritaglio |
| `TOTALE_ASSENTE` | correzione manuale sul ritaglio, che e' conservato |
| `righe_sospette` non vuoto | revisione umana, in blocco sul catalogo |

I report devono poter dire **quanta spesa e' verificata e quanta indicativa**:
e' questa distinzione a rendere accettabile il caricamento dei dati imperfetti.

### Le prove vanno conservate

Una misura senza il suo contesto non e' ripetibile, e un mese dopo nessuno sa se
i numeri citati valgano ancora. Di ogni confronto si conserva: **su quali dati**
e' stato fatto (quanti scontrini, quali), **con quale codice** (il commit) e
**quali numeri** ha prodotto. I documenti di fase citano i numeri col loro
campione ("misurato su 94 scontrini"), mai da soli.

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
- **Ingestione idempotente (Fase A).** 317 scontrini estratti dalle 96 foto,
  ognuno identificato dall'hash del proprio ritaglio. Rilanciare e' sicuro:
  cio' che esiste viene saltato. Le foto duplicate arrivate da fonti diverse
  (backup, WhatsApp) sono riconosciute con un hash percettivo.
- **Verifica sul totale (Fase B).** Ogni scontrino dichiara il proprio totale,
  e la somma delle righe viene confrontata con quel numero. Vedi
  [40_dal_testo_ai_dati.md](40_dal_testo_ai_dati.md).
- **Controllo di verosimiglianza dei prezzi.** Le soglie vengono da 615 prezzi
  misurati su scontrini che quadrano al centesimo.
- **Separazione fra corpo e coda dello scontrino.** Il totale e' localizzato per
  coordinate, e la sua altezza sulla pagina fa da confine: sotto di esso non ci
  sono prodotti. Misurato su 94 scontrini: righe spurie da 77 a 0, scontrini con
  somma gonfiata da 47/95 a 8/94. Dettaglio nel documento 40, sezione 5-bis.
- **Caricamento idempotente nel database (Fase D).** `receipts.image_sha256` e'
  UNIQUE: rilanciare non duplica nulla, e aggiungere foto nuove carica solo le
  novita'.

### Esiste ma e' grezzo
- **OCR**: PaddleOCR con `lang="es"`. 314 scontrini su 317 leggibili.
- **Estrazione dati (Fase C)**: LLM testuale locale (`qwen2.5:3b-instruct`)
  interrogato con domande brevi separate. Funziona, ma la resa e' ancora
  modesta: circa un terzo degli scontrini quadra col totale stampato.
- **Database** SQLite: `commerce_type`, `commerces`, `products`, `receipts`,
  `receipt_lines`. Ha ora i campi di verifica (`total_declared`,
  `total_computed`, `validation_status`) e `products.category`, ancora da
  popolare.
- **Statistiche**: tre query fisse (totale per commercio, totale per prodotto,
  trend mensile). Nessun report, nessuna tipologia.

### Le lacune che bloccano l'obiettivo

Restano aperte:

1. **Nessuna categoria e' stata assegnata.** La colonna `products.category`
   esiste ma e' vuota, e senza di essa il report per tipologia — un requisito
   esplicito — non e' calcolabile. Si popola nella Fase F.
2. **Nessuna omogeneizzazione dei nomi.** Lo stesso pane compare come
   `PA DE PAGES`, `BARRA DE PA 3 U`, `PANET 11 UN`. Il campo `aka` esiste ma
   nessuna logica lo popola. E' la Fase E, e va prima della F: categorizzare
   nomi non ancora fusi significa rispondere piu' volte alla stessa domanda.
3. **La resa dell'estrazione e' ancora bassa.** Circa un terzo degli scontrini
   quadra col totale stampato. Gli altri entrano comunque nel database, marcati:
   `SOMMA_IN_ECCESSO` (righe di troppo) o `SOMMA_IN_DIFETTO` (righe perse). I
   due nomi distinti servono a sapere quale difetto aggredire, perche' sono
   problemi diversi con cause diverse.

Risolte dopo la prima stesura di questo documento:

- ~~Nessuna idempotenza~~ → hash del ritaglio piu' hash percettivo della foto.
- ~~Nessuna verifica di qualita'~~ → il totale stampato e' ora il giudice della
  pipeline, e i prezzi implausibili vengono segnalati.
- ~~La categoria non esiste nello schema~~ → `products.category` esiste; resta da
  popolare sul catalogo dei prodotti distinti.
- ~~Il database non contiene dati reali~~ → la Fase D carica gli scontrini
  estratti, col proprio giudizio di validita' accanto.
- ~~Le righe di pagamento gonfiano le somme~~ → il confine geometrico taglia la
  coda prima ancora di interrogare il modello.

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

**Le lettere corrispondono agli script**, cosi' il piano e il codice si leggono
insieme:

| fase | script | stato |
|---|---|---|
| A — ingestione (foto → testo OCR) | `scripts/fase_a_ingestione.py` | fatta |
| B — verifica sul totale | `app/etl/verifica.py`, `app/etl/coda.py` | fatta |
| C — estrazione dei dati (testo → campi) | `scripts/fase_c_estrazione.py` | fatta, resa da migliorare |
| D — caricamento nel database | `scripts/fase_d_carica_db.py` | fatta |
| E — catalogo e omogeneizzazione dei nomi | — | **da fare** |
| F — categorizzazione | — | **da fare** |
| G — report | — | **da fare** |

### Fase A — Ingestione idempotente (livelli 1-2)
1. Per ogni foto: orienta, segmenta, ritaglia.
2. Calcola l'**hash SHA-256 di ogni ritaglio**: e' l'identita' dello scontrino.
3. OCR, salvando testo e coordinate in `data/estratti/<hash>.json`.
4. Un ritaglio gia' presente viene saltato. Rilanciare la pipeline diventa
   sicuro e incrementale.

**Perche' prima di tutto:** produce il primo dato reale su cui misurare il vero
tasso di errore su 288 scontrini, invece di stimarlo.

### Fase B — Verifica automatica (il totale come giudice)
Ogni scontrino dichiara il proprio totale. Confrontarlo con la somma delle
righe estratte e' il controllo di qualita' piu' forte disponibile, e **non
costa nulla**: il dato c'e' gia'.

```
delta = somma(righe) - totale_dichiarato
```

**Il segno del delta conta quanto il suo valore**, e distinguerlo e' servito a
correggere una diagnosi sbagliata:

| stato | significato | difetto da aggredire |
|---|---|---|
| `VALIDO` | delta entro tolleranza | — |
| `SOMMA_IN_ECCESSO` | righe di **troppo** | coda sfuggita al filtro |
| `SOMMA_IN_DIFETTO` | righe **perse** | estrazione incompleta |
| `TOTALE_ASSENTE` / `PRODOTTI_ASSENTI` | manca un termine del confronto | lettura fallita |

Gli scontrini non validi **vengono caricati comunque ma marcati**, cosi' i
report possono escluderli e si sa sempre quanta parte del totale e' affidabile.

Questo trasforma una domanda vaga ("funziona bene?") in un numero.

### Fase C — Estrazione dei dati (testo → campi)

Un LLM **testuale** locale legge il testo OCR e restituisce negozio, data,
totale e prodotti. Tre scelte gia' misurate:

- **Domande brevi separate**, non un unico JSON: 208 s contro 267 s, e il
  modello da 3B azzeccava il totale su 1 scontrino su 4 con la richiesta unica.
- **Il totale non si chiede al modello** ma si legge per coordinate: sa *dove*
  guardare invece di indovinare.
- **La coda si taglia prima di chiedere.** Il modello ricopia diligentemente
  anche "EFECTIVO 50,00", e ogni riga di troppo gonfia la somma.

Dettaglio in [40_dal_testo_ai_dati.md](40_dal_testo_ai_dati.md).

### Fase D — Caricamento nel database

`receipts.image_sha256` e' UNIQUE: uno scontrino gia' caricato viene
riconosciuto e saltato. Aggiungere foto nuove carica solo le novita'.

### Fase E — Catalogo prodotti e omogeneizzazione (livello 3)
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

### Fase F — Categorizzazione (livello 4)
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

### Fase G — Report (livello 5)
Aggregazioni per mese, anno e categoria, con l'indicazione della **quota di
spesa proveniente da scontrini validi**: un totale senza quel dato non e'
interpretabile.

---

## 5. Stato dello schema del database

**Gia' applicato.**

In `receipts`: `image_sha256 TEXT UNIQUE` (idempotenza), `total_declared`,
`total_computed`, `validation_status`, `validation_delta`, `foto_origine`.
In `products`: `category TEXT`.

**Ancora aperto.**

- Il campo `aka` andrebbe sostituito da una **tabella di alias** vera:
  `product_aliases(raw_text, product_id, lingua)`. Un campo lista non
  interrogabile non risolve nulla. Serve alla Fase E.
- In `receipt_lines`, `quantity` e `unit` restano vuoti: l'estrazione non li
  ricava ancora, scrive quantita' 1 e il prezzo di riga. Sulle righe con
  quantita' ("2 AMANIDA 0,86 1,72") il totale di riga e' comunque corretto,
  quindi le somme tornano; si perde il dettaglio, non l'importo.

---

## 6. Sequenza operativa

Fatto:

1. ~~Segmentazione integrata in `app/`~~ — `app/etl/segmenter.py`.
2. ~~**Fase A**~~ — 317 scontrini in `data/estratti/`, con testo e coordinate.
3. ~~**Fase B**~~ — verifica sui totali, con il verso dello scarto distinto.
4. ~~**Fase C**~~ — estrazione con l'LLM testuale, coda tagliata a monte.
5. ~~**Migrazione dello schema**~~ — campi di verifica e `category`.
6. ~~**Fase D**~~ — caricamento idempotente nel database.

Da fare:

7. **Migliorare la resa dell'estrazione.** Circa un terzo quadra. Il verso dello
   scarto dice dove intervenire: `SOMMA_IN_ECCESSO` e `SOMMA_IN_DIFETTO` sono
   difetti diversi, e vanno contati prima di scegliere quale aggredire.
8. **Fase E** — catalogo prodotti + revisione manuale.
9. **Fase F** — categorizzazione + revisione manuale.
10. **Fase G** — report per mese, anno, categoria.

### Una correzione alla strategia originale

Il documento prevedeva di caricare nel database **solo dopo** normalizzazione e
categorizzazione. Nella pratica il caricamento e' stato anticipato, e la ragione
regge: `image_sha256 UNIQUE` rende il caricamento **idempotente e ripetibile**,
quindi il database non e' piu' un punto di non ritorno. Rilanciare non duplica;
correggere significa cancellare il file e ricaricare.

Resta valido il principio che lo motivava: **il lavoro sporco resta su file
rifacibili**. La scelta si e' gia' ripagata due volte — i 317 scontrini sono
stati rielaborati per le foto capovolte, per i ritagli sbagliati e infine per il
filtro sulla coda, ogni volta cancellando file e rilanciando. In tabelle
relazionali sarebbero serviti UPDATE incrociati.

La scelta si e' gia' ripagata: i 317 scontrini sono stati rielaborati piu'
volte — per correggere le foto capovolte, per ripulire i ritagli sbagliati —
cancellando file e rilanciando. In un database sarebbero serviti UPDATE
incrociati su tabelle collegate.

---

## 7. Rischi noti

| rischio | mitigazione |
|---|---|
| L'LLM locale sbaglia l'estrazione su scontrini rovinati | La verifica sui totali (Fase B) li identifica invece di nasconderli |
| La traduzione catalano/spagnolo -> italiano introduce errori | Revisione umana del catalogo, che e' piccolo |
| I prodotti non alimentari (IKEA, Decathlon) inquinano le statistiche alimentari | Categorie 8-9 dedicate, separabili nei report |
| Scontrini illeggibili o parziali | Stati `TOTALE_ASSENTE` / `PRODOTTI_ASSENTI`: contati, non ignorati |
| Un filtro troppo aggressivo scarta prodotti veri | Il verso dello scarto lo rivela: `SOMMA_IN_DIFETTO` significa righe perse |
| Correggere d'ufficio un dato che non quadra | Vietato: si segnala (`righe_sospette`) e si lascia il record verificabile |
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

---

## 9. Registro delle decisioni condivise

Ogni decisione presa col metodo della sezione 0 lascia una riga qui: chi e'
stato consultato, cosa ha detto, cosa si e' deciso e su quali dati. Serve a
rendere le scelte **recuperabili**: senza questo, un mese dopo nessuno sa se un
numero citato valga ancora, ne' perche' una strada e' stata scartata.

### 2026-08-15 — Separazione fra corpo e coda dello scontrino

**Problema.** Su 30 scontrini solo 6 quadravano. Diagnosi iniziale sbagliata
("il modello perde righe"): la misura mostrava 21 casi su 25 con la somma
*maggiore* del totale, cioe' righe di troppo.

**Consultati.** Gemini, Vibe, Perplexity, con i dati veri e i quattro rimedi
possibili (fuzzy matching, geometria, subset-sum, filtro sull'importo).

**Consenso.** Tutti e tre: geometria come filtro principale, somiglianza come
supporto. Il **subset-sum e' stato scartato**: proposto da Perplexity e messo da
Vibe fra i residui, bocciato da Gemini come "pessimo" e infine **ritirato da
Vibe** ("troppo creativo per dati fiscali") una volta sottoposta l'obiezione.

**Corretto dopo il consenso, misurando.** Il confronto sull'importo doveva
essere stretto (`>`), non `>=` come proposto: su uno scontrino di un solo
prodotto il prodotto *e'* il totale. Con `>=` si risolveva 1 caso e se ne
rompevano 2; con `>` se ne risolvono 2 e nessuno si rompe. Le soglie suggerite
da Vibe (`> totale * 1.1`) non servivano.

**Esito.** Su 94 scontrini: righe spurie da 77 a 0, scontrini con somma gonfiata
da 47/95 a 8/94. Commit `780ba0e`.

### 2026-08-15 — Il metodo di lavoro stesso (sezione 0)

**Consultati.** Gemini e Perplexity hanno risposto; **Vibe e' andato in timeout
due volte** sulla domanda lunga e ha risposto solo alla versione breve.

**Consenso su tre difetti**, tutti accolti:

| difetto | rimedio |
|---|---|
| paralisi da non-consenso | riformulare, poi bivio A/B all'utente |
| costo di tre agenti per ogni scelta | soglia: solo decisioni irreversibili o semantiche |
| auto-giustificazione a posteriori | metrica dichiarata **prima** del test |

**Obiezione di Vibe, accolta.** Una sola riformulazione e' troppo rigida:
il disaccordo nasce spesso da assunzioni implicite che emergono al secondo giro.
Portate a due, con criterio d'uscita sul **progresso** e non sul conteggio —
altrimenti il rimedio alla paralisi diventa esso stesso ping-pong infinito.

**Approvazione finale.** Il testo di questa sezione 0 — non un riassunto — e'
stato risottoposto a Vibe, che ha risposto "APPROVO senza riserve",
confermando che la resa della sua obiezione era fedele e non annacquata dal
criterio del progresso. Unica nota sua, registrata: il criterio del progresso
puo' essere ambiguo nei casi limite, ma la formula "non sposta le posizioni ne'
porta un argomento nuovo" e' abbastanza operativa. Consenso a tre.

**Aggiunte da Gemini non ancora applicate**, da valutare quando serviranno:
misurare il **costo** di una modifica (un +1% di accuratezza che raddoppia il
tempo e' un fallimento non rilevato) e un **confronto differenziale** sui JSON
prima/dopo ogni modifica.

### 2026-08-15 — Lettura della data dallo scontrino

**Problema.** Il 66% degli scontrini risultava senza data pur avendola
stampata, e senza data il report per mese — un obiettivo esplicito — non e'
calcolabile. Alcune date erano inoltre impossibili (2004, 2020) su fotografie
del 2025.

**Metrica dichiarata prima del test.** Principale: scontrini con data valida,
da 34% a oltre l'85%. Guardie: zero date fuori dal 2015-2026, gli scontrini
`VALIDO` non devono calare, la somma dei totali non deve cambiare.

**Tre difetti sovrapposti**, trovati misurando e non ipotizzando:

1. la data e' stampata **in coda**, sotto il totale, e il filtro che toglie la
   coda la portava via con se';
2. ammettere lo spazio come separatore (necessario, l'OCR perde le barre)
   creava date **a cavallo di due righe**: "0,56" + "20/05/2025" diventava
   56/20/05;
3. vinceva la **prima** data trovata: il codice "03/03/04" batteva la data vera
   "06/06/2025".

**Consultati.** Gemini e Perplexity. **Vibe non ha risposto** — timeout su
entrambe le versioni della domanda, lunga e breve.

**Disaccordo, risolto misurando.** Sullo spazio come separatore Gemini lo
definiva "una bomba a orologeria", Perplexity lo dava per sicuro. La misura ha
mostrato che avevano ragione entrambi in parte: `IVA 21 04 2026` produceva una
data falsa (Gemini), ma i telefoni venivano gia' scartati dalla validazione
(Perplexity). Il rimedio proposto da Gemini — legare lo spazio a una parola
chiave — **non reggeva sui dati**: copriva 2 righe su 18. Nelle altre 16 la
maggioranza erano numeri di telefono, e il segnale utile era un altro: lo
spazio vale **solo con l'anno a quattro cifre**, perche' un telefono non
contiene un gruppo di quattro cifre che valga come anno.

**Esito.** 197/218 con data (90%), zero fuori intervallo, `VALIDO` fermo a 61,
somma invariata. Il primo tentativo dava 35%: fallimento secondo la metrica
dichiarata, ed e' stato quel fallimento a rivelare il difetto 2. Senza una
soglia scritta prima, il 35% sarebbe sembrato un miglioramento.

**Non applicato**, in attesa di misura: chiedere la data all'LLM per i 21
scontrini che restano senza (proposto da entrambi, con la cautela di accettarla
solo se cade nell'intervallo ammesso).
