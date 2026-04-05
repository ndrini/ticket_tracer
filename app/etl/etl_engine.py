# app/etl/etl_engine.py

import cv2
import numpy as np
from paddleocr import PaddleOCR


class ReceiptPipeline:
    def __init__(self):
        # Inizializziamo PaddleOCR.
        # Disabilitiamo i modelli accessori (UVDoc, textline, doc_ori, angle_cls)
        # che saturano i gigabyte di RAM caricando 3-4 reti neurali aggiuntive.
        self.ocr = PaddleOCR(
            lang="es", # Spagnolo, copre perfettamente anche catalano, italiano e inglese
            enable_mkldnn=False,
            cpu_threads=3,
            use_doc_orientation_classify=False,
            use_textline_orientation=False
        )

    def process_image(self, image_path):
        """Immagine → lista di dati strutturati (uno per scontrino)."""
        receipts_lines, _ = self.extract_raw_ocr(image_path)
        return [self.parse_raw_data(lines) for lines in receipts_lines]

    def extract_raw_ocr(self, image_path):
        """
        1. Ridimensiona l'immagine se gigantesca.
        2. OCR a 4 rotazioni sull'immagine intera → sceglie la migliore.
        3. Separa i ricevute tramite clustering dei bounding box (Gap Y e Gap X).
        Restituisce (list[list[line]], list[np.ndarray])
        """
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Impossibile leggere: {image_path}")

        # Ridimensionamento anti-freeze
        image = self._resize_safe(image, max_dim=2000)

        # 4-ROTATION OCR
        best_lines, best_image = self._best_rotation_ocr(image)

        if not best_lines:
            return [[]], [best_image]

        # Separa i ricevute in base ai gap tra i bounding box
        return self._split_by_gaps(best_lines, best_image)

    def _resize_safe(self, image: np.ndarray, max_dim: int = 2000) -> np.ndarray:
        h, w = image.shape[:2]
        if max(h, w) <= max_dim:
            return image
        scale = max_dim / float(max(h, w))
        return cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    def _best_rotation_ocr(self, image: np.ndarray):
        """
        Esegue OCR per 0°, 90°, 180°, 270°.
        Sceglie la rotazione con score più alto (n_linee x confidenza_media).
        """
        best_score = -1
        best_lines = []
        best_img = image
        
        rotations = {
            0: None,
            90: cv2.ROTATE_90_CLOCKWISE,
            180: cv2.ROTATE_180,
            270: cv2.ROTATE_90_COUNTERCLOCKWISE,
        }

        for dg, code in rotations.items():
            rotated = image if code is None else cv2.rotate(image, code)
            lines = self._run_single_ocr(rotated)
            score = self._ocr_score(lines)
            if score > best_score:
                best_score = score
                best_lines = lines
                best_img = rotated
        
        return best_lines, best_img

    def _ocr_score(self, lines: list) -> float:
        if not lines: return 0.0
        scores = [l[1][1] for l in lines]
        return len(lines) * (sum(scores)/len(scores))

    def _run_single_ocr(self, image_input):
        """PaddleOCR su immagine singola."""
        try:
            res = self.ocr.predict(image_input)
        except Exception:
            try:
                res = self.ocr.ocr(image_input)
            except Exception:
                return []
        if not res or not res[0]: return []
        return self._extract_lines_from_res(res[0])

    def _extract_lines_from_res(self, res_obj):
        if isinstance(res_obj, list):
            if res_obj and isinstance(res_obj[0], list): return res_obj
        elif hasattr(res_obj, 'get') or isinstance(res_obj, dict):
            rec_texts = res_obj.get('rec_texts', [])
            rec_scores = res_obj.get('rec_scores', [])
            dt_polys = res_obj.get('dt_polys', [])
            lines = []
            for i in range(len(rec_texts)):
                box = dt_polys[i].tolist() if i < len(dt_polys) and hasattr(dt_polys[i], 'tolist') else []
                lines.append([box, (rec_texts[i], rec_scores[i] if i < len(rec_scores) else 1.0)])
            return lines
        return []

    def _split_by_gaps(self, lines: list, full_image: np.ndarray) -> tuple:
        """
        Separa i ricevute clusterizzando i bounding box.
        1. Gap Y (stack verticale)
        2. Gap X (side-by-side) per ogni cluster Y
        """
        if not lines: return [[]], [full_image]

        def get_y_center(line):
            return sum([p[1] for p in line[0]]) / 4
        def get_x_center(line):
            return sum([p[0] for p in line[0]]) / 4

        # Ordina per Y e raggruppa
        lines_sorted_y = sorted(lines, key=get_y_center)
        y_clusters = []
        current_cluster = [lines_sorted_y[0]]
        for line in lines_sorted_y[1:]:
            if get_y_center(line) - get_y_center(current_cluster[-1]) > 100: # Gap Y di 100px
                y_clusters.append(current_cluster)
                current_cluster = [line]
            else:
                current_cluster.append(line)
        y_clusters.append(current_cluster)

        # Per ogni cluster Y, controlliamo se ci sono gap X (affiancati)
        final_receipt_lines = []
        for cluster in y_clusters:
            # Ordina per X e raggruppa
            cluster_sorted_x = sorted(cluster, key=get_x_center)
            current_x_sub = [cluster_sorted_x[0]]
            for line in cluster_sorted_x[1:]:
                # Gap X di 50 pixel è solitamente sufficiente
                if get_x_center(line) - get_x_center(current_x_sub[-1]) > 50:
                    final_receipt_lines.append(current_x_sub)
                    current_x_sub = [line]
                else:
                    current_x_sub.append(line)
            final_receipt_lines.append(current_x_sub)
        
        # Generiamo le immagini ritagliate per coerenza (opzionale, usiamo pezzi del best_image)
        crops = []
        for receipt in final_receipt_lines:
            all_pts = []
            for l in receipt: all_pts.extend(l[0])
            if all_pts:
                all_pts = np.array(all_pts)
                x, y, w, h = cv2.boundingRect(all_pts)
                # Padding
                x, y = max(0, x-10), max(0, y-10)
                w, h = min(full_image.shape[1]-x, w+20), min(full_image.shape[0]-y, h+20)
                crops.append(full_image[y:y+h, x:x+w])
            else:
                crops.append(full_image)

        return final_receipt_lines, crops

    def parse_raw_data(self, raw_ocr_output):
        """Ricostruisce le righe di testo."""
        if not raw_ocr_output: return {"shop_name": "Unknown", "date": None, "total": 0.0, "items": []}
        
        def get_y_center(line): return sum([p[1] for p in line[0]]) / 4
        def get_x_start(line): return min([p[0] for p in line[0]])
        
        sorted_lines = sorted(raw_ocr_output, key=get_y_center)
        rows = []
        if sorted_lines:
            curr_row = [sorted_lines[0]]
            for l in sorted_lines[1:]:
                if get_y_center(l) - get_y_center(curr_row[-1]) < 15: # Soglia riga 15px
                    curr_row.append(l)
                else:
                    rows.append(sorted(curr_row, key=get_x_start))
                    curr_row = [l]
            rows.append(sorted(curr_row, key=get_x_start))
        
        reconstructed_text = []
        for r in rows:
            reconstructed_text.append(" ".join([l[1][0] for l in r]))
            
        return reconstructed_text # Passiamo il testo reconstruction al processore
