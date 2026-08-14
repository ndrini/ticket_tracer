# Dal testo OCR ai dati strutturati

Come si passa dal testo grezzo prodotto dall'OCR ai dati che finiranno nel
database: prodotti, prezzi, totale.

Documento precedente: [30_estrazione_singole_immagini.md](30_estrazione_singole_immagini.md),
che spiega come si arriva dai singoli scontrini al testo OCR.

---

## 1. Il problema in una frase

**L'OCR non dice quali prodotti ci sono.** Restituisce frammenti di testo con
delle coordinate, e nient'altro.

Questo e' cio' che arriva davvero, per uno scontrino di benzina:

```
27.93 €
1.785 €
18.93
de 0,20 euros por litro,
```

Guardando `27.93` non si puo' sapere se sia un prodotto, una base imponibile o
il totale. L'informazione c'e' sulla carta — l'etichetta era stampata a
sinistra, sulla stessa riga — ma l'OCR l'ha separata.

---

## 2. Le quattro fasi

```
 testo OCR ──▶ [1] RICOMPORRE ──▶ [2] RIDURRE ──▶ [3] CHIEDERE ──▶ [4] VERIFICARE
   frammenti     righe come         via il         all'LLM          il totale
   sparsi        sulla carta        superfluo      testuale         stampato
```

| # | modulo | cosa fa |
|---|--------|---------|
| 1 | [`righe_logiche.py`](../app/etl/righe_logiche.py) | rimette insieme i frammenti della stessa riga |
| 2 | [`riduci_testo.py`](../app/etl/riduci_testo.py) | toglie regolamenti, dati carta, intestazioni |
| 3 | *(da scrivere)* | interroga il modello linguistico |
| 4 | [`verifica.py`](../app/etl/verifica.py) + [`totale.py`](../app/etl/totale.py) + [`plausibilita.py`](../app/etl/plausibilita.py) | controlla che i conti tornino |

### Provare i moduli

```bash
# le righe di uno scontrino, come sono stampate
uv run python -c "
import json,glob
from app.etl.righe_logiche import testo_ricomposto
d=json.load(open(sorted(glob.glob('data/estratti/*.json'))[0]))
print(testo_ricomposto(d['righe_ocr']))"

# tutti i test dei moduli descritti qui
uv run pytest tests/unit/test_righe_logiche.py tests/unit/test_totale.py \
              tests/unit/test_verifica.py tests/unit/test_plausibilita.py -q
```

---

## 3. Fase 1 — Ricomporre le righe

I frammenti che stanno alla stessa altezza appartengono alla stessa riga
stampata. Rimettendoli insieme, lo scontrino di prima diventa leggibile:

```
1 MONGETA PLANA IK CO 1,50
Total factura: 10,18
Efectiu 50,20
Canvi 40,02
```

Ora ogni riga contiene quantita', nome e prezzo **insieme**, e le righe di
contesto (`Efectiu` = contante consegnato) dicono cosa NON e' il totale.

**Effetto misurato:** con le righe ricomposte il modello ha restituito il totale
corretto (10,18) su uno scontrino dove il parser geometrico prendeva 50,20,
cioe' il contante.

### L'inclinazione delle foto

Gli scontrini sono fotografati storti, da 1,4 a 6,4 gradi. Su uno largo 400 px,
6 gradi fanno **oltre 40 px di dislivello** fra il primo e l'ultimo frammento —
molto piu' dell'altezza di una riga. Senza tenerne conto, la riga si spezza.

La pendenza si legge dai riquadri che l'OCR disegna attorno al testo, perche'
seguono gia' il testo stesso.

> **Strada chiusa.** La prima versione stimava la pendenza accoppiando
> frammenti vicini in altezza e distanti in orizzontale. Sbagliata: accoppiava
> anche frammenti di righe diverse, con uno scarto medio di **3,6 gradi** e casi
> oltre i 9. Applicata, *peggiorava* il risultato (66% contro il 72% che si
> otteneva ignorando l'inclinazione del tutto).

### Perche' la tolleranza e' bassa

Quanto due frammenti possono distare in altezza restando "sulla stessa riga"?
Aumentando quel margine, il punteggio migliora sempre:

| tolleranza | 0.8 | 1.0 | 1.4 | 2.0 | 2.5 |
|---|---|---|---|---|---|
| "successo" | 73% | 76% | 77% | 79% | **80%** |
| righe totali | 4280 | 2710 | 1804 | 789 | **618** |
| righe con 3+ importi | 16% | 21% | 31% | 45% | **53%** |

**Ed e' un miraggio.** Le righe fisiche vengono fuse fra loro (da 4280 a 618) e
l'etichetta finisce accanto a un numero qualsiasi. Il punteggio sale proprio
perche' la ricomposizione ha smesso di funzionare.

La tolleranza resta a 0.8, dove le righe restano distinte.

**Risultato: 73%** degli scontrini ha etichetta e importo del totale sulla
stessa riga.

### Quando non funziona

Su scontrini con layout a piu' colonne (una fattura di benzina, un modulo con
campi affiancati) righe diverse finiscono comunque fuse:

```
Precio: Producto: Cantidad: Descuento: Numero Alb: Sense Plon 18.93 1.785 €
```

Misurato su 4835 righe ricomposte: **4,3%** contiene tre o piu' etichette,
segno di fusione, e l'8,3% supera i 100 caratteri (la mediana e' 25). E' un
difetto residuo noto, non un caso limite teorico — ma riguarda soprattutto
documenti che non sono scontrini di spesa.

---

## 4. Fase 2 — Ridurre il testo

Su un computer senza scheda grafica, il costo dominante **non e' scrivere la
risposta ma leggere la domanda**:

| | quantita' | tempo | velocita' |
|---|---|---|---|
| **lettura del prompt** | 400 token | **40,7 s** | 9,8 token/s |
| generazione risposta | 200 token | 30,7 s | 6,5 token/s |

Il **57% del tempo** se ne va prima che il modello scriva un carattere. Ridurre
l'input e' quindi piu' efficace che ridurre l'output: su un caso reale, da 50 a
14 righe porta il tempo da 55 a 33 secondi.

Cosa si butta: regolamenti (uno scontrino di camping aveva **20 righe** di
*"REGLAMENTO DE RÉGIMEN INTERNO"*, piu' della meta' del documento), dati di
pagamento, indirizzi, ringraziamenti.

**Il filtro e' deliberatamente prudente**, perche' gli errori non si equivalgono:
perdere una riga di prodotto costa un dato, tenerne una inutile costa qualche
decimo di secondo. Verificato su 84 scontrini che quadrano: **zero importi
persi**. Il prezzo della prudenza e' che riduce il 28% del testo, non il 71% del
caso migliore.

Righe come `Efectiu 50,20` **restano**: servono a capire che 50,20 non e' il
totale ma il contante.

---

## 5. Fase 3 — Chiedere all'LLM

Non ancora scritta. Le scelte gia' misurate:

**Quale modello.** Un modello *testuale* (llama3.1, qwen2.5-instruct), non
multimodale. Il multimodale serviva a sostituire OCR e segmentazione, che pero'
funzionano gia'.

**Dove.** In locale, non su Kaggle. Il problema non sono le ore di calcolo, che
si lanciano di notte, ma il ciclo di sviluppo: ogni correzione al prompt
richiederebbe caricare, eseguire, scaricare, ricongiungere.

**Quante domande.** Piu' domande brevi, non una sola grande. Misurato su tre
scontrini: due chiamate brevi costano **208 s** contro **267 s** di una singola,
il 22% in meno. Sembra controintuitivo, perche' due chiamate pagano due volte la
lettura del prompt, ma la richiesta unica genera molti piu' token e a volte
diverge (153 s su un caso).

**Perche' non bastano le regole.** Un parser puramente geometrico quadra sul 27%
degli scontrini, che sale al 42% su quelli senza sconti. Cio' che manca e'
semantico: che uno sconto vada sottratto, che un subtotale non sia un prodotto,
che una promozione 3x2 cambi il conto. Nessun aggiustamento di coordinate lo
ricava.

---

## 6. Fase 4 — Verificare

### Il totale come giudice

Ogni scontrino stampa il proprio totale. Confrontarlo con la somma delle righe
e' l'unico controllo **indipendente** disponibile, e non costa nulla perche' il
dato e' gia' sulla carta.

Trasforma una domanda vaga ("funziona bene?") in un numero: quanti scontrini
quadrano al centesimo.

Trovare il totale ha richiesto tre correzioni, ognuna scoperta da una firma nei
dati:

| difetto | come si e' manifestato |
|---|---|
| prendevo l'ultima etichetta in basso | sotto il totale c'e' la tabella IVA, che finisce con `TOTAL 0,51` — una quota d'imposta. Ora si prende l'importo **piu' grande** |
| sommavo le quote IVA | la loro colonna (x=388) e' vicina a quella dei prodotti (x=428) e veniva fusa. Ora il confine si applica **prima** di raggruppare |
| sommavo il totale stesso | l'etichetta `TOTAL` sta a y=816 ma il suo importo a y=813: il confine escludeva l'una e non l'altro |

La firma comune era l'asimmetria: **179 casi su 202** avevano somma *maggiore*
del totale, cosa che il rumore casuale non produce.

Effetto delle correzioni: da **23 a 84** scontrini validati, scarto mediano da
15,14 a **3,11**.

### I prezzi impossibili

Il totale dice *se* lo scontrino quadra, non *quale* riga e' sbagliata. Un
prezzo fuori scala indica dove guardare: uno yogurt non costa 15 euro ne' 5
centesimi, e un valore simile e' quasi sempre una virgola letta male.

Le soglie vengono da **615 prezzi** misurati su scontrini che quadrano al
centesimo, quindi da righe provatamente corrette:

| | |
|---|---|
| mediana | **2,00 €** |
| meta' dei prodotti | 1,42 – 2,95 € |
| 95% | sotto 6,48 € |
| oltre 30 € | 0,7% (IKEA, Decathlon, campeggio) |

Nei supermercati alimentari e' ancora piu' compatto: Mercadona non supera 5,48 €
su 71 prezzi, Consum 5,82 € su 50.

**Il controllo discrimina**, ed e' la verifica che conta:

- falsi allarmi su scontrini corretti: 6 su 615 (**1,0%**)
- segnalazioni su scontrini che non quadrano: 43 su 1094 (**3,9%**)

Scatta quasi quattro volte piu' spesso dove sappiamo che c'e' un errore.

I valori **negativi non vengono segnalati**: sono resi e sconti legittimi (il
piu' grande e' −29,88 €, un reso IKEA).

---

## 7. Stato e limiti

| | | |
|---|---|---|
| scontrini estratti | **317** | da 95 foto, dopo la pulizia |
| leggibili (confidenza ≥ 0.6) | 314 | 99% degli estratti |
| con totale individuabile | 242 | 77% dei leggibili |
| che quadrano con le sole regole | 84 | 27% dei leggibili |

Gli estratti erano 373 prima di rimuovere i 57 ritagli prodotti quando 13 foto
uscivano capovolte: quelli restavano su disco accanto alle versioni corrette,
perche' l'identita' di uno scontrino e' l'hash del suo ritaglio e un'immagine
ruotata e' un file diverso.

**Il 27% e' il limite delle regole geometriche, non un difetto da correggere.**
Dei 110 scontrini che falliscono pur non avendo sconti, 95 sbagliano di oltre
2 euro: sono errori strutturali, non refusi. Somma 182,75 contro totale 43,81
significa che vengono raccolti blocchi interi che non sono prodotti.

Cio' che manca e' semantico, ed e' esattamente il lavoro della Fase 3.

---

## 8. Il metodo, che vale piu' dei numeri

Ogni scelta di questo documento e' nata da una misura, e diverse ipotesi
ragionevoli sono state **smentite dai dati**:

- il collo di bottiglia sembrava la generazione della risposta: era la lettura
  del prompt (57%)
- raggruppare gli scontrini in un solo prompt sembrava conveniente: non cambia
  nulla su CPU (59,8 s contro 60,1 s)
- correggere l'inclinazione sembrava ovviamente utile: con una stima sbagliata
  peggiorava (66% contro 72%)
- una tolleranza piu' larga sembrava migliorare tutto: fondeva le righe

**Una metrica che sale non basta: va guardato cosa sta rompendo.** E' l'errore
commesso all'inizio del progetto, quando si contavano gli scontrini senza
guardare i ritagli, e due foto risultavano "corrette" mentre una aveva un box
grande quanto l'intera fotografia.
