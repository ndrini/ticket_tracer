import json
import logging
import re
import ollama

logger = logging.getLogger(__name__)

class OllamaProcessor:
    def __init__(self, model_name="llama3.1:latest"):
        self.model_name = model_name

    def process_receipt_text(self, ocr_lines: list, retry_count: int = 1) -> dict:
        """
        Prende le linee estratte da PaddleOCR: [ [box, (text, score)], ... ]
        o anche un semplice array di stringhe e le passa all'LLM.
        """
        if not ocr_lines:
            return {"shop_name": "Unknown", "date": None, "total": 0.0, "items": []}

        # Estrai solo le stringhe se l'input è nel formato di PaddleOCR
        texts = []
        for line in ocr_lines:
            if isinstance(line, list) and len(line) == 2 and isinstance(line[1], tuple):
                texts.append(line[1][0])
            elif isinstance(line, str):
                texts.append(line)
        
        raw_text = "\n".join(texts)
        
        prompt = f"""
        Sei un assistente specializzato nel leggere gli scontrini. 
        Di seguito troverai il testo estratti da uno scontrino tramite OCR.
        Estrai le seguenti informazioni e restituisci SOLO un oggetto JSON anonimo valido.
        NON aggiungere commenti, spiegazioni o saluti. Solo il JSON.

        - shop_name: nome del supermercato o negozio (es. DIA, Mercadona, Consum)
        - date: data dello scontrino se presente, in formato YYYY-MM-DD
        - total: l'importo totale espresso come float (es. 12.50)
        - items: lista di oggetti con:
            - "name": prodotto tradotto in ITALIANO.
            - "original_name": nome originale esatto.
            - "price": float.

        TESTO OCR:
        {raw_text}
        """

        try:
            response = ollama.chat(model=self.model_name, messages=[
                {
                    'role': 'user',
                    'content': prompt
                }
            ], options={"format": "json"})
            
            content = response.get('message', {}).get('content', '').strip()
            
            if not content or ('{' not in content):
                if retry_count > 0:
                    logger.warning(f"Ollama provided no JSON. Retrying...")
                    return self.process_receipt_text(ocr_lines, retry_count=retry_count-1)
                raise ValueError("Ollama output does not contain JSON structure.")

            # --- Robust JSON Extraction ---
            content = re.sub(r"```json\s*", "", content)
            content = re.sub(r"```\s*", "", content)
            
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx:end_idx+1]
            
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                # --- AUTO-HEALER ---
                content_fixed = re.sub(r"(?<!\w)'(?! \w)", '"', content)
                content_fixed = re.sub(r'(\w+):', r'"\1":', content_fixed)
                data = json.loads(content_fixed)
            
            return data

        except Exception as e:
            logger.error(f"Error calling Ollama/Parsing JSON: {e}")
            if retry_count > 0:
                return self.process_receipt_text(ocr_lines, retry_count=retry_count-1)
            return {"shop_name": "Unknown", "date": None, "total": 0.0, "items": []}


