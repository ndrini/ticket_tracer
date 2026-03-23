import json
import logging
import ollama

logger = logging.getLogger(__name__)

class OllamaProcessor:
    def __init__(self, model_name="llama3.2"):
        self.model_name = model_name

    def process_receipt_text(self, ocr_lines: list) -> dict:
        """
        Prende le linee estratte da PaddleOCR: [ [box, (text, score)], ... ]
        o anche un semplice array di stringhe e le passa all'LLM.
        """
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
        Di seguito troverai il testo grezzo estratto da uno scontrino. Gli scontrini sono principalmente in lingua spagnola o catalana, occasionalmente in italiano.
        Estrai le seguenti informazioni e restituisci SOLO un oggetto JSON anonimo valido (niente markdown o commenti):
        - shop_name: nome del supermercato o negozio principale (es. Ecoveritas, Conad)
        - date: data dello scontrino se presente, in formato YYYY-MM-DD
        - total: l'importo totale espresso come float (es. 12.50)
        - items: una lista di oggetti (array), dove ogni oggetto rappresenta un prodotto e ha:
            - "name": stringa normalizzata e tradotta genericamente in ITALIANO (es. se leggi "Pan" o "Pa" scrivi "Pane", se leggi "Llet" scrivi "Latte").
            - "original_name": stringa esatta originale letta sullo scontrino (es. "Pan", "Llet" o "Farina de blat").
            - "price": float.

        TESTO DELLO SCONTRINO:
        {raw_text}
        """

        try:
            response = ollama.chat(model=self.model_name, messages=[
                {
                    'role': 'user',
                    'content': prompt
                }
            ])
            
            content = response.get('message', {}).get('content', '')
            
            # Pulizia markdown json
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            data = json.loads(content.strip())
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Ollama: {e}")
            return {"shop_name": "Unknown", "date": None, "total": 0.0, "items": []}
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            return {"shop_name": "Unknown", "date": None, "total": 0.0, "items": []}
