# Fase G — Catalogo versionato nel database — Implementazione

**Data:** 2026-08-29  
**Decisione:** Centralizzare il catalogo E.1–E.5 dal file JSON al database  
**Stato:** ✅ Implementato e testato

## Riepilogo

La Fase G ha migrato i 292 file JSON del catalogo (E.1–E.5) in tre tabelle nel database:
- `catalog_versions` — versioni del catalogo (E.1_grezzo, E.2_clustered, E.3_canonical, E.4_split_proposed, E.5_split_applied)
- `catalog_snapshots` — snapshot dei prodotti per versione (790 record)
- `catalog_decisions` — audit trail delle decisioni umane (211 record)

**Vantaggi:**
- ✅ Single source of truth (il database, non file sparsi)
- ✅ Tracciabilità (chi ha deciso cosa, quando, con quale versione)
- ✅ Query facili per confrontare versioni
- ✅ Scalabilità (con il volume crescente oltre 96 foto)

## Schema

### catalog_versions

```sql
CREATE TABLE catalog_versions (
    version_id INTEGER PRIMARY KEY,
    phase TEXT NOT NULL CHECK (phase IN ('E.1_grezzo', 'E.2_clustered', 'E.3_canonical', ...)),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'final', 'deprecated')),
    created_at TEXT NOT NULL,
    description TEXT,
    stats TEXT (JSON)
);
```

**Uso**: ogni fase E genera una riga qui. Status = 'final' se pronto, 'draft' se in iterazione.

### catalog_snapshots

```sql
CREATE TABLE catalog_snapshots (
    id INTEGER PRIMARY KEY,
    version_id INTEGER NOT NULL,
    logical_item_id TEXT,              -- chiave stabile (es. 'item_001')
    product_id INTEGER,
    canonical_name TEXT NOT NULL,
    aka_list TEXT (JSON),              -- sinonimi
    frequency INTEGER,
    cluster_id INTEGER,                -- per tracciare il cluster di origine
    confidence REAL,
    metadata TEXT (JSON),
    UNIQUE(version_id, logical_item_id)
);
```

**Uso**: ogni nome/cluster/prodotto canonico è una riga qui, tracciato fra le versioni con `logical_item_id`.

### catalog_decisions

```sql
CREATE TABLE catalog_decisions (
    id INTEGER PRIMARY KEY,
    version_id INTEGER NOT NULL,
    decision_type TEXT NOT NULL CHECK (decision_type IN ('CLUSTER_MERGE', 'FUSED_SPLIT', 'SKIP', 'REVIEW')),
    target_type TEXT NOT NULL CHECK (target_type IN ('cluster', 'snapshot', 'receipt_line')),
    target_id INTEGER NOT NULL,
    decision_value TEXT,               -- 'MERGE_TO_X', 'SPLIT_OK', etc.
    metadata TEXT (JSON),
    approved_by TEXT,
    created_at TEXT,
);
```

**Uso**: ogni decisione umana è una riga qui, con audit trail completo.

## Migrazione eseguita

Script: `scripts/fase_g_migra_catalogo_al_db.py`

**Input**: file JSON da E.1–E.5
- `fase_e_1_catalogo_grezzo.json` → 729 nomi + 1 versione
- `fase_e_2_cluster_sinonimi.json` → 61 cluster + 1 versione
- `fase_e_validazioni_sinonimi.json` → 61 decisioni (MERGE/SKIP)
- `fase_e_4_proponi_spezzatura.json` → 1 versione
- `fase_e_validazioni_fused.json` → 150 decisioni (SPLIT/CANNOT_SPLIT)

**Output nel database:**

```
catalog_versions:    5 righe (E.1, E.2, E.3, E.4, E.5)
catalog_snapshots:  790 righe (729 grezzo + 61 cluster)
catalog_decisions:  211 righe (61 sinonimi + 150 fused)
```

**Verifica**: migrazione completata senza errori, tutti i dati presenti.

## Vantaggi realizzati

### 1. Single Source of Truth

Prima: 292 file JSON sparsi in data/
Dopo: tutto nel database

### 2. Tracciabilità

Puoi domandare:
- "Quali cluster erano in E.2?"
- "Chi ha approvato la merge A→B?"
- "Quali versioni del catalogo ho testato?"
- "Quando ho deciso di splittare il fused X?"

Con un JOIN su `catalog_decisions.created_at`, risponde subito.

### 3. Query facili

```sql
-- Nomi grezzo (E.1)
SELECT canonical_name, frequency FROM catalog_snapshots
WHERE version_id = (SELECT version_id FROM catalog_versions WHERE phase = 'E.1_grezzo');

-- Cluster con >2 elementi (E.2)
SELECT * FROM catalog_snapshots
WHERE cluster_id IS NOT NULL AND version_id = ...
GROUP BY cluster_id HAVING COUNT(*) > 1;

-- Decisioni non approvate automaticamente
SELECT * FROM catalog_decisions
WHERE approved_by != 'auto' AND decision_value = 'REVIEW';
```

### 4. Scalabilità

Con il dataset che cresce (96→1000 foto):
- File JSON proliferano → caos operativo
- Database centralizzato → ordine, performance

## Cost-benefit

### Costo
- Refactoring di E.1–E.5 per scrivere nel DB (1–2h)
- Complessità schema (ma è contenuta: 3 tabelle)

### Beneficio
- Eliminazione di 292 file sparsi
- Tracciabilità audit trail
- Query deterministiche su versioni
- Pronto per iterazioni di Fase F+

**ROI**: alto quando il volume cresce, medio ora. Investimento future-proof.

## Prossimi passi

### Fase F: Categorizzazione + Weight extraction

1. Estrai peso dai nomi fused/incomplete (regex: "X KG", "X G", etc.)
2. Aggiungi colonne `quantity_value`, `quantity_unit` a `receipt_lines`
3. Calcola `price_per_kg` quando applicabile
4. Categorizza i 679 prodotti (frutta, latticini, pane, etc.)
5. Report: "Quanto spendo in frutta?"

### Fase G.2 (opzionale): Refactorizza E.1–E.5 per scrivere direttamente nel DB

Attualmente:
- E.1–E.5 scrivono JSON
- G migra JSON → DB

Migliore (quando hai tempo):
- E.1–E.5 scrivono direttamente nel DB
- Niente step di migrazione, zero file JSON operativi

## File creati

- `scripts/fase_g_migra_catalogo_al_db.py` — migrazione JSON→DB
- `docs/70_fase_g_catalogo_versionato_db.md` — questo documento

## Documenti correlati

- `docs/60_piano_fase_e_catalogo.md` — Fase E (catalogo grezzo)
- `docs/61_risultati_fase_e_catalogo.md` — Risultati Fase E
- `app/db/db_manager.py` — schema nuovo (tabelle catalogo)
