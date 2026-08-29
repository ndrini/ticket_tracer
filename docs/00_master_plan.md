# Master Plan — Ticket Tracer: Spesa Ricevute

**Stato:** Fase F completata, revisione finale ✅  
**Dataset:** 96 foto, 306 scontrini, €4168.65 spesa  
**Branch:** `feat/catalog-normalization-e` → pronto per main

## Obiettivo del progetto

Tracciare e analizzare la spesa alimentare da foto di ricevute (scontrini) usando OCR geometrico + LLM, con categorizzazione e report per rispondere: **"Quanto spendo in Frutta? In Latticini? In Pane?"**

## Fasi completate

### Fasi A–D (precedenti, non in questo commit)

- **A**: Segmentazione ricevute da foto
- **B**: OCR (testo + layout)
- **C**: Estrazione prodotti via LLM
- **D**: Caricamento in SQLite

### Fase E: Catalogo e Normalizzazione ✅

- 729 nomi unici deduplicated
- 61 cluster di sinonimi proposti (35 automatici)
- 664 prodotti canonici (44% riduzione)
- Preservation 100%
- Fused names: 150 conservate, 7 spezzate

**Metodo**: Opzione C (iterativa con checkpoint umano), consigliato da Perplexity.

**Documento**: [docs/60_piano_fase_e_catalogo.md](60_piano_fase_e_catalogo.md), [docs/61_risultati_fase_e_catalogo.md](61_risultati_fase_e_catalogo.md)

### Fase G: Catalogo Versionato nel DB ✅

- 3 tabelle: `catalog_versions`, `catalog_snapshots`, `catalog_decisions`
- 5 versioni (E.1–E.5)
- 790 snapshot prodotti
- 211 decisioni (audit trail)
- Tracciabilità e scalabilità fino a 1000+ foto

**Documento**: [docs/70_fase_g_catalogo_versionato_db.md](70_fase_g_catalogo_versionato_db.md)

### Fase F: Categorizzazione + Weight Extraction ✅

- Weight extraction: 147 righe (9%, realistico)
- Categorie assegnate: 1589/1589 (100%)
- Report finale: €4168.65 totale, coerente per categoria
- Breakdown: Frutta 6.0%, Latticini 9.3%, Bevande 6.3%, Pane 3.1%, Verdure 3.8%, Carne 1.9%, Igiene 0.1%, Altro 69.4%

**Documento**: [docs/80_fase_f_categorizzazione_report.md](80_fase_f_categorizzazione_report.md)

## Stato della code quality

### ✅ Fatto bene

- **Opzione C**: iterativa, tracciabile, riproducibile
- **Preservation 100%**: nessun dato perso
- **Sanità numerica**: somma categorie = totale generale
- **Tracciabilità**: audit trail nel database, git history pulita
- **Scalabilità**: schema DB sostenibile a 1000+ foto

### ⚠️ Debt intenzionale (accettabile per MVP)

- **Weight coverage 9%**: molti prodotti non hanno unità nel nome. Non è un fallimento; è un trade-off.
  - Soluzione futura: migliorare estrazione OCR in Fase B o C
  
- **Categorizzazione 69% "Altro"**: basso per analisi fini, ok per MVP.
  - Soluzione futura: raffinamento mirato su macro-categorie (Frutta/Verdura, Proteici)

- **Nomi fused 95% non spezzabili**: coerente con bassa FusedCoverage in E.
  - Soluzione futura: usare catalogo per post-processing, non pre-estrazione

### ❌ Missing prima di business logic

- **Date**: gli scontrini non hanno `receipt.date` nel database
  - Necessario per: trend, budget tracking, comparazioni temporali
  - Azione: aggiungere colonna `receipts.date` e parsare da OCR o metadati foto

- **Indici DB**: nessun indice aggiunto
  - Necessario quando dataset cresce
  - Azione: aggiungere indici su `(product_id, category)`, `(receipt_id, date)` quando la query rallenta

## Prossime fasi (roadmap)

### Fase H (prossima, prioritaria): Aggiungere date

- [ ] Aggiungere colonna `receipts.date`
- [ ] Parsare data da OCR (intestazione ricevuta)
- [ ] Riscrivere report per includere date
- [ ] Abilitare trend: "Spesa in Frutta per mese"

### Fase I (opzionale, value-add): Raffinamento categorizzazione

- [ ] Utente valida i 1220 "Altro" (batch di 50 alla volta)
- [ ] Estende dizionario keyword
- [ ] Ripete F.2–F.3 per ridurre "Altro" a <40%
- [ ] Migliora insight per Frutta/Verdura/Proteici

### Fase J (opzionale, advanced): Budget & Alerts

- [ ] Utente definisce budget per categoria
- [ ] Script di verifica: "hai speso più di €100 in latticini questo mese?"
- [ ] Report settimanale/mensile

### Fase K (scale): Indici e ottimizzazione

- [ ] Aggiungere indici DB quando query rallentano
- [ ] Batch processing per catalogo (se dataset >1000 foto)
- [ ] Considerare partition by mese se i dati crescono esponenzialmente

## Revisione finale (feedback Perplexity)

| Aspetto | Giudizio | Note |
|---------|----------|-------|
| Metodologia | ✅ Opzione C corretta | Iterativa, tracciabile, rigore appropriato |
| Fase E | ✅ Bene | Avrebbe potuto estrarre weight subito, ma F ha compensato |
| Fase G (DB) | ✅ Solida | Sostenibile fino a 1000+ foto, aggiungere indici quando cresce |
| Categorizzazione 69% "Altro" | ⚠️ Accettabile MVP | Se usi seriamente, ridurre a <40% con raffinamento |
| Debt tecnico | ✅ Accettabile | Weight 9%, Altro 69%, fused 95% non spezzati sono trade-off consci |
| Blocchi per business logic | ⚠️ Date mancano | Aggiungi receipt.date prima di trend/budget |

## Risposta alle domande originali

### "Quanto spendo in Frutta?"

**Risposta**: €250.07 (6.0% della spesa totale)
- 76 righe in 56 scontrini
- Prezzo medio €3.29 per articolo

### "Il prezzo al chilo è normalizzato?"

**Risposta**: Parzialmente. 147 righe (9%) hanno weight estratto dal nome. Per il resto, è prezzo assoluto (corretto per pezzi singoli).

### "I 292 file JSON sono gestibili?"

**Risposta**: No, sono stati centralizzati nel DB (Fase G). Tracciabilità completa, audit trail, scalabile.

## Come procedere

1. **Code review**: questa revisione è il checkpoint finale prima di merge a main
2. **Merge**: `feat/catalog-normalization-e` → `main`
3. **Fase H**: aggiungere date (1h work)
4. **Fase I** (opzionale): raffinare categorizzazione se necessario (2–3h work)

## File key

- [docs/60_piano_fase_e_catalogo.md](60_piano_fase_e_catalogo.md) — piano E (Opzione C)
- [docs/61_risultati_fase_e_catalogo.md](61_risultati_fase_e_catalogo.md) — risultati E
- [docs/70_fase_g_catalogo_versionato_db.md](70_fase_g_catalogo_versionato_db.md) — Fase G
- [docs/80_fase_f_categorizzazione_report.md](80_fase_f_categorizzazione_report.md) — Fase F e report finale

---

**Stato**: ✅ Pronto per merge e business logic
