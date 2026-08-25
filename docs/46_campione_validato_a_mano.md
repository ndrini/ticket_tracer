# Il campione riletto a mano — 2026-08-24

Otto scontrini riletti dall'immagine e validati dall'utente, per capire da dove
viene il 28% di quadratura. Sono la prima verita' di riferimento sull'ESTRAZIONE
che questo progetto possiede: `data/verita_riferimento.json` copre la
segmentazione, non i prodotti.

**Le immagini non stanno qui.** Contengono nomi, DNI e numeri di carta: restano
in `data/ritagli/`, che non e' versionato. Si rigenerano dall'hash.

## Perche' e' servito

La diagnosi fatta a tavolino era: «l'OCR legge, il modello non restituisce».
Poggiava su un conteggio di stringhe che somigliano a importi (`\d{1,4}[.,]\d{2}`)
nel testo OCR — che conta anche aliquote IVA, resto e contante, non prodotti
recuperabili — e su UN caso letto a mano che si e' rivelato non rappresentativo.

Quattro agenti su quattro (Vibe, Perplexity, Copilot, Gemini) hanno confermato
quella diagnosi. **Erano tutti d'accordo e sbagliavano tutti.** A correggerli e'
bastato guardare otto immagini.

## Gli otto casi

| # | hash | negozio | esito registrato | cosa c'e' davvero |
| --- | --- | --- | --- | --- |
| A | `8b760724d949` | Decathlon + Pepco | `PRODOTTI_ASSENTI` | **due scontrini nel ritaglio**. Decathlon 24,99+7,99=32,98; Pepco 2,50. Totale letto 32,38: viene dalla riga IVA, con una cifra sbagliata |
| B | `989d19fad56a` | Mercadona + Alcampo + benzinaio | `SOMMA_IN_DIFETTO` | **tre scontrini nel ritaglio**. Mercadona: 6 prodotti, somma 15,75 = totale stampato; ne sono stati estratti 3. Alcampo 3,57. Il negozio registrato, `Phlas Maxeip`, e' testo dell'Alcampo letto male |
| C | `0ba230e1ebee` | Consum/Charter | `VALIDO` | corretto, 10 prodotti, 38,50. Ritaglio pulito. Due prodotti hanno il prezzo su riga separata e il modello li ha recuperati lo stesso |
| D | `3d6f44d1de1b` | IKEA Badalona | `PRODOTTI_ASSENTI` | **non ci sono prodotti**: e' l'intestazione di una fattura con due paragrafi di informativa privacy. L'esito e' CORRETTO. Il totale 129,50 e' inventato |
| E | `20e8047e9163` | Cal Fruitos | `PRODOTTI_ASSENTI` | ~17 prodotti su **due righe ciascuno** (nome sopra, peso/€kg/importo sotto). Totale vero **40,58**, con sconto 10% −4,51 e annullazione −1,63. Letto 24,09 |
| F | `11b9b668a333` | IKEA Glories | `PRODOTTI_ASSENTI` | **e' un reso**: `Anul.la el tiquet`, tre `Devolucio` (24,99/17,99/16,00), totale 58,98, pagamento −58,98 |
| G | `152cf78ab94f` | IKEA | `SOMMA_IN_DIFETTO` | 8 articoli su **tre righe ciascuno** (codice, nome, importo). Totale 52,00; ne e' stato estratto 1, scarto −50,50 |
| H | `325c72d0d73c` | Decathlon | `PRODOTTI_ASSENTI` | **un reso** (quantita' −1, −6,99) **e** un ritaglio con due strisce di altri scontrini ai bordi |

## I quattro meccanismi, e quanto pesano

Nessuno degli otto e' «il modello non ha risposto».

### 1. Layout a piu' righe per prodotto — il piu' frequente

Nome su una riga, importo su quella dopo. E' come IKEA e Cal Fruitos stampano,
non un difetto di lettura. `_e_riga_prodotto` pretende nome e importo sulla
STESSA riga (`len(riga) < 6 or not IMPORTO.search(riga)`) e scarta entrambe.

Misurato su 218 scontrini, contando quelli in cui le righe spezzate superano le
complete:

| esito | dominati dal layout a piu' righe |
| --- | --- |
| `PRODOTTI_ASSENTI` | **28%** (16/57) |
| `SOMMA_IN_DIFETTO` | 16% (11/70) |
| `VALIDO` | **5%** (3/62) |

Quasi sei volte piu' frequente nei falliti. E' un'assunzione sbagliata nel
codice, non un problema di OCR ne' di modello.

### 2. Ritagli con piu' scontrini

Rivelati dal divario orizzontale massimo fra i centri dei frammenti OCR: due
scontrini affiancati lasciano un vuoto fra le due colonne.

| esito | ritagli a due colonne (gap > 25%) |
| --- | --- |
| `PRODOTTI_ASSENTI` | **18%** |
| `VALIDO` | 3% |

La ricomposizione incolla orizzontalmente righe di scontrini diversi: in A il
nome del prodotto Decathlon finisce su una riga e il prezzo sulla successiva,
insieme all'indirizzo di Pepco.

⚠️ **Il «16/16» della segmentazione e' misurato su 6 foto di riferimento e non
descrive il materiale reale**: su otto ritagli, tre contengono piu' scontrini o
tagliano via i prodotti.

### 3. Documenti che prodotti non ne hanno

Fatture, informative, buoni sconto (il gia' noto `0260bfd2f37f`, Milbby).
`PRODOTTI_ASSENTI` e' l'esito giusto. Vanno **riconosciuti e marcati**, non
estratti meglio. Osservazione dell'utente su D: probabilmente esiste lo
scontrino gemello con la stessa data, quindi il documento e' da ignorare, non da
recuperare.

### 4. Resi

Due su otto. Importi negativi, `Devolucio` / `Anul.la el tiquet` / quantita' −1.
Non sono acquisti: trattarli come tali falsa i conti prima di qualunque
estrazione. Nessuno dei quattro agenti li aveva previsti.

## Cosa se ne ricava per il metodo

- **Il consenso non e' una prova, e stavolta e' costato una diagnosi intera.**
  Quattro agenti concordi, smentiti da otto immagini.
- **Un proxy non e' una misura.** Contare le stringhe che somigliano a importi
  non dice quanti prodotti si stanno perdendo. Il segnale che i `VALIDO` avevano
  14,1 «importi» e 4,0 prodotti estratti avrebbe dovuto far sospettare subito
  che la metrica misurasse altro.
- **Un caso scelto perche' leggibile non e' un campione.** Il Mercadona pulito su
  cui poggiava la diagnosi era stato scelto proprio per la sua leggibilita'.
