import pytest
from unittest.mock import patch
from app.etl.processor import OllamaProcessor

def test_process_receipt_text_success():
    processor = OllamaProcessor(model_name="dummy_model")
    
    ocr_lines = [
        "ECOVERITAS",
        "P.IVA 1234567890",
        "Farina di grano tenero  1.50",
        "Latte parz. scremato    1.20",
        "TOTALE             2.70"
    ]
    
    # Mocking ollama.chat to return a predefined JSON string
    mock_json = '{"shop_name": "Ecoveritas", "date": "2023-11-20", "total": 2.70, "items": [{"name": "Farina di grano tenero", "price": 1.50}, {"name": "Latte parz. scremato", "price": 1.20}]}'
    
    with patch("app.etl.processor.ollama.chat") as mock_chat:
        mock_chat.return_value = {
            "message": {
                "content": mock_json
            }
        }
        
        result = processor.process_receipt_text(ocr_lines)
        
        assert result["shop_name"] == "Ecoveritas"
        assert result["date"] == "2023-11-20"
        assert result["total"] == 2.70
        assert len(result["items"]) == 2
        assert result["items"][0]["name"] == "Farina di grano tenero"
        assert result["items"][0]["price"] == 1.50

def test_process_receipt_text_failure_fallback():
    processor = OllamaProcessor(model_name="dummy_model")
    
    with patch("app.etl.processor.ollama.chat") as mock_chat:
        # Invalid JSON
        mock_chat.return_value = {
            "message": {
                "content": "Not a JSON"
            }
        }
        
        result = processor.process_receipt_text(["test"])
        
        assert result["shop_name"] == "Unknown"
        assert result["total"] == 0.0
        assert result["items"] == []
