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
        """
        Metodo principale: Immagine -> Lista di Dati Strutturati
        Gestisce il ritaglio automatico se ci sono più scontrini.
        """
        # 1. Preprocessing: Rilevamento e ritaglio
        raw_results, rotated_images = self.extract_raw_ocr(image_path)
        
        structured_results = []
        for raw in raw_results:
            structured_results.append(self.parse_raw_data(raw))

        return structured_results


    def extract_raw_ocr(self, image_path):
        """
        Rileva e ritaglia gli scontrini dall'immagine, esegue l'OCR e restituisce
        sia l'output grezzo (le righe estratte) che l'immagine ritagliata. 
        Utile per la pipeline in 2 fasi e il debug.
        """
        cropped_images = self._detect_and_crop_receipts(image_path)
        all_raw_data = []
        final_rotated_images = []
        for img in cropped_images:
            raw_ocr_data, best_img = self._run_ocr(img)
            all_raw_data.append(raw_ocr_data)
            final_rotated_images.append(best_img)
        return all_raw_data, final_rotated_images




    def _detect_and_crop_receipts(self, image_path):
        """
        Analizza l'immagine per trovare uno o più scontrini, li raddrizza
        con una trasformazione prospettica e li restituisce.
        Questo metodo è più robusto del semplice rilevamento di contorni.
        """
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Impossibile leggere l'immagine: {image_path}")

        # --- NOVITA' ANTI-FREEZING: Ridimensioniamo preventivamente ---
        # Molte fotocamere (12-50 MPixel) creano immagini gigantesche in RAM. 
        # Canny e findContours possono superare i 15 GB su una singola immagine!
        img_h, img_w = image.shape[:2]
        max_dim = 1600 # Massima dimensione consigliata per uno scontrino
        if max(img_h, img_w) > max_dim:
            scale = max_dim / float(max(img_h, img_w))
            image = cv2.resize(image, (int(img_w * scale), int(img_h * scale)), interpolation=cv2.INTER_AREA)

        orig = image.copy()
        img_h, img_w = image.shape[:2]
        min_area = max(40000, (img_w * img_h) * 0.02) # Leggermente più permissivo per scontrini piccoli

        # --- PRE-PROCESSING ROBUSTO ---
        # Bilateral filter mantiene i bordi ma pulisce il rumore/trama di sottofondo
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.bilateralFilter(gray, 11, 75, 75)
        
        # Adaptive Threshold per gestire luci non uniformi
        thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        
        edges = cv2.Canny(thresh, 50, 150)
        
        # --- SEPARAZIONE SCONTRINI ---
        # Usiamo un kernel VERTICALE per unire le righe di uno scontrino
        # senza però unire gli scontrini tra loro (che sono affiancati).
        kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 15))
        closed_v = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel_v, iterations=2)
        
        # Un piccolo tocco orizzontale solo per stabilizzare i bordi
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1))
        closed = cv2.morphologyEx(closed_v, cv2.MORPH_CLOSE, kernel_h, iterations=1)




        contours, _ = cv2.findContours(
            closed.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )


        def score_quad(pts):
            rect = cv2.minAreaRect(pts)
            (w, h) = rect[1]
            if w <= 0 or h <= 0:
                return 0.0
            area = abs(cv2.contourArea(pts))
            ratio = max(w / h, h / w)
            if ratio > 5.0:
                return 0.0
            aspect_score = 1.0 - abs((ratio - 1.5) / 4.0)
            aspect_score = max(aspect_score, 0.0)
            size_score = min(area / (img_w * img_h), 1.0)
            return aspect_score * size_score

        candidates = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area or area > img_w * img_h * 0.98:
                continue
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                candidates.append((score_quad(approx), approx))

        if not candidates:
            # fallback con minAreaRect sui contorni grandi
            for c in sorted(contours, key=cv2.contourArea, reverse=True)[:50]:
                area = cv2.contourArea(c)
                if area < min_area or area > img_w * img_h * 0.98:
                    continue
                rect = cv2.minAreaRect(c)
                (w, h) = rect[1]
                if min(w, h) < 60 or max(w, h) < 100: # Ancora più permissivo per scontrini piccoli
                    continue
                ratio = max(w / h, h / w)
                if ratio > 8.0: # Permettiamo scontrini Molto lunghi
                    continue
                box = cv2.boxPoints(rect).astype("float32")
                score = score_quad(box)
                if score > 0:
                    candidates.append((score, box.reshape(4, 1, 2)))
                if len(candidates) >= 10:
                    break

        receipt_contours = [
            x[1] for x in sorted(candidates, key=lambda s: s[0], reverse=True)[:10]
        ]


        # --- FALLBACK: Se non ha trovato quadrilateri validi, proviamo con le bounding box dei contorni grandi ---
        if not receipt_contours:
            for c in sorted(contours, key=cv2.contourArea, reverse=True)[:20]:
                area = cv2.contourArea(c)
                if area < min_area:
                    continue
                # Verifichiamo il rapporto d'aspetto della bounding box
                x, y, w, h = cv2.boundingRect(c)
                ratio = max(w / h, h / w)
                if ratio < 1.05 or ratio > 15.0: # Leggermente più permissivo
                    continue
                rect = cv2.minAreaRect(c)
                box = cv2.boxPoints(rect).astype("float32")
                receipt_contours.append(box.reshape(4, 1, 2))
                if len(receipt_contours) >= 10: # Fino a 10 scontrini
                    break




        def order_points(pts):
            rect = np.zeros((4, 2), dtype="float32")
            s = pts.sum(axis=1)
            rect[0] = pts[np.argmin(s)]
            rect[2] = pts[np.argmax(s)]
            diff = np.diff(pts, axis=1)
            rect[1] = pts[np.argmin(diff)]
            rect[3] = pts[np.argmax(diff)]
            return rect

        def four_point_transform(image, pts):
            rect = order_points(pts)
            (tl, tr, br, bl) = rect
            widthA = np.linalg.norm(br - bl)
            widthB = np.linalg.norm(tr - tl)
            heightA = np.linalg.norm(tr - br)
            heightB = np.linalg.norm(tl - bl)
            maxWidth = max(int(widthA), int(widthB))
            maxHeight = max(int(heightA), int(heightB))
            if maxWidth <= 0 or maxHeight <= 0:
                return None
            dst = np.array(
                [
                    [0, 0],
                    [maxWidth - 1, 0],
                    [maxWidth - 1, maxHeight - 1],
                    [0, maxHeight - 1],
                ],
                dtype="float32",
            )
            M = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))

            # --- AUTO-ROTATE TO PORTRAIT ---
            # Se la larghezza è maggiore dell'altezza, probabilmente lo scontrino
            # è disteso orizzontalmente. Ruotiamolo di 90 gradi per l'OCR.
            if maxWidth > maxHeight:
                 warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)

            return warped


        warped_images = [
            four_point_transform(orig, c.reshape(4, 2)) for c in receipt_contours
        ]
        warped_images = [img for img in warped_images if img is not None]

        # --- NOVITA': SPLITTING DI RITAGLI DOPPI/TRIPLI ---
        # Se un ritaglio è troppo largo rispetto all'altezza (es. ratio > 0.7),
        # probabilmente contiene più scontrini affiancati. Proviamo a dividerlo.
        final_crops = []
        for img in warped_images:
            h, w = img.shape[:2]
            if w > h * 0.7:  # Sconto tipico scontrino: 1 a 3 o 1 a 4.
                # Proiezione verticale per trovare le "valli" (spazi tra scontrini)
                gray_crop = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                _, binary = cv2.threshold(gray_crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                vertical_projection = np.sum(binary, axis=0) / 255
                
                # Cerchiamo i punti di divisione (valli profonde e larghe)
                # Media mobile per pulire la proiezione
                window = 20
                if w > window:
                    smooth_proj = np.convolve(vertical_projection, np.ones(window)/window, mode='same')
                    
                    # Un gap è dove la densità di testo è molto bassa (< 10% della media)
                    avg_density = np.mean(smooth_proj)
                    gap_threshold = avg_density * 0.15
                    
                    split_points = []
                    in_gap = False
                    start_gap = 0
                    for x in range(window, w - window):
                        if smooth_proj[x] < gap_threshold:
                            if not in_gap:
                                in_gap = True
                                start_gap = x
                        else:
                            if in_gap:
                                in_gap = False
                                end_gap = x
                                if end_gap - start_gap > 15: # Gap largo almeno 15px
                                    split_points.append((start_gap + end_gap) // 2)
                    
                    if split_points:
                        curr_x = 0
                        for sp in split_points:
                            if sp - curr_x > 100: # Evitiamo strisce troppo sottili
                                final_crops.append(img[:, curr_x:sp])
                                curr_x = sp
                        if w - curr_x > 100:
                            final_crops.append(img[:, curr_x:])
                        continue
            
            final_crops.append(img)


        if not final_crops:
            return [orig]

        return final_crops


    def _run_ocr(self, image_input):
        """
        Esegue PaddleOCR sull'immagine e formatta l'output per compatibilità.
        Sperimenta sia 0 che 180 gradi e restituisce la migliore versione.
        Args:
            image_input: path string o numpy array
        Returns:
            (normalized_lines, upright_image)
        """
        # --- SISTEMA DUALE (0° e 180°) PER ORIENTAMENTO INFALLIBILE ---
        # 1. OCR Originale (0°)
        try:
            res_0 = self.ocr.predict(image_input)
        except Exception:
            res_0 = self.ocr.ocr(image_input)
        
        lines_0 = self._extract_lines_from_res(res_0[0]) if res_0 and res_0[0] else []
        score_0 = sum([l[1][1] for l in lines_0]) / len(lines_0) if lines_0 else 0
        quality_0 = len(lines_0) * score_0

        # 2. OCR Ruotato (180°)
        rotated = cv2.rotate(image_input, cv2.ROTATE_180)
        try:
            res_180 = self.ocr.predict(rotated)
        except Exception:
            res_180 = self.ocr.ocr(rotated)
            
        lines_180 = self._extract_lines_from_res(res_180[0]) if res_180 and res_180[0] else []
        score_180 = sum([l[1][1] for l in lines_180]) / len(lines_180) if lines_180 else 0
        quality_180 = len(lines_180) * score_180

        # Scegliamo il migliore in base a (numero linee * confidenza media)
        if quality_180 > quality_0:
            return lines_180, rotated
        return lines_0, image_input

    def _extract_lines_from_res(self, res_obj):
        if isinstance(res_obj, list):
            # Gestione caso legacy: res_obj è già una lista di linee [ [box, (text, score)], ... ]
            if len(res_obj) > 0 and isinstance(res_obj[0], list):
                return res_obj
        elif hasattr(res_obj, 'keys') or isinstance(res_obj, dict):
            # Caso PaddleX OCRResult
            rec_texts = res_obj.get('rec_texts', [])
            rec_scores = res_obj.get('rec_scores', [])
            dt_polys = res_obj.get('dt_polys', [])
            
            lines = []
            for i in range(len(rec_texts)):
                box = dt_polys[i].tolist() if i < len(dt_polys) and hasattr(dt_polys[i], 'tolist') else []
                text = rec_texts[i]
                score = rec_scores[i] if i < len(rec_scores) else 1.0
                lines.append([box, (text, score)])
            return lines
        return []




    def parse_raw_data(self, raw_ocr_output):
        """
        Prende l'output grezzo dell'OCR, ricostruisce le righe
        e usa l'LLM per estrarre il JSON.
        """
        # 1. Ricostruzione linee (clustering Y)
        lines = self._cluster_lines(raw_ocr_output)

        # 2. Chiamata a Ollama (Mock per ora)
        # TODO: Implementare chiamata a Ollama

        # Return mock structure per far passare il test
        return {"shop_name": "Unknown", "date": "2023-01-01", "total": 0.0, "items": []}

    def _cluster_lines(self, raw_ocr_output):
        """
        Raggruppa i box di testo che sono sulla stessa linea orizzontale.
        """
        # Logica placeholder
        return []
