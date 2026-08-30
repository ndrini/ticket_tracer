"""Rivedi gli scontrini piu' problematici, non un campione a caso.

    uv run python scripts/revisione_umana.py --chi aless@ndrini.eu

Poi si apre http://localhost:8098 — tutto in locale, niente esce da qui.

## Cosa si vede

Quattro riquadri affiancati: la FOTO D'ORIGINE (per capire se il ritaglio ha
tagliato via qualcosa), il RITAGLIO, le RIGHE ESTRATTE e la CONFIDENZA.

Quando la foto ha prodotto piu' ritagli, sopra il ritaglio compaiono delle
schede, una per scontrino: le frecce sinistra/destra le scorrono. Guardarle non
sposta il giudizio, che resta sullo scontrino in cima (quello con la freccia).
La coda li tiene consecutivi, cosi' Invio passa al fratello successivo e non a
un'altra foto - vedi app/revisione/coda.py.

## Cosa si risponde

Due domande separate: il taglio e' buono? i dati sono giusti? Sono indipendenti
perche' un ritaglio sbagliato rende inutile la domanda sui dati - infatti chi
risponde "taglio sbagliato" puo' passare oltre senza giudicare i numeri.

## Cosa NON fa

Non corregge. Registra un giudizio in `manual_review_queue`. Segnalare, non
correggere d'ufficio: le correzioni si decideranno guardando i giudizi raccolti.

## L'ordine della coda nasce da una misura

Sui 306 scontrini: 104 hanno zero o una riga (sospetto ritaglio), 52 non
quadrano (sospetto estrazione), 65 non hanno totale (non verificabili), 85 sono
validi e pieni e non si guardano. Vedi app/revisione/coda.py.
"""
import argparse
import http.server
import json
import mimetypes
import pathlib
import socketserver
import threading
import sqlite3
import sys
import urllib.parse
import webbrowser

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.revisione.coda import costruisci_coda  # noqa: E402
from app.revisione.dati import (  # noqa: E402
    costruisci_scheda, mappa_foto, registra_giudizio)
from app.storage import costruisci_archivio  # noqa: E402

RADICE = pathlib.Path(__file__).resolve().parent.parent

# Folders a photo may come from, newest batch first. Keys inside the archive,
# not paths: on S3 they become key prefixes.
CARTELLE_FOTO = ("2026_scontrini", "2025_scontrini", "pictures_archived")
PREFISSO_ORIENTATE = "cache_revisione_orientate/"

PAGINA = """<!doctype html>
<meta charset="utf-8"><title>Revisione scontrini</title>
<style>
 :root{--bg:#f6f6f4;--carta:#fff;--bordo:#dcdcd6;--ombra:0 1px 3px rgba(0,0,0,.09);
       --testo:#222;--tenue:#6b6b66;--ok:#2e7d32;--no:#c62828;--attenzione:#b26a00}
 .tab{display:flex;flex-wrap:wrap;gap:4px;padding:8px 10px 0}
 .tab .scheda{font:inherit;font-size:12px;padding:3px 9px;border-radius:6px;
   border:1px solid var(--bordo);background:#fafaf8;color:var(--tenue);cursor:pointer}
 .tab .scheda:hover{background:#f0f0ec}
 .tab .attiva{background:var(--carta);color:var(--testo);border-color:#9a9a92;font-weight:600}
 .tab .giudicando{box-shadow:inset 0 -2px 0 var(--attenzione)}
 .tab .fatto{color:var(--ok)}
 *{box-sizing:border-box}
 body{margin:0;font:14px/1.5 system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--testo)}
 header{display:flex;align-items:baseline;gap:16px;padding:10px 16px;
        background:var(--carta);border-bottom:1px solid var(--bordo);position:sticky;top:0;z-index:5}
 h1{font-size:15px;margin:0;font-weight:600}
 .avanzamento{color:var(--tenue)}
 .etichetta{padding:2px 8px;border-radius:99px;font-size:12px;font-weight:600}
 .taglio{background:#fdecea;color:var(--no)}
 .estrazione{background:#fff4e0;color:var(--attenzione)}
 .non_verificabile{background:#eceff1;color:var(--tenue)}
 main{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;padding:12px;align-items:start}
 .riquadro{background:var(--carta);border:1px solid var(--bordo);border-radius:8px;
           box-shadow:var(--ombra);overflow:hidden}
 .riquadro h2{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--tenue);
              margin:0;padding:8px 12px;border-bottom:1px solid var(--bordo);font-weight:600}
 .riquadro .corpo{padding:12px}
 img{width:100%;display:block;background:#e8e8e4;cursor:zoom-in}
 img.zoom{position:fixed;inset:0;width:100vw;height:100vh;object-fit:contain;
          background:rgba(0,0,0,.92);z-index:50;cursor:zoom-out;padding:16px}
 table{width:100%;border-collapse:collapse}
 td{padding:3px 0;vertical-align:top}
 td.prezzo{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;padding-left:8px}
 .vuoto{color:var(--no);font-style:italic}
 dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:4px 10px}
 dt{color:var(--tenue)}
 dd{margin:0;text-align:right;font-variant-numeric:tabular-nums}
 .barra{height:6px;background:#e8e8e4;border-radius:3px;overflow:hidden;margin-top:2px}
 .barra i{display:block;height:100%;background:var(--ok)}
 footer{position:sticky;bottom:0;background:var(--carta);border-top:1px solid var(--bordo);
         padding:10px 16px;display:flex;gap:22px;align-items:center;flex-wrap:wrap}
 fieldset{border:0;margin:0;padding:0;display:flex;gap:8px;align-items:center}
 legend{float:left;margin-right:8px;color:var(--tenue);font-size:13px}
 button{font:inherit;padding:7px 13px;border-radius:6px;border:1px solid var(--bordo);
        background:var(--carta);cursor:pointer}
 button:hover{border-color:#999}
 button.si{border-color:var(--ok);color:var(--ok)} button.si.scelto{background:var(--ok);color:#fff}
 button.no{border-color:var(--no);color:var(--no)} button.no.scelto{background:var(--no);color:#fff}
 kbd{font:11px monospace;background:#eee;border:1px solid var(--bordo);border-radius:3px;padding:0 4px}
 input[type=text]{font:inherit;padding:7px;border:1px solid var(--bordo);border-radius:6px;flex:1;min-width:180px}
 .avanti{margin-left:auto;background:#1a1a1a;color:#fff;border-color:#1a1a1a;padding:7px 18px}
 .finito{text-align:center;padding:70px 20px;color:var(--tenue)}
</style>
<body>
<div id="app"></div>
<script>
let S = null, taglio = null, dati = null;

async function carica(pos){
  const r = await fetch('/scheda?pos=' + (pos===undefined?'':pos));
  S = await r.json(); taglio = null; dati = null; disegna();
}
function euro(v){ return v===null||v===undefined ? '—' : v.toFixed(2)+' €'; }

// Look at a sibling crop WITHOUT changing the verdict target. The judgement
// always belongs to S.receipt_id: peeking at the neighbour must not silently
// move it, or one would score the wrong receipt.
//
// Swaps the image and the tab classes in place instead of calling disegna():
// a full redraw rebuilds the <input>, throwing away a note half typed.
function guarda(sha){
  S.mostra_sha = sha;
  const img = document.querySelector('#ritaglio img');
  if(img) img.src = '/ritaglio/' + sha;
  document.querySelectorAll('#ritaglio .tab .scheda').forEach((b, i) => {
    b.classList.toggle('attiva', S.fratelli[i].sha256 === sha);
  });
}

function disegna(){
  const a = document.getElementById('app');
  if(S.finito){
    a.innerHTML = '<div class="finito"><h1>Coda finita.</h1><p>'+S.giudicati+
                  ' scontrini giudicati.</p></div>';
    return;
  }
  const righe = S.righe.length
    ? '<table>'+S.righe.map(r=>'<tr><td>'+r.nome+'</td><td class="prezzo">'+
        euro(r.prezzo)+'</td></tr>').join('')+'</table>'
    : '<p class="vuoto">Nessuna riga estratta.</p>';
  const conf = Math.round((S.confidenza||0)*100);

  // Tabs only when the photo yielded more than one crop. The current receipt is
  // always a tab, so the strip shows which piece of paper you are judging.
  const tab = (S.fratelli && S.fratelli.length > 1)
    ? '<div class="tab">' + S.fratelli.map((f, i) => {
        const attivo = (S.mostra_sha || S.sha256) === f.sha256;
        const cl = ['scheda', attivo ? 'attiva' : '',
                    f.corrente ? 'giudicando' : '',
                    f.giudicato ? 'fatto' : ''].filter(Boolean).join(' ');
        const eti = f.negozio || ('#' + f.receipt_id);
        return `<button class="${cl}" onclick="guarda('${f.sha256}')" `
             + `title="#${f.receipt_id} ${f.stato||''}">${i + 1}. ${eti}`
             + (f.corrente ? ' \u25c0' : '') + (f.giudicato ? ' \u2713' : '')
             + '</button>';
      }).join('') + '</div>'
    : '';

  a.innerHTML = `
   <header>
     <h1>#${S.receipt_id}</h1>
     <span class="etichetta ${S.sospetto}">${S.motivo}</span>
     <span class="avanzamento">${S.posizione} di ${S.totale_coda}</span>
   </header>
   <main>
     <div class="riquadro"><h2>Foto d'origine</h2>
       ${S.foto_origine ? '<img src="/foto/'+encodeURIComponent(S.foto_origine)+'">'
                        : '<div class="corpo vuoto">Foto non trovata.</div>'}</div>
     <div class="riquadro" id="ritaglio"><h2>Ritaglio</h2>
       ${tab}
       <img src="/ritaglio/${S.mostra_sha || S.sha256}"></div>
     <div>
       <div class="riquadro" style="margin-bottom:12px"><h2>Righe estratte</h2>
         <div class="corpo">${righe}</div></div>
       <div class="riquadro"><h2>Estrazione</h2><div class="corpo"><dl>
         <dt>negozio</dt><dd>${S.negozio||'—'}</dd>
         <dt>data</dt><dd>${S.data||'—'}</dd>
         <dt>totale stampato</dt><dd>${euro(S.totale_dichiarato)}</dd>
         <dt>somma righe</dt><dd>${euro(S.totale_calcolato)}</dd>
         <dt>scarto</dt><dd>${euro(S.delta)}</dd>
         <dt>stato</dt><dd>${S.stato||'—'}</dd>
         <dt>confidenza</dt><dd>${conf}%<div class="barra"><i style="width:${conf}%"></i></div></dd>
       </dl></div></div>
     </div>
   </main>
   <footer>
     <fieldset><legend>Taglio</legend>
       <button class="si" id="t1" onclick="segna('taglio',true)">buono <kbd>1</kbd></button>
       <button class="no" id="t0" onclick="segna('taglio',false)">sbagliato <kbd>2</kbd></button>
     </fieldset>
     <fieldset><legend>Dati</legend>
       <button class="si" id="d1" onclick="segna('dati',true)">giusti <kbd>3</kbd></button>
       <button class="no" id="d0" onclick="segna('dati',false)">sbagliati <kbd>4</kbd></button>
     </fieldset>
     <input type="text" id="nota" placeholder="nota (facoltativa)">
     <button class="avanti" onclick="salva()">Salva e avanti <kbd>invio</kbd></button>
   </footer>`;

  document.querySelectorAll('img').forEach(i =>
    i.onclick = () => i.classList.toggle('zoom'));
}

function segna(quale, valore){
  if(quale==='taglio') taglio = (taglio===valore ? null : valore);
  else                 dati   = (dati===valore   ? null : valore);
  for(const [id,v] of [['t1',taglio===true],['t0',taglio===false],
                       ['d1',dati===true],['d0',dati===false]]){
    const b=document.getElementById(id); if(b) b.classList.toggle('scelto', v);
  }
}

async function salva(){
  if(taglio===null && dati===null){ alert('Dai almeno un giudizio.'); return; }
  // Enter held down, or pressed again while the POST is in flight, would judge
  // the next receipt with the previous one's answers.
  if(salvando) return;
  salvando = true;
  try{
    await fetch('/giudica', {method:'POST', body: JSON.stringify({
      receipt_id:S.receipt_id, taglio_ok:taglio, dati_ok:dati,
      nota:(document.getElementById('nota')||{}).value || ''})});
    await carica();
  } finally { salvando = false; }
}

let salvando = false;

document.addEventListener('keydown', e => {
  // Typing in the note must not trigger the 1-4 shortcuts, but Enter still
  // saves: reaching for the mouse after every note would slow the review down.
  if(e.target.tagName === 'INPUT' && e.key !== 'Enter') return;
  if(e.key === 'Enter') e.preventDefault();
  if(e.key==='1') segna('taglio',true);
  else if(e.key==='2') segna('taglio',false);
  else if(e.key==='3') segna('dati',true);
  else if(e.key==='4') segna('dati',false);
  else if(e.key==='Enter') salva();
  else if((e.key==='ArrowLeft'||e.key==='ArrowRight') && S && S.fratelli && S.fratelli.length>1){
    const n = S.fratelli.length;
    const i = S.fratelli.findIndex(f => f.sha256 === (S.mostra_sha||S.sha256));
    const j = (i + (e.key==='ArrowRight' ? 1 : n-1)) % n;
    guarda(S.fratelli[j].sha256); e.preventDefault();
  }
});
carica();
</script>
"""


class Sessione:
    """The queue, rebuilt from the DB so an interrupted session resumes."""

    def __init__(self, db, chi, sospetto=None):
        self.db = db
        self.chi = chi
        self.sospetto = sospetto
        self.conn = sqlite3.connect(db, check_same_thread=False)
        self.archivio = costruisci_archivio()
        self.giudicati = 0
        self._pipeline = None  # built on first orientation, not at startup
        self._pipeline_lock = threading.Lock()
        self._in_corso = set()
        self._in_corso_lock = threading.Lock()
        self.ricalcola()

    def ricalcola(self):
        # One registry read per rebuild, shared by the queue (to keep siblings
        # together) and by each card (to list them).
        self.mappa = mappa_foto()
        self.coda = costruisci_coda(self.conn, mappa_foto=self.mappa)
        if self.sospetto:
            self.coda = [v for v in self.coda if v.sospetto.value == self.sospetto]

    def scheda(self, pos=0):
        self.ricalcola()
        if not self.coda or pos >= len(self.coda):
            return {"finito": True, "giudicati": self.giudicati}
        voce = self.coda[pos]
        self.prepara_foto(pos)
        s = costruisci_scheda(self.conn, voce, pos + 1, len(self.coda), self.mappa)
        return {
            "finito": False, "receipt_id": s.receipt_id, "sha256": s.sha256,
            "sospetto": s.sospetto, "motivo": s.motivo, "stato": s.stato,
            "delta": s.delta, "confidenza": s.confidenza, "negozio": s.negozio,
            "data": s.data, "totale_dichiarato": s.totale_dichiarato,
            "totale_calcolato": s.totale_calcolato,
            "righe": [{"nome": r.nome, "prezzo": r.prezzo} for r in s.righe],
            "foto_origine": s.foto_origine,
            "fratelli": [{"receipt_id": f.receipt_id, "sha256": f.sha256,
                          "negozio": f.negozio, "stato": f.stato,
                          "giudicato": f.giudicato, "corrente": f.corrente}
                         for f in s.fratelli],
            "posizione": s.posizione, "totale_coda": s.totale_coda,
        }

    def giudica(self, dati):
        registra_giudizio(self.conn, dati["receipt_id"], dati.get("taglio_ok"),
                          dati.get("dati_ok"), dati.get("nota"), self.chi)
        self.giudicati += 1

    def trova_foto(self, nome):
        """Where this photo lives. Photos arrive in one folder per batch."""
        for cartella in CARTELLE_FOTO:
            chiave = f"{cartella}/{nome}"
            if self.archivio.esiste(chiave):
                return chiave
        return None

    def orienta(self, chiave, attendi=False):
        """Key of the photo turned the way a human reads it, cached on disk.

        Returns the raw key immediately when the turned copy is not ready yet:
        the first orientation has to load PaddleOCR, tens of seconds during
        which the browser would simply give up and show no photo at all. A
        sideways photo beats a missing one, and the next card gets the turned
        version.

        The pipeline already rotates every photo before segmenting it (see
        ReceiptPipeline._orient_whole_image, a trained classifier checked over
        96 real photos), but it does that in memory and keeps only the crops.
        So the review screen was showing the raw photo, often sideways, next to
        an upright crop - and judging whether a crop cut something off is
        harder when the two are not the same way up.

        Done on demand rather than for every photo at ingestion: only the ones
        actually reviewed cost anything, and the cost is paid once.
        """
        nome = chiave.rsplit("/", 1)[-1]
        cache = f"{PREFISSO_ORIENTATE}{nome}"
        if self.archivio.esiste(cache):
            return cache

        if not attendi:
            # Turn it in the background and serve the raw one meanwhile.
            with self._in_corso_lock:
                if nome not in self._in_corso:
                    self._in_corso.add(nome)
                    threading.Thread(target=self._orienta_e_libera,
                                     args=(chiave, nome), daemon=True).start()
            return chiave

        try:
            import cv2
            import numpy as np

            dati = self.archivio.leggi(chiave)
            img = cv2.imdecode(np.frombuffer(dati, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return chiave
            with self._pipeline_lock:
                if self._pipeline is None:
                    from app.etl.etl_engine import ReceiptPipeline
                    self._pipeline = ReceiptPipeline()
                # The classifier is not thread-safe, and two cards can ask at
                # once: serialise the model, not the whole request.
                girata = self._pipeline._orient_whole_image(img)
            ok, buf = cv2.imencode(".jpg", girata, [cv2.IMWRITE_JPEG_QUALITY, 88])
            if not ok:
                return chiave
            self.archivio.scrivi(cache, buf.tobytes())
            return cache
        except Exception as e:
            # Showing the photo the wrong way up beats showing no photo.
            print(f"  orientamento fallito per {nome}: {e}")
            return chiave

    def _orienta_e_libera(self, chiave, nome):
        try:
            self.orienta(chiave, attendi=True)
        finally:
            with self._in_corso_lock:
                self._in_corso.discard(nome)

    def prepara_foto(self, pos):
        """Turn the photos of the next few cards before they are asked for.

        Reviewing is a steady march down the queue, so what comes next is known.
        Without this every new photo shows up raw the first time and turned only
        on the way back.
        """
        viste = set()
        for v in self.coda[pos:pos + 4]:
            foto = self.mappa.get(v.sha256)
            if not foto or foto in viste:
                continue
            viste.add(foto)
            chiave = self.trova_foto(foto)
            if chiave:
                self.orienta(chiave)


def servi(sessione, porta):
    class Gestore(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass  # keep the console readable

        def _manda(self, corpo, tipo="application/json", codice=200):
            if isinstance(corpo, str):
                corpo = corpo.encode("utf-8")
            self.send_response(codice)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def _immagine(self, chiave, ripiego=None):
            """Serve an image through the archive, so this works on S3 too."""
            for tentativo in [chiave] + ([ripiego] if ripiego else []):
                try:
                    dati = sessione.archivio.leggi(tentativo)
                except Exception:
                    continue
                tipo = mimetypes.guess_type(tentativo)[0] or "image/jpeg"
                return self._manda(dati, tipo)
            self._manda(b"", "image/jpeg", 404)

        def do_GET(self):
            p = urllib.parse.urlparse(self.path)
            if p.path == "/":
                return self._manda(PAGINA, "text/html; charset=utf-8")
            if p.path == "/scheda":
                q = urllib.parse.parse_qs(p.query)
                pos = int((q.get("pos") or ["0"])[0] or 0)
                return self._manda(json.dumps(sessione.scheda(pos)))
            if p.path.startswith("/ritaglio/"):
                sha = urllib.parse.unquote(p.path[len("/ritaglio/"):])
                return self._immagine(f"ritagli/{sha}.jpg")
            if p.path.startswith("/foto/"):
                nome = urllib.parse.unquote(p.path[len("/foto/"):])
                chiave = sessione.trova_foto(nome)
                if chiave is None:
                    return self._manda(b"", "text/plain", 404)
                return self._immagine(sessione.orienta(chiave), chiave)
            self._manda(b"", "text/plain", 404)

        def do_POST(self):
            lunghezza = int(self.headers.get("Content-Length", 0))
            corpo = json.loads(self.rfile.read(lunghezza) or b"{}")
            if self.path == "/giudica":
                sessione.giudica(corpo)
                return self._manda(json.dumps({"ok": True}))
            self._manda(b"", "text/plain", 404)

    class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    with Server(("127.0.0.1", porta), Gestore) as s:
        print(f"\n  Revisione su http://localhost:{porta}")
        print(f"  {len(sessione.coda)} scontrini in coda. Ctrl-C per uscire.\n")
        try:
            s.serve_forever()
        except KeyboardInterrupt:
            print(f"\n  {sessione.giudicati} giudicati in questa sessione.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chi", default="ignoto", help="chi sta rivedendo")
    ap.add_argument("--db", default=str(RADICE / "data" / "spese.db"))
    ap.add_argument("--porta", type=int, default=8098)
    ap.add_argument("--apri", action="store_true", help="apre il browser")
    ap.add_argument("--sospetto", choices=["taglio", "estrazione", "non_verificabile"],
                    help="rivedi solo questa classe (per una misura mirata: "
                         "'estrazione' e' il campione per confrontare gli estrattori, "
                         "vedi docs/122_metrica_confronto_vlm.md)")
    args = ap.parse_args()

    sessione = Sessione(args.db, args.chi, args.sospetto)
    if not sessione.coda:
        print("Niente da rivedere: la coda e' vuota.")
        return 0
    if args.apri:
        webbrowser.open(f"http://localhost:{args.porta}")
    servi(sessione, args.porta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
