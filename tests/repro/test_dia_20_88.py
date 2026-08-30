import os
import pytest
from app.etl.etl_engine import ReceiptPipeline
from app.etl.processor import OllamaProcessor

@pytest.mark.integration
def test_dia_20_88_extraction():
    """
    Test di integrazione per lo scontrino DIA 'Boss Level'.
    Verifica che moondream + llama3.1 estraggono correttamente:
    - Totale: 20.88
    - Prodotti: 10+
    - Nome: DIA
    """
    # Usiamo l'immagine archiviata come sorgente del test
    image_path = "data/pictures_archived/2025-02-20 07.57.06.jpg"
    
    if not os.path.exists(image_path):
        pytest.skip(f"Immagine non trovata: {image_path}")

    # Il modello va verificato PRIMA, come l'immagine. Senza, OllamaProcessor
    # cattura l'errore e restituisce {"shop_name": "Unknown", ...}: il test
    # fallisce su "DIA non trovato", che manda a cercare un difetto
    # nell'estrazione invece che un modello mancante.
    modello = "llama3.1:latest"
    try:
        import requests
        disponibili = [m["name"] for m in requests.get(
            "http://localhost:11434/api/tags", timeout=5).json()["models"]]
    except Exception as errore:
        pytest.skip(f"Ollama non raggiungibile: {errore}")
    if modello not in disponibili:
        pytest.skip(f"modello {modello} non installato (ci sono: {disponibili})")

    # 1. Pipeline OCR (Phase 0-1)
    pipeline = ReceiptPipeline()
    receipts_texts, _ = pipeline.extract_raw_ocr(image_path)
    
    # Ci aspettiamo che DIA sia uno dei ricevuti (o l'unico se moondream vede 1 blocco unico)
    assert len(receipts_texts) >= 1
    
    # 2. LLM Analysis (Phase 2)
    processor = OllamaProcessor(model_name=modello)
    
    results = []
    for lines in receipts_texts:
        res = processor.process_receipt_text(lines)
        results.append(res)
    
    # Cerchiamo quello di DIA
    dia_receipt = next((r for r in results if "DIA" in r.get("shop_name", "").upper()), None)
    
    assert dia_receipt is not None, f"DIA non trovato nei risultati: {results}"
    
    print(f"\nRisultati DIA: {dia_receipt}")
    
    # ASSERZIONI RICHIESTE DALL'UTENTE
    actual_total = float(dia_receipt.get("total", 0))
    actual_items = len(dia_receipt.get("items", []))
    
    assert actual_total == 20.88, f"Totale errato: previsto 20.88, ottenuto {actual_total}"
    assert actual_items >= 10, f"Pochi prodotti: previsti 10+, ottenuti {actual_items}"
    assert "DIA" in dia_receipt["shop_name"].upper()
