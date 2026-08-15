# Come siamo arrivati a 6/6

Diario tecnico della segmentazione degli scontrini. Documenta `segmenta_detector.py`
e, soprattutto, **perché** il predecessore `segmenta_bottomup.py` non poteva arrivarci.

Il valore di questo file non sta nella soluzione finale, che è breve, ma nelle
strade chiuse: sono costate settimane e la loro misura è l'unica cosa che
impedisce di riprovarle.

---

## Il problema

Foto di scontrini di carta termica su un tavolo di legno chiaro, da ritagliare
uno per scontrino. Il contrasto carta/tavolo è quasi nullo: Otsu e Canny
trovano il bordo del *tavolo*, non quello della carta. Su una foto con un solo
scontrino il contorno rilevato aveva `minAreaRect` 1999x1504, cioè l'intera
immagine.

Sei foto di riferimento con verità nota, da 1 a 5 scontrini ciascuna.

---

## Le quattro generazioni

| # | approccio | conteggi esatti | perché è caduto |
|---|-----------|-----------------|-----------------|
| 1 | soglia su saturazione HSV | — | la carta non è meno satura del legno chiaro |
| 2 | densità di testo + colore | — | stesso limite di fondo: cerca il *foglio* |
| 3 | bottom-up: testo → crescita → merge → filtro | **4/6** | plateau, vedi sotto |
| 4 | detector di righe + split su colonne vuote | **6/6** | — |

---

## Perché il bottom-up si è fermato a 4/6

La generazione 3 fu un vero progresso: partire dal **testo stampato** invece che
dal bordo carta portò da 2/6 a 4/6, perché il testo è l'unico segnale ad alto
contrasto nella scena. L'intuizione era giusta e sopravvive nella generazione 4.

A fermarla fu il **primo** stadio, non le tarature successive. Su `07.47.51`
(5 scontrini affiancati) il primo componente connesso misurava già:

```
469 x 1500  =  tutta l'altezza del fotogramma
```

`adaptiveThreshold` + morfologia salda il testo di due scontrini adiacenti in un
unico blob **prima** che qualunque stadio successivo possa distinguerli.
L'informazione è distrutta al livello zero: nessun filtro a valle la recupera.

### Il sintomo: la coperta corta

Quattro misure consecutive, in ordine cronologico:

| modifica | esatti | effetto |
|----------|--------|---------|
| baseline | 4/6 | — |
| + split dei blocchi larghi su valle di densità | **2/6** | rompe 2 foto e non risolve quella mirata |
| + filtro "ritmo delle righe" | 3/6 | risolve 10.33.47, rompe 21.12.47 |
| + ritmo solo sui box piccoli | 4/6 | risolve una foto, ne rompe un'altra |

Ogni intervento aggiustava una foto e ne rompeva un'altra: il segno che si stava
tarando sul rumore di sei campioni invece di risolvere il problema.

### La metrica che nascondeva i difetti

Il "conteggio esatto" è binario e maschera ritagli pessimi. Due successi falsi:

- `07.57.06`: contato **2/2 OK**, con box che coprivano il 62% e il 55% del
  fotogramma, ampiamente sovrapposti
- `21.12.47`: contato **1/1 OK**, con l'unico box uguale a **tutto** il
  fotogramma (1505x2000). La segmentazione non aveva trovato lo scontrino:
  aveva restituito la foto intera

---

## Test provati e ritirati dalla misura

Ognuno sembrava ragionevole a priori. La misura li ha chiusi: **non riproporli.**

| test | misura | esito |
|------|--------|-------|
| interruzioni ("runs") per riga | legno **29.3** vs scontrino vero **16.3** | nessuna informazione di classe: il legno si spezza più del testo |
| `rowstd` assoluto | scontrino 0.030 vs legno 0.037 | classi sovrapposte |
| `rowstd` normalizzato sulla densità | scontrino 0.309 **sotto** legno 0.465 | classi sovrapposte |
| split su valle di densità verticale | taglio corretto a x=361 (0.029 vs soglia 0.055) | **inutile per costruzione**: crescita e merge a valle lo ricuciono |
| luminosità p75 | carta 152-183 vs legno 122-130 | separa, ma dipende dall'illuminazione |

Il caso più istruttivo è `21.25.11`: una venatura del legno a strisce
orizzontali ottenne un "ritmo" di **1.016**, più alto di uno scontrino vero
(0.57). Nessuna soglia su quella famiglia di misure poteva separarli.

---

## Il cambio di paradigma

Consultati Gemini, Vibe e Perplexity. Le tre risposte convergevano su due punti,
entrambi confermati dai fatti raccolti:

1. **La metrica va cambiata** (il conteggio nasconde i ritagli pessimi).
2. **I due errori vanno separati in stadi diversi**: fusione di adiacenti è un
   problema di *partizionamento*, il legno è un problema di *classificazione*.
   Tentare di risolverli entrambi con `ink_ok` era la causa della coperta corta.

L'osservazione decisiva è di Gemini:

> Cercare il bordo visibile della carta è un problema mal posto.
> **Lo scontrino *è* il cluster delle sue righe di testo.**

Cioè: smettere di inseguire il bordo carta e prendere come ritaglio l'inviluppo
delle righe di testo, con un piccolo margine.

Scartata invece la proposta di addestrare un RandomForest su ~20 regioni
estratte dalle stesse 6 foto: addestrare e validare sugli stessi dati
*formalizza* l'overfitting invece di curarlo. Gemini e Perplexity hanno
confermato indipendentemente.

---

## La soluzione

Tre passi, in `segmenta_detector.py`:

1. **Rilevare le righe di testo** con il detector pre-addestrato di PaddleOCR
   (`TextDetection`, solo detection, niente riconoscimento).
2. **Proiettare** gli intervalli `[x_min, x_max]` di ogni riga sull'asse x e
   trovare le **colonne (quasi) vuote**: sono i separatori tra scontrini.
3. **Ritagliare** l'inviluppo di ogni gruppo di righe, con margine del 2%.

### Perché funziona

Il detector **non salda** gli scontrini adiacenti, perché lavora sui gradienti
ad alta frequenza dei caratteri e segmenta riga per riga. Su `07.47.51`, dove il
bottom-up produceva un blob unico, il profilo orizzontale delle righe è:

```
..#######..########...#######...#######..#######..
  ^scont.1  ^scont.2   ^scont.3  ^scont.4 ^scont.5
```

386 righe rilevate, **cinque gruppi separati da valli nette** larghe 62-111px,
mentre nessuno scontrino ne contiene una al proprio interno.

**Il falso positivo su legno sparisce gratis**: il detector non rileva righe di
testo sulla venatura, quindi la regione non viene mai proposta. Il problema che
aveva resistito a tre filtri diversi si è dissolto cambiando stadio — esattamente
la separazione di responsabilità suggerita dai tre consulenti.

### Le due soglie, e perché non sono tarature

- `empty_frac=0.05` — livello sotto cui una colonna è "vuota", **relativo** alla
  densità di testo della foto stessa, quindi indipendente da quanto i
  scontrini riempiono il fotogramma.
- `min_width=15` — larghezza minima della valle, in pixel.

Non è una coppia scelta al punto ottimo. È il **centro di un altopiano**:

```
valle minima ->    10    15    20    25    30    40
f=0.03            6/6   6/6   5/6   5/6   5/6   4/6
f=0.05            6/6   6/6   6/6   5/6   5/6   4/6
f=0.08            6/6   6/6   6/6   5/6   5/6   4/6
```

Quattro foto su sei sono corrette a **ogni** combinazione testata. Un massimo
isolato sarebbe stato il sospetto di overfitting che volevamo evitare; un
altopiano è la firma di un criterio che regge.

### Perché "quasi vuota" e non "vuota"

Con il criterio stretto (copertura esattamente zero) il punteggio era 5/6: su
`07.53.17` due scontrini si toccano e il varco assottiglia la copertura senza
mai azzerarla. Ammorbidire a "quasi vuota" ha dato 4 gruppi su tutte le soglie
dal 5% al 25%, di nuovo un altopiano.

---

## Gli scontrini sbiechi: raddrizzare il ritaglio, non la foto

Su `2025-09-06 10.43.15` tre scontrini accatastati e inclinati finivano in un
box solo. La causa e' geometrica: un testo inclinato di pochi gradi si spalma
lateralmente nella proiezione e riempie le valli che separano i fogli vicini.

Il deskew **globale** e' stato provato e **misurato peggiore** (4→3, 3→2, 4→2
gruppi): ruotando attorno al centro del fotogramma, gli scontrini ai bordi
scorrono lateralmente e le loro colonne si sovrappongono.

Funziona invece raddrizzare **solo il ritaglio sospetto**, trattandolo come una
foto a se': nient'altro nell'immagine si muove. L'angolo si ricava dal testo
stesso, come inclinazione mediana delle sue righe.

Un box e' "sospetto" per due segni indipendenti, e su trenta box misurati
l'unico difettoso e' il solo a superarli, senza casi al limite:

| | altri box | il box fuso |
|---|---|---|
| larghezza / fotogramma | 0.15 – 0.37 | **0.56** |
| righe di testo | 10 – 95 | **206** |

La procedura e' **ricorsiva**, e la misura ha mostrato perche' serve: quando
gli scontrini sono accatastati ad angoli diversi, ogni passata libera una
giuntura sola. La prima ha isolato il Mercadona lasciando insieme i due
Decathlon, ancora con 195 righe; la seconda li ha separati. Il tetto e' tre
passate.

Risultato su quella foto: da 3 box (di cui uno con tre scontrini) a **5 box,
uno per scontrino**. Le altre nove foto restano invariate.

## Limiti noti

- **I box aderiscono al testo, non alla carta.** Con `pad_frac=0.02` resta
  escluso un margine di carta bianca (visibile in `21.25.11`, striscia
  sinistra). Irrilevante per l'OCR, ma da sapere se servisse il foglio intero.
- **Costo**: il detector gira su CPU e richiede il modello PaddleOCR in cache
  (`~/.paddlex/official_models/PP-OCRv5_server_det`). Offline dopo il primo
  download.
- **oneDNN**: su questa build va disabilitato (`enable_mkldnn=False`), altrimenti
  `ConvertPirAttribute2RuntimeAttribute` fa fallire l'inferenza.
- **Solo split verticale.** Gli scontrini sono affiancati orizzontalmente in
  tutte e sei le foto. Scontrini impilati in verticale richiederebbero la stessa
  logica sull'asse y.
- **I ritagli ottenuti per rotazione sono piu' stretti.** I due Decathlon
  separati al secondo giro perdono un margine sul lato destro: restano
  leggibili (intestazione, articoli, totale) ma sono meno puliti dei box
  ottenuti al primo colpo. E' il prezzo del taglio su testo inclinato.
- **Sei foto restano poche.** 6/6 su un altopiano è un buon segnale, non una
  garanzia. La metrica IoU (sotto) va introdotta prima di dichiarare chiuso.

---

## Lavoro rimanente

1. **Metrica IoU** al posto del conteggio: etichettare a mano i box veri e
   misurare IoU medio, precision/recall a IoU≥0.7 e tasso di
   sotto-segmentazione. È l'unica difesa contro il ripetersi dell'overfitting,
   e avrebbe smascherato subito i due falsi successi di `07.57.06` e `21.12.47`.
2. ~~**Integrazione in `app/`**~~ — fatto: [`app/etl/segmenter.py`](../app/etl/segmenter.py).
3. ~~**Ritiro di `segmenta_bottomup.py`**~~ — fatto.
