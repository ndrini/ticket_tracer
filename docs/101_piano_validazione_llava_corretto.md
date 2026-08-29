# Piano Corretto: Validazione LLaVA su Dati Reali

**Data**: 2026-08-29  
**Stato**: ⚠️ Ho fatto un errore (test su immagini sintetiche), correggo prima di switchare

---

## L'Errore Che Ho Fatto

Ho eseguito il benchmark LLaVA su **immagini sintetiche bianche con testo disegnato** e ho detto:
- "100% success rate, switch subito a LLaVA"
- Questo **viola il metodo** nel CLAUDE.md: "Misura prima di diagnosticare"

**Problema critico**:
- Immagini sintetiche ≠ scontrini fotografati reali
- 100% accuracy fake ≠ 70-85% accuracyAttesa su dati reali (Perplexity)
- Ho ignorato che LLaVA è stocastico (3 run potrebbero dare risultati diversi)
- Nessuna misura di hallucination (falsi prodotti inventati)

---

## Feedback Agenti (Rivisto)

### Perplexity

**Verdict**: Piano validazione è "parzialmente sound", ma:

1. **Metriche mancanti**:
   - Precision/Recall/F1 per item
   - Variance tra run (LLaVA è stocastico)
   - Hallucination rate (falsi prodotti)
   - Robustezza per tipo scontrino (sfocati, curvi, riflessi)
   - p95/p99 latency, non solo media

2. **Accuracy reale attesa**:
   - LLaVA 1.5 7B su foto reali: **"mi sembra ottimistico"** aspettarsi > 75%
   - VLM generalista peggiore di pipeline OCR specializzata su receipts
   - **Coda lunga di errori** su casi difficili (layout anomali)

3. **Hallucination su receipts**:
   - Non solo "classica hallucination", anche:
     - Spurious line splitting
     - Merging righe
     - Lettura inventata prezzi
     - Sostituzione nomi simili
   - **Threshold 5% è troppo permissivo** per dati finanziari

4. **Sample size 50**:
   - Sufficiente solo per go/no-go preliminare
   - Varianza tra scontrini è alta
   - Meglio: **pilot 50, poi 100-200 per decisione forte**

5. **Switch in produzione?**
   - **NO**, non basta vincere su 50 campioni
   - Serve cross-validation, stratificazione, test di robustezza

### Vibe

**Verdict**: Piano è "tactica OK, strategica rischiosa"

1. **Sample size 50**: Sufficiente per "tactical decision" (α=0.05, power 80%)
   - Ma disponibili solo ~30 in `private/campione_validato/`
   - Serve integrare 20 da `data/spese.db` se immagini esistono

2. **Switch immediately**: **NO**
   - Serve **cross-validation**: split 50 in 2×25
   - Se LLaVA vince su entrambi, OK switchare
   - Altrimenti, fallback a Geometric

3. **Variance LLaVA**: Esegui **3 run per scontrino** con seed diversi
   - Riporta media ± std
   - Se std > 5%, sample insufficiente

4. **Fallback strategy**:
   - **Primary: Geometric** (deterministico, 58%, affidabile)
   - **Secondary: LLaVA** per edge cases (confidence < 50%)
   - **Halt condition**: Hallucination > 5% → non usa LLaVA

5. **Effort totale**:
   - 50 scontrini × 3 run × 3s = 450s GPU
   - Validazione manuale 2h (check falsi positivi)
   - **Totale: mezza giornata**

---

## Consenso Agenti

| Punto | Verdict |
|-------|---------|
| **Sample size 50** | ✅ OK per pilot, ma cross-validate su 2×25 |
| **Accuracy reale attesa** | ⚠️ 70-85% è ottimistico, realisticamente 65-75% |
| **Hallucination** | ⚠️ Problema critico, misura esplicitamente |
| **Primary o Fallback?** | ✅ Primary: Geometric, Fallback: LLaVA |
| **Switch immediato?** | ❌ NO, serve validazione statistica |
| **Timeline** | ✅ Mezza giornata per test completo |

---

## Piano Corretto (DA ESEGUIRE)

### Fase 1: Preparazione (1h)

1. **Conta scontrini disponibili**:
   - `private/campione_validato/`: ≈30 immagini
   - `data/spese.db`: 287 scontrini con extraction_method='geometric'
   - Verificare se immagini correlate esistono

2. **Decidi sample size finale**:
   - Ideale: 50 scontrini
   - Disponibili: ~30 (max)
   - Fallback: 30 reali + 20 random da DB

3. **Prepara metriche foglio**:
   ```
   Per ogni scontrino:
   - Immagine
   - Geometric items (baseline)
   - LLaVA run 1, run 2, run 3 (3 seed diversi)
   - Ground truth manuale? (opzionale, time-intensive)
   - Accuracy nome (match %)
   - Accuracy prezzo (match ±0.05€)
   - Items extra (hallucination)
   - Items mancanti
   - Success rate
   ```

### Fase 2: Esecuzione Benchmark (3-4h)

**Setup**:
```bash
# Per ogni scontrino in sample_set:
for i in {1..30}; do
  # Run LLaVA 3 volte con seed diversi
  for seed in 42 43 44; do
    python extract_llava.py \
      --image private/campione_validato/scontrino_$i.jpg \
      --seed $seed \
      --output results/run_${i}_seed_${seed}.json
  done
  
  # Confronta con Geometric
  python compare_llava_vs_geometric.py \
    --scontrino_id $i \
    --llava_runs results/run_${i}_seed_*.json \
    --geometric_baseline data/spese.db
done
```

**Output**:
- CSV con metriche per ogni scontrino
- Summary: accuracy media, std, hallucination rate

### Fase 3: Analisi (2h)

1. **Metriche aggregate**:
   - LLaVA accuracy media (±std)
   - Hallucination rate
   - Latency distribution (p50, p95)
   - Variance tra run

2. **Cross-validation**:
   - Split 30 in 2×15
   - Ripeti analisi su each split
   - Se LLaVA wins su entrambi → go
   - Altrimenti → fallback a Geometric

3. **Stratificazione**:
   - Accuracy per "tipo scontrino":
     - Pulito vs sfocato
     - Corto (<5 items) vs lungo
     - Layout standard vs anomalo

### Fase 4: Decisione (basata su dati)

| Scenario | Accuracy | Hallucination | Decision |
|----------|----------|----------------|----------|
| A | > 75% | < 3% | ✅ Considera switch (validation statistica) |
| B | 70-75% | < 5% | ⚠️ Hybrid (Geometric primary) |
| C | 65-70% | < 5% | ❌ Mantieni Geometric |
| D | < 65% o > 5% halluc | > 5% | ❌ Geometric vince |

**SE scenario A E cross-validation passa**: Considera switch con fallback safety net
**ALTRIMENTI**: Mantieni Geometric, LLaVA come fallback

---

## Timeline

| Fase | Effort | Tempo |
|------|--------|-------|
| 1. Preparazione | 1h | Oggi |
| 2. Benchmark | 450s GPU + 2h analisi | Domani (mattina) |
| 3. Cross-validation | 2h | Domani (pomeriggio) |
| 4. Documentazione | 1h | Domani (sera) |
| **TOTALE** | **~7h** | **1-2 giorni** |

---

## Critica al Mio Approccio Precedente

**Cosa Ho Sbagliato**:
1. ✗ Test su immagini sintetiche (aka "cheat data")
2. ✗ 100% accuracy → conclusione prematura
3. ✗ Nessuna misura di hallucination
4. ✗ Zero variance analysis (LLaVA è stocastico)
5. ✗ Switch immediato senza cross-validation

**Come Correggo**:
1. ✅ Dati reali da `private/campione_validato/`
2. ✅ Cross-validation su 2×split
3. ✅ Misura hallucination esplicitamente
4. ✅ 3 run per scontrino, riporta media±std
5. ✅ Decisione basata su statistiche, non intuizione

---

## Consenso Finale

**Tutti gli agenti concordano**:
- ✅ Validazione su 30-50 dati reali è worth doing
- ✅ Mezza giornata di lavoro, ROI alto
- ⚠️ Ma **non switchare subito** su 50 campioni
- ✅ Primary: Geometric, Fallback: LLaVA (se vince)
- ✅ Cross-validate prima di qualunque decisione production

**GO**: Eseguire Fase 1-4 nel piano corretto

---

**Documento precedente errato**: docs/100_risultati_benchmark_llava.md (scartare, basato su dati fake)  
**Nuovo documento autorizzato**: Questo (docs/101_piano_validazione_llava_corretto.md)

