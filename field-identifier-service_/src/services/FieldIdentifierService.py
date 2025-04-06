import cv2
import numpy as np
import geopandas as gpd
from shapely.geometry import Polygon
import requests
from PIL import Image
from io import BytesIO
import matplotlib.pyplot as plt
import time
import concurrent.futures

class FieldIdentifierService:
    def __init__(self):
        # Simple in-memory cache for tiles
        self._tile_cache = {}

    def solidez(self, img, sol_min=0.0):
        """
        Keep contours above a certain solidity threshold.
        """
        contours, hierarchy = cv2.findContours(img, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        if not contours or hierarchy is None:
            return np.zeros_like(img)

        hierarchy = hierarchy[0]
        mask = np.zeros_like(img)

        for i, cnt in enumerate(contours):
            area_contorno = cv2.contourArea(cnt)
            casco_convexo = cv2.convexHull(cnt)
            area_casco_convexo = cv2.contourArea(casco_convexo)

            # If the area of the convex hull is zero, skip
            if area_casco_convexo <= 0:
                continue

            solidity = float(area_contorno) / area_casco_convexo
            if solidity >= sol_min:
                # Keep external contours (parent == -1)
                if hierarchy[i][3] == -1:
                    cv2.drawContours(mask, [cnt], -1, 255, thickness=cv2.FILLED)
                else:
                    # Remove holes (children)
                    cv2.drawContours(mask, [cnt], -1, 0, thickness=cv2.FILLED)

        return mask

    def remove_white(self, img, min_area_w=1000, min_area_b=1000):
        """
        Remove white contours below min_area_w and internal black contours below min_area_b.
        """
        contours, hierarchy = cv2.findContours(img, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if not contours or hierarchy is None:
            return np.zeros_like(img)

        hierarchy = hierarchy[0]
        mask = np.zeros_like(img)

        for i, cnt in enumerate(contours):
            area = cv2.contourArea(cnt)
            # If this is a parent contour (external, hierarchy[i][3] == -1)
            if hierarchy[i][3] == -1:
                if area >= min_area_w:
                    cv2.drawContours(mask, [cnt], -1, 255, thickness=cv2.FILLED)
            else:
                # Child contour
                if area >= min_area_b:
                    cv2.drawContours(mask, [cnt], -1, 0, thickness=cv2.FILLED)

        return mask

    def lat_lon_para_tile_xy(self, lat, lon, zoom):
        """
        Convert latitude and longitude to tile X/Y coordinates for a given zoom.
        """
        n = 2 ** zoom
        xtile = int((lon + 180.0) / 360.0 * n)
        lat_rad = np.radians(lat)
        ytile = int((1.0 - np.log(np.tan(lat_rad) + 1 / np.cos(lat_rad)) / np.pi) / 2.0 * n)
        return xtile, ytile

    def tile_xy_para_bounds(self, xtile, ytile, zoom):
        """
        Return (lon_left, lat_bottom, lon_right, lat_top) for a given tile.
        """
        n = 2 ** zoom
        lon_left = xtile / n * 360.0 - 180.0
        lon_right = (xtile + 1) / n * 360.0 - 180.0
        lat_top_rad = np.arctan(np.sinh(np.pi * (1 - 2 * ytile / n)))
        lat_bottom_rad = np.arctan(np.sinh(np.pi * (1 - 2 * (ytile + 1) / n)))
        lat_top = np.degrees(lat_top_rad)
        lat_bottom = np.degrees(lat_bottom_rad)
        return (lon_left, lat_bottom, lon_right, lat_top)

    def _download_single_tile(self, x, y, z):
        """
        Helper function to download a single tile (used by thread executor).
        Checks cache first.
        """
        if (x, y, z) in self._tile_cache:
            return self._tile_cache[(x, y, z)]

        url = f"https://mts1.google.com/vt/lyrs=y&hl=en&src=app&x={x}&y={y}&z={z}&s=G"
        response = requests.get(url)
        if response.status_code == 200:
            image = Image.open(BytesIO(response.content))
            image_cv = np.array(image)
            if image_cv.shape[2] == 4:
                image_cv = cv2.cvtColor(image_cv, cv2.COLOR_RGBA2BGR)
            else:
                image_cv = cv2.cvtColor(image_cv, cv2.COLOR_RGB2BGR)

            self._tile_cache[(x, y, z)] = image_cv
            return image_cv
        else:
            raise Exception(f"Erro ao baixar imagem: {response.status_code}")

    def juntar_tiles_regiao(self, lat, lon, zoom, tile_gap_x, tile_gap_y):
        """
        Download and merge all tiles for a region around (lat, lon).
        Uses parallel download to speed up tile fetching.
        """
        xtile, ytile = self.lat_lon_para_tile_xy(lat, lon, zoom)

        xtile_min = xtile - tile_gap_x
        xtile_max = xtile + tile_gap_x
        ytile_min = ytile - tile_gap_y
        ytile_max = ytile + tile_gap_y

        # Prepare all (x, y) combos
        tiles_coords = [
            (x, y) 
            for y in range(ytile_min, ytile_max + 1) 
            for x in range(xtile_min, xtile_max + 1)
        ]

        # Download in parallel
        tile_images = {}
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_tile = {
                executor.submit(self._download_single_tile, x, y, zoom): (x, y)
                for (x, y) in tiles_coords
            }
            for future in concurrent.futures.as_completed(future_to_tile):
                x, y = future_to_tile[future]
                tile_images[(x,y)] = future.result()

        # Now build rows in ascending y order
        # (Note: tile coordinates increase downward, so we sort by y ascending)
        linhas = []
        for y in range(ytile_min, ytile_max + 1):
            linha_tiles = []
            for x in range(xtile_min, xtile_max + 1):
                linha_tiles.append(tile_images[(x, y)])
            linha_concatenada = np.concatenate(linha_tiles, axis=1)
            linhas.append(linha_concatenada)

        # Concatenate vertically
        imagem_final = np.concatenate(linhas, axis=0)

        # Calculate geographic bounds
        min_lon_final, _, _, max_lat_final = self.tile_xy_para_bounds(xtile_min, ytile_min, zoom)
        _, min_lat_final, max_lon_final, _ = self.tile_xy_para_bounds(xtile_max, ytile_max, zoom)

        bounds = (min_lon_final, min_lat_final, max_lon_final, max_lat_final)
        tiles_count = len(tiles_coords)
        return imagem_final, bounds, tiles_count

    def processar_imagem_1(self, imagem, blur=5, area=5000, sol=0.3):
        """
        Single-step approach to detect edges, fill masks, remove noise, and return contours.
        """
        # Convert to HSV, then blur
        hsv = cv2.cvtColor(imagem, cv2.COLOR_BGR2HSV)
        hsv_blur = cv2.GaussianBlur(hsv, (blur, blur), 0)

        # Canny
        edges = cv2.Canny(hsv_blur, 50, 150)

        # Basic dilation + close
        kernel = np.ones((2,2), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=1)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

        # Threshold inverted -> potential region mask
        _, edges_inv = cv2.threshold(edges, 127, 255, cv2.THRESH_BINARY_INV)

        # Remove small white/black
        cleaned = self.remove_white(edges_inv, area, area)

        # Filter by solidity
        cleaned = self.solidez(cleaned, sol)

        # Final contours
        contornos, hierarchy = cv2.findContours(cleaned, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        approx_contours = []
        if contornos is not None:
            for cnt in contornos:
                if cv2.contourArea(cnt) > 0:
                    # Larger epsilon -> simpler polygons, faster
                    epsilon = 0.001 * cv2.arcLength(cnt, True)
                    approx = cv2.approxPolyDP(cnt, epsilon, True)
                    approx_contours.append(approx)

        return approx_contours, hierarchy

    def processar_imagem_2(self, imagem):
        """
        An alternative process flow with heavier filtering.
        (Kept as is, but simplified slightly.)
        """
        hsv = cv2.cvtColor(imagem, cv2.COLOR_BGR2HSV)
        hsv_blur = cv2.GaussianBlur(hsv, (11,11), 0)

        # Canny
        edges = cv2.Canny(hsv_blur, 50, 150)
        kernel = np.ones((4,4), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=1)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

        _, edges_inv = cv2.threshold(edges, 127, 255, cv2.THRESH_BINARY_INV)
        edges_inv = self.remove_white(edges_inv, 5000, 5000)
        aux = edges_inv

        # Additional filtering
        filtrada = cv2.bitwise_and(hsv, hsv, mask=edges_inv)
        filtrada = cv2.GaussianBlur(filtrada, (5,5), 0)
        bordas_filtrada = cv2.Canny(filtrada, 50, 150)
        bordas_filtrada = cv2.bitwise_and(bordas_filtrada, bordas_filtrada, mask=edges_inv)

        bordas_filtrada = cv2.bitwise_not(bordas_filtrada)
        merged = cv2.bitwise_and(edges_inv, edges_inv, mask=bordas_filtrada)
        merged = cv2.Canny(merged, 50, 150)

        merged = cv2.dilate(merged, kernel, iterations=1)
        merged = cv2.morphologyEx(merged, cv2.MORPH_CLOSE, kernel)
        _, merged = cv2.threshold(merged, 127, 255, cv2.THRESH_BINARY_INV)
        merged = cv2.bitwise_and(merged, merged, mask=aux)

        merged = self.solidez(merged, 0.3)
        merged = self.remove_white(merged, 3000, 3000)

        contornos, hierarchy = cv2.findContours(merged, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        approx_contours = []
        if contornos is not None:
            for cnt in contornos:
                if cv2.contourArea(cnt) > 0:
                    epsilon = 0.001 * cv2.arcLength(cnt, True)
                    approx = cv2.approxPolyDP(cnt, epsilon, True)
                    approx_contours.append(approx)

        return approx_contours, hierarchy

    def identify_fields(self, latitude, longitude, type=1):
        """
        Download/merge tiles, process final image, and build WKT polygons.
        """
        # Decide which zoom/tile gap based on type
        if type == 2 or type == 3:
            imagem, bounds, tiles = self.juntar_tiles_regiao(latitude, longitude, 16, 6, 4)
        else:
            imagem, bounds, tiles = self.juntar_tiles_regiao(latitude, longitude, 15, 3, 2)

        min_lon_img, min_lat_img, max_lon_img, max_lat_img = bounds

        # Pick the processing pipeline
        if type == 3:
            contornos, hierarchy = self.processar_imagem_1(imagem, blur=7, area=10000, sol=0.5)
        elif type == 2:
            contornos, hierarchy = self.processar_imagem_1(imagem, blur=5, area=3000, sol=0.3)
        elif type == 1:
            contornos, hierarchy = self.processar_imagem_1(imagem, blur=5, area=3000, sol=0.3)
        else:
            contornos, hierarchy = self.processar_imagem_2(imagem)

        altura_img, largura_img = imagem.shape[:2]
        poligonos = []

        if contornos and hierarchy is not None:
            hierarchy = hierarchy[0]
            # Map parent index -> list of its holes (children)
            contour_children = {}
            for idx, (cnt, hier) in enumerate(zip(contornos, hierarchy)):
                parent_idx = hier[3]
                if parent_idx == -1:
                    contour_children[idx] = []
                else:
                    contour_children.setdefault(parent_idx, []).append(idx)

            for parent_idx, child_indices in contour_children.items():
                cnt = contornos[parent_idx]
                pontos_ext = cnt[:, 0, :]
                lon_list_ext = min_lon_img + (pontos_ext[:, 0] / (largura_img - 1)) * (max_lon_img - min_lon_img)
                lat_list_ext = max_lat_img - (pontos_ext[:, 1] / (altura_img - 1)) * (max_lat_img - min_lat_img)
                lon_list_ext = [round(lon, 6) for lon in lon_list_ext]
                lat_list_ext = [round(lat, 6) for lat in lat_list_ext]
                exterior_coords = list(zip(lon_list_ext, lat_list_ext))

                # Skip if not enough points
                if len(exterior_coords) < 4:
                    continue

                holes = []
                for child_idx in child_indices:
                    cnt_hole = contornos[child_idx]
                    pontos_int = cnt_hole[:, 0, :]
                    lon_list_int = min_lon_img + (pontos_int[:, 0] / (largura_img - 1)) * (max_lon_img - min_lon_img)
                    lat_list_int = max_lat_img - (pontos_int[:, 1] / (altura_img - 1)) * (max_lat_img - min_lat_img)
                    hole_coords = list(zip(lon_list_int, lat_list_int))
                    if len(hole_coords) < 4:
                        continue
                    holes.append(hole_coords)

                poligono = Polygon(shell=exterior_coords, holes=holes)
                poligonos.append(poligono)


        wkts = []
        i = 0
        for poly in poligonos:
            dict = {"id":i, "coordinates":poly.wkt}
            wkts.append(dict)
            i = i+1

        return wkts



