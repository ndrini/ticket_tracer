# Da una foto con molti scontrini ai singoli scontrini

Questo documento spiega come il sistema passa da **una fotografia contenente
piu' scontrini** ai **ritagli singoli**, uno per scontrino, pronti per l'OCR.

E' il seguito operativo di [20_analisi_e_strategie_sviluppo.md](20_analisi_e_strategie_sviluppo.md),
che elencava il problema fra i punti deboli ("l'algoritmo basato su contorni
classici fatica a isolare gli scontrini") e proponeva due strategie. La
soluzione adottata non e' nessuna delle due, per una ragione documentata piu'
avanti: non ha richiesto ne' API a pagamento (Strategia A) ne' l'addestramento
di YOLO su un dataset etichettato (Strategia B).

Implementazione: [`scripts/segmenta_detector.py`](../scripts/segmenta_detector.py).
Il diario tecnico con tutte le strade chiuse e le misure che le hanno chiuse e'
in [`scripts/segmenta_detector.md`](../scripts/segmenta_detector.md).

---

## 1. Il problema, in una frase

Gli scontrini sono di carta termica chiara, appoggiati su tavoli chiari. Il
contrasto fra carta e sfondo e' quasi nullo: **Otsu e Canny trovano il bordo
del tavolo, non quello della carta.**

Su una foto con un solo scontrino, il contorno rilevato dall'algoritmo classico
misurava `minAreaRect` 1999x1504, cioe' l'intera immagine.

## 2. L'idea che risolve

> Cercare il bordo visibile della carta e' un problema mal posto.
> **Lo scontrino *e'* il cluster delle sue righe di testo.**

Il testo stampato e' l'unico segnale ad alto contrasto nella scena. Invece di
inseguire il bordo del foglio, si individuano le righe di testo e si prende come
ritaglio il loro inviluppo, con un piccolo margine.

## 3. La pipeline, passo per passo

### Passo 0 — Orientamento della foto

La foto viene ruotata al verso giusto (0/90/180/270 gradi) con il classificatore
`PP-LCNet_x1_0_doc_ori` di PaddleOCR, in `app/etl/etl_engine.py`.

Se l'immagine **non contiene testo** non viene ruotata affatto: non c'e'
orientamento da recuperare, e il classificatore su un fotogramma vuoto tira a
indovinare (un'immagine nera torna "270" con confidenza 0.26).

Costo: **~8.9 secondi** per foto. In precedenza questo stadio provava tutte e
quattro le rotazioni valutandole con un OCR completo, e costava **210 secondi**:
il riconoscimento del testo leggeva le parole solo per contare quante fossero
leggibili, cioe' faceva lavoro che veniva buttato.

### Passo 1 — Rilevamento delle righe di testo

Il detector pre-addestrato di PaddleOCR (`TextDetection`, **solo detection**,
niente riconoscimento) restituisce un poligono per ogni riga di testo.

Questo passo e' il vero motivo per cui il metodo funziona. Il precedente
approccio con `adaptiveThreshold` + componenti connesse **saldava** il testo di
scontrini adiacenti in un blocco unico: su una foto con 5 scontrini affiancati,
il primo componente misurava gia' 469x1500, cioe' tutta l'altezza del
fotogramma. Il detector invece lavora sui gradienti ad alta frequenza dei
caratteri e segmenta riga per riga, quindi **non fonde** gli scontrini vicini.

### Passo 2 — Taglio sulle colonne vuote

Si proietta l'intervallo orizzontale `[x_min, x_max]` di ogni riga sull'asse x e
si conta quante righe coprono ciascuna colonna. Le colonne **quasi vuote** sono
i separatori fra scontrini.

Sulla foto con 5 scontrini il profilo e':

```
..#######..########...#######...#######..#######..
  ^scont.1  ^scont.2   ^scont.3  ^scont.4 ^scont.5
```

386 righe rilevate, cinque gruppi separati da valli larghe 62-111 px, mentre
nessuno scontrino ne contiene una al proprio interno.

"Quasi vuote" e non "vuote": quando due scontrini si toccano, il varco
assottiglia la copertura senza mai azzerarla, e pretendere lo zero li fondeva.

### Passo 3 — Ritaglio

Per ogni gruppo di righe si prende il rettangolo che le contiene, con un margine
del 2%.

### Passo 4 — Scarto dei box annidati

Un box contenuto quasi per intero in uno piu' grande viene eliminato.

Si fonda su un **vincolo di dominio**: gli scontrini sono affiancati, mai
sovrapposti in modo consistente, quindi un box annidato non e' un secondo
scontrino ma un pezzo dello stesso. Il caso reale: su uno scontrino inclinato la
colonna fra descrizione e prezzo e' povera di testo, la proiezione la legge come
separatore e ritaglia una fetta con le sole cifre.

### Passo 5 — Recupero dei box sospetti

Se un box sembra contenere piu' scontrini, viene **raddrizzato e risegmentato
come se fosse una foto a se'**.

Serve perche' un testo inclinato di pochi gradi si spalma lateralmente nella
proiezione e riempie le valli fra fogli vicini. Raddrizzare l'**intera foto**
peggiora le cose (misurato: 4→3, 3→2, 4→2 gruppi), perche' la rotazione attorno
al centro fa scorrere lateralmente gli scontrini ai bordi. Raddrizzare il solo
ritaglio evita il problema: nient'altro nell'immagine si muove.

Un box e' sospetto per due segni indipendenti. Su trenta box misurati, l'unico
difettoso e' il solo a superarli, e nessuno dei due e' al limite:

| | altri box | il box fuso |
|---|---|---|
| larghezza / fotogramma | 0.15 – 0.37 | **0.56** |
| righe di testo | 10 – 95 | **206** |

La procedura e' **ricorsiva**: con scontrini accatastati ad angoli diversi ogni
passata libera una giuntura sola (la prima ha isolato il Mercadona lasciando
insieme i due Decathlon, ancora con 195 righe; la seconda li ha separati).
Massimo tre passate.

---

## 4. Due problemi risolti senza scrivere codice apposta

**I falsi positivi sul legno sono spariti.** Il vecchio approccio doveva
distinguere il testo stampato dalle venature del tavolo, e non ci riusciva: una
venatura ottenne un punteggio di "ritmo delle righe" di **1.016**, piu' alto di
uno scontrino vero a 0.57. Il detector semplicemente non rileva righe di testo
sul legno, quindi la regione non viene mai proposta.

**Il disegno a matita viene ignorato.** Su `2025-09-06 10.44.58` c'e' un disegno
accanto a una fattura manoscritta: viene ritagliata solo la fattura.

---

## 5. Come si misura la qualita' — IoU e mAP

Il conteggio degli scontrini ("ne ha trovati 5 su 5") e' una metrica **binaria e
ingannevole**. Due esempi reali, entrambi contati come successi:

- una foto contata **2/2 OK**, con due box che coprivano il 62% e il 55% del
  fotogramma e si sovrapponevano pesantemente;
- una foto contata **1/1 OK**, in cui l'unico box era **tutta l'immagine**: la
  segmentazione non aveva trovato lo scontrino, aveva restituito la foto intera.

Serve una metrica che misuri **quanto bene** il ritaglio si sovrappone allo
scontrino vero, non solo quanti ne sono stati contati.

### 5.1 IoU (Intersection over Union)

Misura la sovrapposizione fra il rettangolo predetto e quello vero
(*ground truth*, cioe' etichettato a mano):

```
        area dell'intersezione
IoU = ----------------------------
           area dell'unione
```

Vale **0** quando i due rettangoli non si toccano, **1** quando coincidono
esattamente.

```
   ┌───────────────┐
   │  vero         │
   │        ┌──────┼────────┐
   │        │▓▓▓▓▓▓│        │
   │        │▓▓▓▓▓▓│ predetto│
   └────────┼──────┘        │
            └───────────────┘

   ▓ = intersezione (numeratore)
   tutta l'area coperta = unione (denominatore)
```

E' la metrica che smaschera subito i due falsi successi: un box che copre
l'intero fotogramma quando lo scontrino ne occupa un quarto ottiene IoU ~0.25.

### 5.2 Da IoU alla decisione: vero positivo o no

Si fissa una **soglia** (tipicamente 0.5, o 0.7 se si vuole essere severi):

- un box predetto che copre uno scontrino vero con IoU ≥ soglia e' un
  **vero positivo** (TP);
- un box predetto che non corrisponde a nulla e' un **falso positivo** (FP),
  ad esempio una fetta di legno;
- uno scontrino vero che nessun box copre e' un **falso negativo** (FN), cioe'
  uno scontrino perso.

Da qui:

- **Precision** = TP / (TP + FP) — quanto e' pulito cio' che produco
- **Recall** = TP / (TP + FN) — quanto di cio' che esiste riesco a trovare
- **F1** = media armonica delle due

### 5.3 Che cos'e' l'mAP

**AP** (*Average Precision*) riassume in un numero solo l'andamento della
precision al variare del recall: si ordinano le predizioni dalla piu' sicura
alla meno sicura, si calcola la curva precision/recall e se ne prende l'area.
Premia chi trova molti scontrini veri **senza** produrre spazzatura.

**mAP** (*mean Average Precision*) e' la media dell'AP su piu' classi di
oggetti. E' lo standard nella *object detection* (COCO, Pascal VOC), dove le
classi sono decine: persona, auto, cane...

**Qui c'e' una sola classe, "scontrino".** Quindi la "m" di *mean* non aggiunge
nulla: mAP coinciderebbe con AP. Inoltre l'AP presuppone che ogni predizione
abbia un **punteggio di confidenza** con cui ordinarla, mentre questo algoritmo
e' geometrico e non ne produce uno.

**Per questo progetto conviene misurare:**

1. **IoU medio** sui box accoppiati — quanto sono precisi i ritagli
2. **Precision, Recall, F1** a IoU ≥ 0.5 — quanti scontrini trovo e quanta
   spazzatura produco
3. **Tasso di sotto-segmentazione** — quante volte un box copre due o piu'
   scontrini veri (l'errore piu' insidioso: perde dati senza sembrare un errore)
4. **Tasso di sovra-segmentazione** — quante volte uno scontrino vero e' spezzato
   in piu' box

L'mAP resterebbe utile se in futuro si aggiungessero classi (es. "scontrino",
"ricevuta carta di credito", "fattura manoscritta") o un modello che produce
punteggi di confidenza, come lo YOLO della Strategia B.

---

## 6. Risultati attuali

| | conteggi esatti |
|---|---|
| 6 foto di riferimento (usate durante lo sviluppo) | **6/6** |
| 10 foto mai viste, estratte a caso | **10/10** |

I ritagli sono stati verificati **a occhio** uno per uno: intestazione, righe
prodotto e totale sono presenti e leggibili.

Le soglie non sono tarate su un punto ottimo ma stanno al **centro di un
altopiano**: il 6/6 vale per `empty_frac` da 0.03 a 0.08 incrociato con valle
minima da 10 a 20 px, e quattro foto su sei sono corrette a *ogni* combinazione
provata. Un massimo isolato sarebbe stato il sospetto di overfitting; un
altopiano e' la firma di un criterio che regge.

---

## 7. Limiti noti

- **I box aderiscono al testo, non alla carta.** Con un margine del 2% resta
  escluso un bordo di carta bianca. Irrilevante per l'OCR, ma da sapere se
  servisse il foglio intero.
- **I ritagli ottenuti per rotazione sono piu' stretti** e perdono un margine
  laterale. Restano leggibili ma meno puliti.
- **Solo taglio verticale.** Gli scontrini sono sempre affiancati
  orizzontalmente nel materiale disponibile; scontrini impilati richiederebbero
  la stessa logica sull'asse y.
- **La metrica IoU non e' ancora implementata**: i ritagli sono finora giudicati
  a occhio. E' il prossimo passo (vedi sotto).
- **Sedici foto restano poche.** 16/16 e' un buon segnale, non una garanzia.

---

## 8. Prossimi passi

1. **Implementare la metrica IoU** della sezione 5: etichettare a mano i box
   veri e misurare IoU medio, precision/recall e i due tassi di errore. E'
   l'unica difesa contro il ripetersi dell'overfitting, e avrebbe smascherato
   subito i due falsi successi citati sopra.
2. **Integrare la segmentazione in `app/`**: oggi
   `scripts/segmenta_detector.py` e' ancora uno script sperimentale, fuori dalla
   pipeline ETL.
3. **Ritirare `scripts/segmenta_bottomup.py`** una volta completato il punto 2.
4. **Estrazione e omogeneizzazione dei dati** per il database: e' la fase
   successiva, da pianificare a parte.
