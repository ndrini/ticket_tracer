import os
import glob
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
import cv2


# Limita il numero di thread usati dalle librerie C/C++ sottostanti (Numpy, OpenCV, Paddle)
# per evitare di saturare tutte le CPU e bloccare il computer. (Uso: 3 thread)
os.environ["OMP_NUM_THREADS"] = "3"
os.environ["OPENBLAS_NUM_THREADS"] = "3"
os.environ["MKL_NUM_THREADS"] = "3"
os.environ["VECLIB_MAXIMUM_THREADS"] = "3"
os.environ["NUMEXPR_NUM_THREADS"] = "3"

# Configurazione percorsi
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"

INPUT_DIR = DATA_DIR / "pictures_input"
CROPPED_DIR = DATA_DIR / "receipts_input"
OCR_CACHE_DIR = DATA_DIR / "cache_ocr"
ARCHIVED_IMG_DIR = DATA_DIR / "pictures_archived"
ARCHIVED_OCR_DIR = DATA_DIR / "cache_ocr_archived"

DB_DIR = DATA_DIR / "db"
DB_PATH = DB_DIR / "produzione.db"

# Crea le cartelle se non esistono
for d in [INPUT_DIR, CROPPED_DIR, OCR_CACHE_DIR, ARCHIVED_IMG_DIR, ARCHIVED_OCR_DIR, DB_DIR]:
    os.makedirs(d, exist_ok=True)


try:
    from app.etl.etl_engine import ReceiptPipeline
    from app.etl.processor import OllamaProcessor
    from app.db.inserter import insert_receipt_data
    from app.db.db_manager import init_db
except ImportError as e:
    print(f"Errore di importazione moduli (sicuro di lavorare dalla cartella radice del progetto?): {e}")
    exit(1)


def step_1_run_ocr():
    """Fase 1: Legge immagini, esegue l'OCR e salva i risultati grezzi in cache."""
    print("--- INIZIO FASE 1: Estrazione Testo (OCR) ---")
    image_files = []
    for ext in ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"]:
        image_files.extend(glob.glob(str(INPUT_DIR / ext)))

    if not image_files:
        print(f"Nessun nuovo scontrino trovato in {INPUT_DIR.name}/.")
        return

    print(f"Trovati {len(image_files)} scontrini. Inizializzazione PaddleOCR...")
    pipeline = ReceiptPipeline()

    for img_path in image_files:
        filename = os.path.basename(img_path)
        print(f"Elaborazione OCR per {filename}...")
        try:
            # Estraziamo il testo raw e le immagini ritagliate
            raw_data, cropped_images = pipeline.extract_raw_ocr(img_path)
            
            base_name = os.path.splitext(filename)[0]
            
            # Salvataggio ritagli fisici per debug/ispezione
            for i, crop in enumerate(cropped_images):
                crop_filename = f"{base_name}_crop_{i}.jpg"
                cv2.imwrite(str(CROPPED_DIR / crop_filename), crop)
            
            # Salvataggio nella cartella di cache come JSON
            base_name = os.path.splitext(filename)[0]
            cache_file = OCR_CACHE_DIR / f"{base_name}.json"
            
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(raw_data, f, ensure_ascii=False, indent=2)
                
            # Archiviazione immagine
            shutil.move(img_path, ARCHIVED_IMG_DIR / filename)
            print(f"✓ Cache OCR salvata in {cache_file.name}. Immagine archiviata.")
            
            # Pausa per limitare il carico sulla CPU
            time.sleep(2)
            
        except Exception as e:
            print(f"❌ Errore durante l'OCR di {filename}: {e}")


def step_2_run_llm_and_db():
    """Fase 2: Legge i file OCR salvati, interroga Ollama e salva sul database."""
    print("\n--- INIZIO FASE 2: Analisi Intelligente (LLM) & Inserimento DB ---")
    json_files = glob.glob(str(OCR_CACHE_DIR / "*.json"))
    
    if not json_files:
        print(f"Nessun file OCR trovato in {OCR_CACHE_DIR.name}/ da processare.")
        return

    print(f"Trovati {len(json_files)} file OCR in cache. Controllo Database...")
    
    # Inizializza il DB se non esiste ancora
    if not os.path.exists(DB_PATH):
        init_db(str(DB_PATH))
        print(f"Database {DB_PATH.name} creato/inizializzato.")
        
    print("Inizializzazione Ollama (Llama 3.1 8B)...")
    processor = OllamaProcessor()

    for json_file in json_files:
        filename = os.path.basename(json_file)
        print(f"Analisi LLM per i dati da {filename}...")
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                ocr_data = json.load(f)
            
            # ocr_data contiene una lista, un elemento per ogni scontrino trovato nell'immagine
            for index, receipt_ocr_lines in enumerate(ocr_data):
                if not receipt_ocr_lines:
                    print(f"Avviso: Scontrino {index+1} senza testo in {filename}.")
                    continue
                
                # Chiamata all'LLM locale
                structured_data = processor.process_receipt_text(receipt_ocr_lines)
                
                if structured_data and "items" in structured_data:
                    # Inserimento nel database SQLite
                    insert_receipt_data(str(DB_PATH), structured_data, image_blob=None)
                    
                    shop_name = structured_data.get('shop_name', 'Sconosciuto')
                    total = structured_data.get('total', 0.0)
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[{now_str}] ✓ Inserito nel DB: {shop_name} - Totale: {total}€ ({len(structured_data['items'])} prodotti)")
                else:
                    print(f"⚠️ LLM non ha restituito dati validi per {filename} (Scontrino {index+1}).")
                    
                # Pausa tra scontrini multipli
                time.sleep(1)

            # A fine elaborazione di tutti gli scontrini del file OCR, archiviamo il JSON
            shutil.move(json_file, ARCHIVED_OCR_DIR / filename)
            
            # Pausa per limitare il carico sul sistema
            time.sleep(2)
            
        except Exception as e:
            print(f"❌ Errore durante l'analisi LLM di {filename}: {e}")

if __name__ == "__main__":
    print("====================================")
    print("  Ticket Tracer Pipeline Avviata")
    print("====================================\n")
    
    step_1_run_ocr()
    step_2_run_llm_and_db()
    
    print("\n✅ Pipeline completata.")
