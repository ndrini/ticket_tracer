# Piano Fase E — Catalogo e Normalizzazione Nomi

**Data:** 2026-08-29  
**Approccio:** Opzione C (iterativa con checkpoint umano), consigliato da Perplexity  
**Responsabile:** Claude Haiku + validazione umana su casi ambigui

## Riepilogo esecutivo

La Fase E trasforma i 1300 nomi "complete" in un **catalogo canonico**, normalizzando sinonimi e spezzando i 150 nomi "fused" (probabilmente due prodotti in uno). L'approccio è iterativo: si costruisce il catalogo grezzo dai nomi affidabili, si normalizza con supervisione umana, poi si usa il catalogo per spezzare i fused.

**Risultato atteso**:
- Catalogo canonico con ~800–1000 prodotti unici (deduplica i sinonimi)
- 1300 righe "complete" mappate al catalogo canonico
- 150 righe "fused" spezzate in 250–300 righe di nuovi prodotti
- Conversione di 0–24 righe "incomplete" o marcate come usabili

## Strategie scartate e motivo

### ❌ Opzione A: Catalogo → Dizionario → Spezzatura

**Problema**: il catalogo grezzo contiene sinonimi non normalizzati (mela, mele, MELA). Se li normalizzi *dopo*, devi refactorizzare i `product_id` nelle `receipt_lines`: operazione rischiosa e costosa.

**Rischio misurato da Perplexity**: la spezzatura dei fused usa un catalogo "sporco", propagando errori di sinonimia nel nuovo catalogo spezzato.

### ❌ Opzione B: Normalizzazione → Catalogo → Spezzatura

**Problema**: costruisci un dizionario "a priori" senza vedere il catalogo reale. Rischio di over-normalization ("melone" + "melagrana" → "mela" erroneamente) e mancanza di scalabilità.

**Rischio misurato da Perplexity**: dipendenza da regole costruite nel vuoto; ogni nuovo dominio di prodotti richiede aggiustamenti manuali.

### ✅ Opzione C: Catalogo grezzo → Normalizzazione supervisionata → Catalogo canonico → Spezzatura (SCELTA)

**Vantaggio**: si costruisce il catalogo su dati reali, si normalizza con revisione umana su casi ambigui, poi si usa il catalogo stabile per spezzare.

**Vantaggi**:
- Catalogo fondato su evidenza, non su ipotesi
- Normalizzazione supervisionata evita over-fitting
- Circolarità minimizzata (mai usare fused per "insegnare" il catalogo principale)

**Costi**:
- Step umano su cluster di sinonimi ambigui
- Timing più lungo (iterativo, non batch)

**Accettabile per il dataset**: 93 scontrini, 1300 righe complete, ~50–100 cluster di sinonimi stimati.

## Metriche dichiarate PRIMA di misurare

### Principale: Preservation (preservazione dei dati affidabili)

```
Preservation = (righe 'complete' ancora mappate dopo Fase E) / 1300
```

**Vincolo**: deve stare a ~100%. Se scende, stai normalizzando in modo distruttivo.

**Fallimento**: se Preservation < 95%, la Fase E ha cancellato informazione. Stop e debug.

### Di guardia 1: Coverage dei fused (spezzatura riuscita)

```
FusedCoverage = (righe 'fused' spezzate in almeno 2 token) / 150
```

**Vincolo**: cerchiamo di spezzare il 70%+ dei fused (105 su 150).

**Se fallisce**: significa che il catalogo canonico è troppo generico oppure le regole di spezzatura non riconoscono gli abbinamenti di due prodotti in uno.

### Di guardia 2: Nuovi prodotti creati

```
ProduzioniNuove = (prodotti nel catalogo dopo spezzatura fused) - (prodotti nel catalogo canonico)
```

**Vincolo**: atteso ~50–150 nuovi prodotti dalla spezzatura.

**Se fallisce**: se è 0, nessun fused è stato spezzato (FusedCoverage basso). Se è > 300, stai spezzando in frammenti troppo piccoli (ogni token è un prodotto, non riconosci gli abbinamenti).

### Di guardia 3: Conflict rate (token non riconosciuti)

```
ConflictRate = (token da fused non presenti nel catalogo canonico) / (token totali da spezzatura fused)
```

**Vincolo**: < 5%. Se è più alto, significa che la spezzatura produce parole che il catalogo grezzo non conosce (es. errori OCR, abbreviazioni non normalizzate).

## Fasi di esecuzione

### Fase E.1: Costruisci il catalogo grezzo (script)

**Input**: `receipt_lines` con `name_quality = 'complete'` e `extraction_method = 'geometric'`.

**Output**: `products_canonical` (tabella temporanea) con un record per ogni stringa distinta normalizzata per casing e whitespace.

**Algoritmo**:
```python
1. SELECT DISTINCT LOWER(TRIM(r.name)) as canonical_name
   FROM receipt_lines r
   WHERE r.name_quality = 'complete' AND r.extraction_method = 'geometric'
   
2. Per ogni canonical_name:
   - Conta quante righe lo usano
   - Registra il nome_originale più frequente (come "display name")
   - Crea un record in products_canonical
```

**Risultato atteso**: ~1000–1200 prodotti unici.

**Script**: `scripts/fase_e_1_catalogo_grezzo.py`

### Fase E.2: Identifica cluster di sinonimi (script + umano)

**Input**: `products_canonical` dal passo precedente.

**Algoritmo**:
1. Genera cluster di sinonimi usando:
   - **Distanza testuale** (Levenshtein, distanza max 2 per edit distance normalizzata)
   - **Prefissi comuni** (primi 5 caratteri)
   - **Lunghezza simile** (±3 caratteri)

2. Per ogni cluster, genera un report:
   ```
   Cluster 15:
     - mela (45 occorrenze)
     - mele (28 occorrenze)
     - MELA (12 occorrenze)
     
   Suggerito: merge a "mela" ✓
   ```

**Output**: Report JSON con cluster marcati come:
- ✅ Automatico (alta confidenza, es. solo case differences)
- ❓ Richiede validazione umana (ambiguo)

**Script**: `scripts/fase_e_2_cluster_sinonimi.py`

**Step umano**: revisionare i cluster marcati come ❓ e approvare i merge.

**File di validazione**: `data/fase_e_validazioni_sinonimi.json`

Formato:
```json
{
  "cluster_15": {
    "suggerimento": "merge a 'mela'",
    "elementi": ["mela", "mele", "MELA"],
    "approvazione_umana": "✓",
    "decisione": "MERGE_A_MELA"
  }
}
```

### Fase E.3: Applica la normalizzazione (script)

**Input**: 
- `products_canonical` 
- `data/fase_e_validazioni_sinonimi.json` con le decisioni umane

**Output**: 
- `products_normalized` (tabella database)
- Mappa `{nome_originale → product_id_canonico}`

**Algoritmo**:
```python
1. Per ogni cluster con decisione umana:
   - Crea un record in products_normalized con il nome canonico
   - Registra tutti i sinonimi in products.aka
   - Genera la mappa nome_originale → product_id

2. UPDATE receipt_lines SET product_id = mapped_id
   WHERE name_quality = 'complete' AND extraction_method = 'geometric'
```

**Misura**: Preservation = 1300 righe ancora mappate post-update. Deve essere ~100%.

**Script**: `scripts/fase_e_3_applica_normalizzazione.py`

### Fase E.4: Spezzatura dei nomi fused (script + umano)

**Input**:
- 150 righe con `name_quality = 'fused'`
- `products_normalized` (catalogo canonico)

**Algoritmo**:
1. Per ogni nome fused (es. "LLEVAT ROYAL 80G 6 LLET SEN.CONSUM 1L"):
   - Dividi in token (splitting per spazi e punteggiatura)
   - Per ogni token, cerca il miglior match nel catalogo canonico
   - Se 2+ token trovano un match con alta confidenza (Levenshtein < 3), suggerisc la spezzatura

2. Genera un report:
   ```
   Fused: "LLEVAT ROYAL 80G 6 LLET SEN.CONSUM 1L"
   Match 1: "LLEVAT ROYAL 80G" → id_prod_123 (conf 95%)
   Match 2: "LLET SEN.CONSUM 1L" → id_prod_456 (conf 98%)
   
   Suggerito: spezzatura in due righe ✓
   ```

3. Per i match < 80% di confidenza: marca come ❓ per revisione umana.

**Output**: Report JSON con proposte di spezzatura.

**File di validazione**: `data/fase_e_validazioni_fused.json`

**Script**: `scripts/fase_e_4_proponi_spezzatura.py`

**Step umano**: revisionare i casi ❓ e approvare le spezzature.

### Fase E.5: Applica la spezzatura (script)

**Input**:
- Righe `fused` dal database
- `data/fase_e_validazioni_fused.json` con le decisioni umane

**Output**:
- Nuove righe in `receipt_lines` (una per ogni prodotto spezzato)
- Colonna `receipt_lines.split_from_fused_id` che traccia l'origine

**Algoritmo**:
```python
1. Per ogni fused con decisione umana SPLIT_OK:
   - Leggi gli id_prod dalla decisione
   - Dividi il prezzo proporzionalmente ai prezzi noti dei prodotti
   - Inserisci due righe nuove in receipt_lines
   - Marca l'originale con split_from_fused_id (soft delete)
```

**Misura**:
- FusedCoverage = (righe fused spezzate) / 150
- ProduzioniNuove = (prodotti nuovi creati)
- ConflictRate = (token non riconosciuti) / (token totali)

**Script**: `scripts/fase_e_5_applica_spezzatura.py`

## Algoritmo di matching per la spezzatura (dettaglio tecnico)

Per cada token nel nome fused, cerchiamo il miglior match nel catalogo canonico:

```python
def best_match_in_catalog(token, catalog, threshold=0.8):
    """
    Cerca il miglior match di un token nel catalogo.
    
    Ordine di priorità:
    1. Match esatto (case-insensitive)
    2. Levenshtein distance < 2
    3. Token è substring di un nome nel catalogo
    4. Prefisso comune (primi 5 char)
    
    Restituisce (product_id, confidenza) o (None, 0).
    """
```

**Rationale**: l'OCR a volte taglia o fonde i token. Cerchiamo il nome nel catalogo che somigli di più al token trovato.

## Rollback e recupero da errori

Se in uno step trovi Preservation < 95% o ConflictRate > 5%:

1. **Rollback**: cancella gli insert dalla Fase E.3/E.5 usando le colonne di traccia (`split_from_fused_id`, `normalized_from_id`)
2. **Debug**: rivedi i cluster di sinonimi o le proposte di spezzatura
3. **Riprova**: riesegui lo script di normalizzazione/spezzatura con parametri aggiustati

## Timeline e dipendenze

```
E.1 (Catalogo grezzo)
  ↓
E.2 (Cluster sinonimi) → Step umano: validazione
  ↓
E.3 (Applica normalizzazione, misura Preservation)
  ↓
E.4 (Proponi spezzatura) → Step umano: validazione
  ↓
E.5 (Applica spezzatura, misura FusedCoverage + ConflictRate)
```

**Tempo totale stimato**: 4–6 ore (2h script + 2–4h revisione umana).

## File da creare

- `scripts/fase_e_1_catalogo_grezzo.py` — catalogo dai nomi complete
- `scripts/fase_e_2_cluster_sinonimi.py` — identifica cluster di sinonimi
- `scripts/fase_e_3_applica_normalizzazione.py` — normalizza e rebind le righe
- `scripts/fase_e_4_proponi_spezzatura.py` — propone la spezzatura dei fused
- `scripts/fase_e_5_applica_spezzatura.py` — applica la spezzatura

- `data/fase_e_validazioni_sinonimi.json` — decisioni umane su cluster
- `data/fase_e_validazioni_fused.json` — decisioni umane su spezzatura

## Successiva: Fase F (Categorizzazione)

Con il catalogo canonico in mano, si possono categorizzare i 900–1100 prodotti finali (frutta, latticini, etc.) e rispondere a domande come "Quanto spendo in frutta?"

## Documenti correlati

- `docs/50_risultati_collegamento_geometrico.md` — baseline e dati in ingresso
- `scripts/report_nomi.py` — metriche sui nomi existing
- Memory: [[come-consultare-gli-altri-agenti.md]] — consultazione con Perplexity
