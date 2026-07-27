#!/usr/bin/env python
"""
Environment check for the extraction pipeline.

Answers one question: can this machine actually run the pipeline right now?
Without it, a missing Ollama model surfaces as a plausible-looking wrong result
(see F3 in private/2026-07-26_PIANO_ESTRAZIONE.md) instead of an error.

Usage:
    uv run python scripts/check_env.py
Exit code 0 if everything needed is present, 1 otherwise.
"""
import sys

# Models the pipeline expects. Keep in sync with the defaults in
# ReceiptPipeline.__init__ and OllamaProcessor.__init__.
REQUIRED_MODELS = {
    "moondream:1.8b": "conteggio scontrini (VLM)",
    "qwen2:1.5b": "normalizzazione del testo (LLM)",
}


def check_ollama_service():
    """Returns (ok, list of installed model names)."""
    try:
        import ollama
    except ImportError:
        print("  MANCA  pacchetto python 'ollama' non installato")
        return False, []

    try:
        response = ollama.list()
    except Exception as e:
        print(f"  MANCA  servizio Ollama non raggiungibile: {e}")
        print("          avvialo con:  ollama serve")
        return False, []

    models = []
    for entry in response.get("models", []):
        name = entry.get("model") or entry.get("name")
        if name:
            models.append(name)

    print(f"  OK      servizio Ollama attivo ({len(models)} modelli installati)")
    return True, models


def check_models(installed):
    """Verify each required model is present. Returns True if all are."""
    all_present = True
    for model, purpose in REQUIRED_MODELS.items():
        # Ollama reports names as "name:tag"; accept an exact or prefix match.
        base = model.split(":")[0]
        if any(m == model or m.split(":")[0] == base for m in installed):
            print(f"  OK      {model} — {purpose}")
        else:
            print(f"  MANCA  {model} — {purpose}")
            print(f"          installalo con:  ollama pull {model}")
            all_present = False
    return all_present


def check_paddleocr():
    try:
        import paddleocr  # noqa: F401
        print("  OK      paddleocr importabile")
        return True
    except Exception as e:
        print(f"  MANCA  paddleocr non importabile: {e}")
        return False


def main():
    print("Verifica ambiente TicketTracer\n")

    print("OCR:")
    ocr_ok = check_paddleocr()

    print("\nOllama:")
    service_ok, installed = check_ollama_service()
    models_ok = check_models(installed) if service_ok else False

    print()
    if ocr_ok and service_ok and models_ok:
        print("Ambiente completo: la pipeline puo' girare.")
        return 0

    print("Ambiente INCOMPLETO.")
    if not models_ok and service_ok:
        print("Senza modelli, normalizzazione e conteggio VLM non funzionano:")
        print("la pipeline restituirebbe risultati plausibili ma vuoti.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
