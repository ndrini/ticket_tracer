"""Lavori lunghi lanciati da una pagina web, senza bloccarla.

L'ingestione costa ~2 minuti a fotografia: dentro una richiesta HTTP il browser
resterebbe appeso e poi rinuncerebbe. Qui il lavoro parte in un processo a
parte, la pagina chiede lo stato quando vuole, e la riga di comando resta
disponibile per chi la preferisce — gli script non vengono duplicati, si
invocano.

UN LAVORO PER VOLTA, di proposito: due ingestioni insieme si contendono gli
stessi otto thread di questa macchina senza GPU, e ci mettono piu' del doppio.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent


@dataclass
class Lavoro:
    """Un comando in corso o finito, con cio' che ha scritto finora."""
    nome: str
    comando: list[str]
    righe: list[str] = field(default_factory=list)
    stato: str = "in_corso"          # in_corso | finito | fallito
    codice: int | None = None
    iniziato: float = field(default_factory=time.time)

    def come_dizionario(self):
        return {
            "nome": self.nome,
            "stato": self.stato,
            "codice": self.codice,
            "secondi": round(time.time() - self.iniziato),
            # Le ultime righe bastano: l'avanzamento e' in coda, non in testa.
            "righe": self.righe[-40:],
        }


class Lavori:
    """Il lavoro in corso, se c'e'."""

    def __init__(self):
        self._corrente: Lavoro | None = None
        self._lucchetto = threading.Lock()

    @property
    def corrente(self):
        return self._corrente

    def in_corso(self) -> bool:
        return self._corrente is not None and self._corrente.stato == "in_corso"

    def avvia(self, nome: str, argomenti: list[str]) -> tuple[bool, str]:
        """(avviato, messaggio). Rifiuta se ce n'e' gia' uno in corso."""
        with self._lucchetto:
            if self.in_corso():
                return False, f"gia' in corso: {self._corrente.nome}"

            comando = [sys.executable] + argomenti
            lavoro = Lavoro(nome=nome, comando=comando)
            self._corrente = lavoro

        threading.Thread(target=self._esegui, args=(lavoro,), daemon=True).start()
        return True, "avviato"

    def _esegui(self, lavoro: Lavoro):
        try:
            processo = subprocess.Popen(
                lavoro.comando, cwd=str(RADICE),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
                # Python bufferizza l'output quando non scrive su un terminale,
                # e l'avanzamento arriverebbe tutto insieme alla fine.
                env={**__import__("os").environ, "PYTHONUNBUFFERED": "1"})
            for riga in processo.stdout:
                riga = riga.rstrip()
                if riga and not riga.startswith(("Warning", "  warnings.warn")):
                    lavoro.righe.append(riga)
            processo.wait()
            lavoro.codice = processo.returncode
            lavoro.stato = "finito" if processo.returncode == 0 else "fallito"
        except Exception as e:
            lavoro.righe.append(f"errore: {e}")
            lavoro.stato = "fallito"
            lavoro.codice = -1


def cartelle_candidate(radice: Path = None):
    """Cartelle di foto sotto data/, con quante immagini contengono.

    Solo sotto data/: l'archivio rifiuta per progetto le chiavi fuori dalla
    propria radice, e i symlink non servono a aggirarlo (rglob non li
    attraversa, verificato).
    """
    radice = radice or (RADICE / "data")
    estensioni = (".jpg", ".jpeg", ".png", ".webp")
    salta = {"ritagli", "estratti", "miniature", "strutturati",
             "strutturati_geometrici", "kaggle_ritagli", "kaggle_output",
             "cache_ocr", "cache_oriented", "cache_revisione_orientate",
             "cache_ocr_archived", "cache_oriented_test10", "db"}

    trovate = []
    for cartella in sorted(radice.iterdir()):
        if not cartella.is_dir() or cartella.name in salta:
            continue
        n = sum(1 for f in cartella.iterdir()
                if f.is_file() and f.suffix.lower() in estensioni)
        if n:
            trovate.append({"nome": cartella.name, "immagini": n})
    return trovate
