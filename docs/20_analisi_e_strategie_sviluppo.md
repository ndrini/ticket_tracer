# Analisi di Stato e Strategie di Sviluppo - Ticket Tracer

Questo documento analizza le prestazioni attuali del sistema di estrazione dati dagli scontrini e propone due percorsi alternativi per superare i limiti riscontrati.

## 1. Analisi dello Stato Attuale

Dai test eseguiti su un set di oltre 90 immagini archiviate, emerge che il sistema attuale cattura solo una minima parte dei dati reali (~174€ su centinaia di prodotti potenziali).

### Punti di Debolezza Identificati:
*   **Segmentazione (OpenCV):** L'algoritmo basato su contorni classici (Canny/Contours) fatica a isolare correttamente gli scontrini se lo sfondo non è uniforme o se gli scontrini sono sovrapposti/stropicciati.
*   **Gestione Multilingua:** Sebbene PaddleOCR sia impostato su `lang="es"`, l'assenza di un vocabolario specialistico porta a errori di lettura su termini catalani o italiani meno comuni.
*   **Ricostruzione Spaziale:** L'OCR restituisce il testo in un flusso disordinato. Senza raggruppamento per righe (clustering Y), l'associazione "Prodotto <-> Prezzo" viene persa prima ancora di arrivare all'LLM.
*   **Capacità dell'LLM:** Il modello `qwen2:1.5b` non ha una finestra di contesto sufficientemente "intelligente" per pulire il rumore dell'OCR e tradurre simultaneamente i prodotti in italiano mantenendo la coerenza.

---

## 2. Strategia A: Approccio "Vision-First" (Multimodale)

Questa strategia elimina la necessità di una pipeline complessa di pre-processing e OCR, delegando l'intelligenza visiva a un modello superiore.

### Funzionamento:
Invece di: `Immagine -> OCR -> Testo -> LLM`, si segue il flusso: `Immagine -> Multimodal LLM -> JSON`.

### Pro e Contro:
*   **PRO:**
    *   **Comprensione del Layout:** Il modello "vede" lo scontrino e capisce la relazione spaziale tra nome e prezzo senza algoritmi di clustering.
    *   **Robustezza:** Gestisce ombre, pieghe e testi ruotati molto meglio di un OCR standard.
    *   **Scalabilità Multilingua:** Modelli come GPT-4o o Claude 3.5 hanno capacità di traduzione integrate eccellenti.
*   **CONTRO:**
    *   **Costi/Hardware:** Richiede API a pagamento (OpenAI/Anthropic) o una GPU locale di fascia alta (12GB+ VRAM) per modelli come Llava o Qwen2-VL.

---

## 3. Strategia B: Pipeline "Deep Engineering" (YOLO + Specialist OCR)

Questa strategia mantiene l'approccio modulare attuale ma potenzia drasticamente ogni singolo componente.

### Funzionamento:
1.  **Detezione (YOLOv8/10):** Un modello YOLO addestrato specificamente per rilevare "oggetti scontrino". Restituisce ritagli puliti di ogni singolo scontrino nella foto.
2.  **Specialist OCR (Cloud Vision o PaddleX):** Uso di motori OCR avanzati che restituiscono non solo il testo, ma la struttura a tabelle (Table Recognition).
3.  **Parsing (LLM 7B/8B):** Uso di modelli più grandi (es. Llama 3 8B o Mistral) per la conversione finale in JSON.

### Pro e Contro:
*   **PRO:**
    *   **Controllo Totale:** Puoi debuggare esattamente dove la pipeline fallisce (se è la detezione o l'OCR).
    *   **Costo Esercizio:** Una volta addestrato, YOLO è estremamente leggero e può girare su quasi ogni hardware.
*   **CONTRO:**
    *   **Sviluppo:** Richiede la creazione di un dataset etichettato (labeling) per addestrare YOLO.
    *   **Complessità:** Molte parti mobili che devono essere coordinate.

---

## 4. Raccomandazioni e Prossimi Passi

1.  **Test Comparativo:** Eseguire lo stesso scontrino (quello con più errori) tramite un modello Multimodale (es. GPT-4o o Llava) per stabilire il "limite superiore" di precisione ottenibile.
2.  **Salvataggio Ritagli:** Modificare l'attuale logica per salvare fisicamente i ritagli (`cropped_images`) in una cartella `data/debug_crops/`. Questo permetterà di verificare se il problema è la detezione o l'OCR.
3.  **Potenziamento Prompt:** Rivedere il prompt dell'LLM per includere esempi "Few-Shot" di traduzione Catalano->Italiano.
