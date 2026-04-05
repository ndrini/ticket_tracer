import json
import logging
import re
import ollama

logger = logging.getLogger(__name__)

class OllamaProcessor:
    def __init__(self, model_name="qwen2:1.5b"):
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
            
            # --- Robust JSON Extraction ---
            # Cerchiamo il blocco JSON più grande o il primo blocco completo
            # Usiamo una ricerca non greed per il primo blocco se possibile, 
            # o cerchiamo di pulire l'output.
            
            # Rimuoviamo eventuali tag markdown ```json ... ```
            content = re.sub(r"```json\s*", "", content)
            content = re.sub(r"```\s*", "", content)
            
            # Cerchiamo il primo '{' e l'ultimo '}'
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx:end_idx+1]
            
            # Pulizia ulteriore per evitare "Extra data" se l'LLM ha scritto altro dopo l'ultima parentesi
            content = content.strip()
            
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                # Se fallisce, proviamo a estrarre solo il primo oggetto valido
                # Questo è un approccio più "brute force" per bilanciare le parentesi
                bracket_count = 0
                for i, char in enumerate(content):
                    if char == '{':
                        bracket_count += 1
                    elif char == '}':
                        bracket_count -= 1
                        if bracket_count == 0:
                            content = content[:i+1]
                            break
                
                # --- AUTO-HEALER (per case con single quotes o chiavi non quotate) ---
                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    # Prova a sostituire ' con " (rischioso se nel testo ci sono apostrofi, ma meglio di nulla)
                    # Solo se non è già circondato da lettere
                    content_fixed = re.sub(r"(?<!\w)'(?! \w)", '"', content)
                    # Prova a mettere virgolette alle chiavi non quotate (es. shop_name: -> "shop_name":)
                    content_fixed = re.sub(r'(\w+):', r'"\1":', content_fixed)
                    try:
                        data = json.loads(content_fixed)
                    except:
                        raise # Rilancia per il catch esterno
            
            return data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Ollama: {content[:200]}... Error: {e}")
            return {"shop_name": "Unknown", "date": None, "total": 0.0, "items": []}
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            return {"shop_name": "Unknown", "date": None, "total": 0.0, "items": []}

