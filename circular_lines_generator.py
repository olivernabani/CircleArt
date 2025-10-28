#!/usr/bin/env python3
"""
Circular Lines Generator
========================

Autor: Oliver Nabani
Versión: 1.0
"""

import argparse
import numpy as np
from PIL import Image, ImageEnhance
import sys
import os

try:
    from shapely.geometry import Polygon, MultiPolygon, box
    from shapely.ops import unary_union
    from shapely.affinity import translate
except ImportError:
    print("Error: Se requiere la librería 'shapely'")
    print("Instálala con: pip install shapely")
    sys.exit(1)


# CONSTANTES FÍSICAS PARA IMPRESIÓN 3D (Pueden cambiarse)
PANEL_SIZE_MM = 217.7  # Tamaño de cada panel en mm
MARCO_WIDTH_MM = 3.2   # Ancho del marco en mm
LINEA_SEPARADORA_MM = 2.8  # Ancho de las líneas separadoras entre paneles


def ajustar_contraste(imagen, contraste):
    """Ajusta el contraste de la imagen."""
    factor = contraste / 50.0
    enhancer = ImageEnhance.Contrast(imagen)
    return enhancer.enhance(factor)


def suavizar_valores(valores, ventana=1):
    """Aplica un promedio móvil circular para suavizar transiciones."""
    n = len(valores)
    suavizados = np.zeros(n)
    mitad_ventana = ventana // 2

    for i in range(n):
        indices = [(i + j - mitad_ventana) % n for j in range(ventana)]
        suavizados[i] = np.mean([valores[idx] for idx in indices])

    return suavizados


def calcular_dimensiones_canvas(imagen):

    ancho_img, alto_img = imagen.size

    # Determinar si es horizontal o vertical
    if ancho_img >= alto_img:
        # Horizontal: 3 columnas x 2 filas
        cols, rows = 3, 2
    else:
        # Vertical: 2 columnas x 3 filas
        cols, rows = 2, 3

    ancho_mm = cols * PANEL_SIZE_MM
    alto_mm = rows * PANEL_SIZE_MM

    return ancho_mm, alto_mm, cols, rows


def ajustar_proporcion_imagen(imagen, cols, rows):

    ancho_actual, alto_actual = imagen.size
    ratio_actual = ancho_actual / alto_actual

    # Calcular ratio objetivo
    ratio_objetivo = cols / rows

    # Si ya tiene la proporción correcta (con tolerancia de 1%), no hacer nada
    if abs(ratio_actual - ratio_objetivo) < 0.01:
        return imagen

    # Determinar si recortar por ancho o por alto
    if ratio_actual > ratio_objetivo:
        # Imagen más ancha de lo necesario - recortar ancho
        nuevo_ancho = int(alto_actual * ratio_objetivo)
        nuevo_alto = alto_actual

        # Calcular offset para centrar
        offset_x = (ancho_actual - nuevo_ancho) // 2
        offset_y = 0
    else:
        # Imagen más alta de lo necesario - recortar alto
        nuevo_ancho = ancho_actual
        nuevo_alto = int(ancho_actual / ratio_objetivo)

        # Calcular offset para centrar
        offset_x = 0
        offset_y = (alto_actual - nuevo_alto) // 2

    # Realizar crop centrado
    imagen_cropped = imagen.crop((
        offset_x,
        offset_y,
        offset_x + nuevo_ancho,
        offset_y + nuevo_alto
    ))

    print(f"  Imagen ajustada: {ancho_actual}x{alto_actual} → {nuevo_ancho}x{nuevo_alto} (crop centrado)")

    return imagen_cropped


def optimizar_puntos(puntos_exterior, puntos_interior, grosores, tolerancia=0.01):

    n = len(grosores)
    if n < 3:
        return puntos_exterior, puntos_interior, list(range(n))

    indices_mantenidos = []
    i = 0

    while i < n:
        grosor_actual = grosores[i]
        j = i + 1

        while j < n and abs(grosores[j] - grosor_actual) < tolerancia:
            j += 1

        longitud_segmento = j - i

        if longitud_segmento >= 6:
            indices_mantenidos.append(i)
            paso = max(3, longitud_segmento // 4)
            for k in range(i + paso, j, paso):
                indices_mantenidos.append(k)
        else:
            for k in range(i, j):
                indices_mantenidos.append(k)

        i = j

    indices_mantenidos = sorted(list(set(indices_mantenidos)))

    # Rellenar huecos grandes
    indices_final = []
    for idx in range(len(indices_mantenidos)):
        indices_final.append(indices_mantenidos[idx])
        siguiente_idx = (idx + 1) % len(indices_mantenidos)
        distancia = indices_mantenidos[siguiente_idx] - indices_mantenidos[idx]

        if siguiente_idx == 0:
            distancia = n - indices_mantenidos[idx] + indices_mantenidos[siguiente_idx]

        if distancia > 5:
            puntos_intermedios = distancia // 3
            for p in range(1, puntos_intermedios + 1):
                nuevo_idx = (indices_mantenidos[idx] + p * distancia // (puntos_intermedios + 1)) % n
                if nuevo_idx not in indices_final:
                    indices_final.append(nuevo_idx)

    indices_final = sorted(list(set(indices_final)))

    puntos_ext_opt = [puntos_exterior[i] for i in indices_final]
    puntos_int_opt = [puntos_interior[i] for i in indices_final]

    return puntos_ext_opt, puntos_int_opt, indices_final


def crear_poligono_anillo(puntos_exterior, puntos_interior):

    try:
        if len(puntos_exterior) < 3 or len(puntos_interior) < 3:
            return None

        poligono = Polygon(puntos_exterior, [puntos_interior])

        if not poligono.is_valid:
            poligono = poligono.buffer(0)

        return poligono
    except Exception as e:
        return None


def polygon_a_svg_path(poligono):

    paths = []

    if poligono.is_empty:
        return ""

    if isinstance(poligono, MultiPolygon):
        for poly in poligono.geoms:
            path = polygon_a_svg_path(poly)
            if path:
                paths.append(path)
        return " ".join(paths)

    if not isinstance(poligono, Polygon):
        return ""

    # Exterior del polígono
    coords = list(poligono.exterior.coords)
    if len(coords) < 3:
        return ""

    path_data = f"M {coords[0][0]:.2f},{coords[0][1]:.2f} "
    for x, y in coords[1:]:
        path_data += f"L {x:.2f},{y:.2f} "
    path_data += "Z "

    # Agujeros interiores
    for interior in poligono.interiors:
        coords = list(interior.coords)
        if len(coords) < 3:
            continue
        path_data += f"M {coords[0][0]:.2f},{coords[0][1]:.2f} "
        for x, y in coords[1:]:
            path_data += f"L {x:.2f},{y:.2f} "
        path_data += "Z "

    return path_data


def circulo_intersecta_canvas(cx, cy, radio, grosor_max, ancho, alto):

    radio_ext = radio + grosor_max / 2

    if cx + radio_ext < 0 or cx - radio_ext > ancho:
        return False
    if cy + radio_ext < 0 or cy - radio_ext > alto:
        return False

    return True


def escribir_svg(file_path, ancho, alto, ancho_mm, alto_mm, geometria):

    with open(file_path, 'w') as f:
        f.write('<?xml version="1.0" ?>\n')
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'baseProfile="full" '
                f'height="{alto_mm}mm" '
                f'width="{ancho_mm}mm" '
                f'viewBox="0 0 {ancho} {alto}" '
                f'version="1.1">\n')

        path_data = polygon_a_svg_path(geometria)
        if path_data:
            f.write(f'<path d="{path_data}" fill="black"/>\n')

        f.write('</svg>\n')


def generar_svg_circular(imagen_path, num_lineas, grosor_min, grosor_max, contraste, centro_x, centro_y, output_path, dividir_paneles=True):

    print(f"Cargando imagen: {imagen_path}")
    imagen = Image.open(imagen_path)

    if imagen.mode != 'L':
        imagen = imagen.convert('L')

    # Calcular dimensiones físicas según orientación (antes de ajustar)
    ancho_mm, alto_mm, cols, rows = calcular_dimensiones_canvas(imagen)

    # Ajustar proporción de la imagen mediante crop centrado
    imagen = ajustar_proporcion_imagen(imagen, cols, rows)

    # Ajustar contraste
    if contraste != 50:
        print(f"Ajustando contraste: {contraste}")
        imagen = ajustar_contraste(imagen, contraste)

    # Trabajar con la imagen (ya con proporción ajustada)
    imagen_array = np.array(imagen)
    alto_original, ancho_original = imagen_array.shape

    print(f"Modo: {'Archivo completo + 6 paneles' if dividir_paneles else 'Solo archivo completo'}")
    print(f"Orientación detectada: {'Horizontal' if cols > rows else 'Vertical'}")
    print(f"Disposición de paneles: {cols}x{rows}")
    print(f"Dimensiones físicas totales: {ancho_mm}mm x {alto_mm}mm")
    print(f"Marco: {MARCO_WIDTH_MM}mm")

    alto, ancho = alto_original, ancho_original

    # Calcular posición del centro en píxeles
    cx = int(ancho * centro_x / 100.0)
    cy = int(alto * centro_y / 100.0)

    print(f"Dimensiones canvas: {ancho}x{alto} píxeles")
    print(f"Centro: ({cx}, {cy})")

    radio_max = np.sqrt(
        max(cx**2 + cy**2,
            (ancho - cx)**2 + cy**2,
            cx**2 + (alto - cy)**2,
            (ancho - cx)**2 + (alto - cy)**2)
    )

    num_segmentos = 900

    print(f"Generando {num_lineas} círculos con grosor variable...")

    # Crear rectángulo del canvas para operación booleana
    canvas_rect = box(0, 0, ancho, alto)

    # Calcular escala píxel a mm
    escala_pixel_a_mm = ancho / ancho_mm
    marco_width_pixels = MARCO_WIDTH_MM * escala_pixel_a_mm

    print(f"Escala: {escala_pixel_a_mm:.2f} píxeles/mm")
    print(f"Ancho del marco: {marco_width_pixels:.2f} píxeles ({MARCO_WIDTH_MM}mm)")

    # Crear marco con 4 rectángulos en los bordes
    marco_superior = box(0, 0, ancho, marco_width_pixels)
    marco_inferior = box(0, alto - marco_width_pixels, ancho, alto)
    marco_izquierdo = box(0, 0, marco_width_pixels, alto)
    marco_derecho = box(ancho - marco_width_pixels, 0, ancho, alto)

    marco = unary_union([marco_superior, marco_inferior, marco_izquierdo, marco_derecho])

    # Lista para acumular todos los polígonos
    todos_los_poligonos = [marco]

    # Solo añadir separadores si dividir_paneles == True
    if dividir_paneles:
        # Calcular ancho de las líneas separadoras en píxeles
        linea_sep_pixels = LINEA_SEPARADORA_MM * escala_pixel_a_mm
        print(f"Ancho líneas separadoras: {linea_sep_pixels:.2f} píxeles ({LINEA_SEPARADORA_MM}mm)")

        # Crear líneas separadoras entre paneles
        lineas_separadoras = []

        # Líneas VERTICALES (entre columnas)
        if cols == 3:
            # 3x2 (horizontal): Dos líneas verticales a 217.7mm y 435.4mm
            x_pos_1_pixels = PANEL_SIZE_MM * escala_pixel_a_mm
            x_pos_2_pixels = PANEL_SIZE_MM * 2 * escala_pixel_a_mm

            linea_vertical_1 = box(
                x_pos_1_pixels - linea_sep_pixels / 2,
                0,
                x_pos_1_pixels + linea_sep_pixels / 2,
                alto
            )
            linea_vertical_2 = box(
                x_pos_2_pixels - linea_sep_pixels / 2,
                0,
                x_pos_2_pixels + linea_sep_pixels / 2,
                alto
            )
            lineas_separadoras.append(linea_vertical_1)
            lineas_separadoras.append(linea_vertical_2)
        else:
            # 2x3 (vertical): Una línea vertical a 217.7mm
            x_pos_pixels = PANEL_SIZE_MM * escala_pixel_a_mm
            linea_vertical = box(
                x_pos_pixels - linea_sep_pixels / 2,
                0,
                x_pos_pixels + linea_sep_pixels / 2,
                alto
            )
            lineas_separadoras.append(linea_vertical)

        # Líneas HORIZONTALES (entre filas)
        if rows == 2:
            # 3x2 (horizontal): Una línea horizontal a 217.7mm
            y_pos_pixels = PANEL_SIZE_MM * escala_pixel_a_mm
            linea_horizontal = box(
                0,
                y_pos_pixels - linea_sep_pixels / 2,
                ancho,
                y_pos_pixels + linea_sep_pixels / 2
            )
            lineas_separadoras.append(linea_horizontal)
        else:
            # 2x3 (vertical): Dos líneas horizontales a 217.7mm y 435.4mm
            y_pos_1_pixels = PANEL_SIZE_MM * escala_pixel_a_mm
            y_pos_2_pixels = PANEL_SIZE_MM * 2 * escala_pixel_a_mm

            linea_horizontal_1 = box(
                0,
                y_pos_1_pixels - linea_sep_pixels / 2,
                ancho,
                y_pos_1_pixels + linea_sep_pixels / 2
            )
            linea_horizontal_2 = box(
                0,
                y_pos_2_pixels - linea_sep_pixels / 2,
                ancho,
                y_pos_2_pixels + linea_sep_pixels / 2
            )
            lineas_separadoras.append(linea_horizontal_1)
            lineas_separadoras.append(linea_horizontal_2)

        separadores = unary_union(lineas_separadoras)
        todos_los_poligonos.append(separadores)

        print(f"Líneas separadoras: {cols - 1} verticales + {rows - 1} horizontales")

    total_puntos_antes = 0
    total_puntos_despues = 0
    circulos_completos = 0
    circulos_cortados = 0
    circulos_descartados = 0

    # Generar cada círculo
    for i in range(num_lineas):
        radio = radio_max * (i + 1) / num_lineas

        if not circulo_intersecta_canvas(cx, cy, radio, grosor_max, ancho, alto):
            circulos_descartados += 1
            continue

        # Recopilar intensidades
        intensidades_circulo = []
        for j in range(num_segmentos):
            angulo_medio = 2 * np.pi * (j + 0.5) / num_segmentos
            x = int(cx + radio * np.cos(angulo_medio))
            y = int(cy + radio * np.sin(angulo_medio))

            if 0 <= x < ancho and 0 <= y < alto:
                intensidad = imagen_array[y, x]
            else:
                intensidad = 255

            intensidades_circulo.append(intensidad)

        intensidades_suavizadas = suavizar_valores(intensidades_circulo, ventana=1)

        # Convertir a grosores
        grosores = []
        for intensidad in intensidades_suavizadas:
            factor = 1.0 - (intensidad / 255.0)
            grosor = grosor_min + (grosor_max - grosor_min) * factor
            grosores.append(grosor)

        # Calcular puntos
        puntos_exterior = []
        puntos_interior = []

        for j in range(num_segmentos):
            angulo = 2 * np.pi * j / num_segmentos
            grosor_actual = grosores[j]

            radio_interior = radio - grosor_actual / 2
            radio_exterior = radio + grosor_actual / 2

            x_ext = cx + radio_exterior * np.cos(angulo)
            y_ext = cy + radio_exterior * np.sin(angulo)
            puntos_exterior.append((x_ext, y_ext))

            x_int = cx + radio_interior * np.cos(angulo)
            y_int = cy + radio_interior * np.sin(angulo)
            puntos_interior.append((x_int, y_int))

        # Optimizar puntos
        total_puntos_antes += len(puntos_exterior)
        puntos_ext_opt, puntos_int_opt, _ = optimizar_puntos(
            puntos_exterior, puntos_interior, grosores, tolerancia=0.01
        )
        total_puntos_despues += len(puntos_ext_opt)

        # Crear polígono del anillo
        poligono_anillo = crear_poligono_anillo(puntos_ext_opt, puntos_int_opt)

        if poligono_anillo is None or poligono_anillo.is_empty:
            circulos_descartados += 1
            continue

        # OPERACIÓN BOOLEANA: Intersección con el canvas
        try:
            poligono_recortado = poligono_anillo.intersection(canvas_rect)

            if poligono_recortado.is_empty:
                circulos_descartados += 1
                continue

            if poligono_recortado.area < poligono_anillo.area * 0.99:
                circulos_cortados += 1
            else:
                circulos_completos += 1

            todos_los_poligonos.append(poligono_recortado)

        except Exception as e:
            print(f"  Advertencia: Error procesando círculo {i}: {e}")
            circulos_descartados += 1
            continue

        if (i + 1) % 50 == 0:
            print(f"  Procesados {i + 1}/{num_lineas} círculos...")

    # UNIÓN BOOLEANA FINAL
    print("Realizando unión booleana final...")
    geometria_completa = unary_union(todos_los_poligonos)
    print("✓ Unión booleana exitosa")

    # GUARDAR ARCHIVO COMPLETO
    print(f"\nGuardando archivo completo: {output_path}")
    escribir_svg(output_path, ancho, alto, ancho_mm, alto_mm, geometria_completa)
    print(f"✓ SVG completo guardado")

    # Si no dividir paneles, terminar aquí
    if not dividir_paneles:
        print(f"\n✓ Generación completa (archivo único)")
        # Estadísticas
        if total_puntos_antes > 0:
            reduccion = 100 * (1 - total_puntos_despues / total_puntos_antes)
            print(f"\nEstadísticas:")
            print(f"  Puntos antes: {total_puntos_antes}")
            print(f"  Puntos después: {total_puntos_despues}")
            print(f"  Reducción de puntos: {reduccion:.1f}%")
            print(f"  Círculos completos: {circulos_completos}")
            print(f"  Círculos cortados: {circulos_cortados}")
            print(f"  Círculos descartados: {circulos_descartados}")
        return

    # CREAR CARPETA PARA PANELES
    base_name = os.path.splitext(output_path)[0]
    panels_dir = base_name
    os.makedirs(panels_dir, exist_ok=True)
    print(f"\nCarpeta para paneles: {panels_dir}/")

    # CALCULAR DIMENSIONES DE CADA PANEL EN PÍXELES
    panel_width_pixels = PANEL_SIZE_MM * escala_pixel_a_mm
    panel_height_pixels = PANEL_SIZE_MM * escala_pixel_a_mm

    # GENERAR LOS 6 PANELES
    print(f"\nGenerando {cols * rows} paneles individuales...")
    panel_num = 1

    for row in range(rows):
        for col in range(cols):
            # Calcular rectángulo de corte para este panel
            x_min = col * panel_width_pixels
            y_min = row * panel_height_pixels
            x_max = x_min + panel_width_pixels
            y_max = y_min + panel_height_pixels

            panel_rect = box(x_min, y_min, x_max, y_max)

            # Cortar la geometría completa con el rectángulo del panel
            panel_geom = geometria_completa.intersection(panel_rect)

            if not panel_geom.is_empty:
                # Trasladar la geometría al origen (0,0)
                panel_geom_trasladado = translate(panel_geom, -x_min, -y_min)

                # Guardar SVG del panel
                panel_svg_path = os.path.join(panels_dir, f"panel_{panel_num}.svg")
                escribir_svg(
                    panel_svg_path,
                    panel_width_pixels,
                    panel_height_pixels,
                    PANEL_SIZE_MM,
                    PANEL_SIZE_MM,
                    panel_geom_trasladado
                )
                print(f"  ✓ Panel {panel_num}: {panel_svg_path}")
            else:
                print(f"  ⚠ Panel {panel_num} vacío (omitido)")

            panel_num += 1

    # Estadísticas
    if total_puntos_antes > 0:
        reduccion = 100 * (1 - total_puntos_despues / total_puntos_antes)
        print(f"\nEstadísticas:")
        print(f"  Puntos antes: {total_puntos_antes}")
        print(f"  Puntos después: {total_puntos_despues}")
        print(f"  Reducción de puntos: {reduccion:.1f}%")
        print(f"  Círculos completos: {circulos_completos}")
        print(f"  Círculos cortados: {circulos_cortados}")
        print(f"  Círculos descartados: {circulos_descartados}")

    print(f"\n✓ Generación completa!")
    print(f"✓ 1 archivo completo: {output_path}")
    print(f"✓ 6 archivos SVG en: {panels_dir}/")


def main():
    parser = argparse.ArgumentParser(
        description='Circular Lines Generator - Genera círculos concéntricos a partir de imágenes',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  %(prog)s imagen.jpg -o salida.svg
  %(prog)s imagen.jpg -n 500 -min 0.5 -max 5.0 -c 75
  %(prog)s imagen.jpg -cx 50 -cy 30 -n 300
  %(prog)s imagen.jpg -o salida.svg --no-dividir  (solo archivo único)

Características:
  - Dimensiones físicas: 217.7mm x 217.7mm por panel (6 paneles total)
  - Marco de 3.2mm y líneas separadoras de 2.8mm
  - Optimización automática de puntos
  - Operaciones booleanas para recorte preciso
        """
    )

    parser.add_argument('imagen', help='Ruta de la imagen de entrada (blanco y negro)')
    parser.add_argument('-o', '--output', default='salida.svg', help='Archivo SVG salida (default: salida.svg)')
    parser.add_argument('-n', '--num-lineas', type=int, default=120, help='Número de círculos (default: 120)')
    parser.add_argument('-min', '--grosor-min', type=float, default=6.0, help='Grosor mínimo (default: 6.0)')
    parser.add_argument('-max', '--grosor-max', type=float, default=16.0, help='Grosor máximo (default: 16.0)')
    parser.add_argument('-c', '--contraste', type=float, default=75.0, help='Contraste: 50=neutro (default: 75)')
    parser.add_argument('-cx', '--centro-x', type=float, default=-20.0, help='Centro X en % (default: -20)')
    parser.add_argument('-cy', '--centro-y', type=float, default=50.0, help='Centro Y en % (default: 50)')
    parser.add_argument('--no-dividir', action='store_true', help='Solo generar archivo completo, sin paneles')

    args = parser.parse_args()

    if args.num_lineas < 1:
        print("Error: El número de líneas debe ser al menos 1", file=sys.stderr)
        sys.exit(1)

    if args.grosor_min < 0 or args.grosor_max < 0:
        print("Error: Los grosores no pueden ser negativos", file=sys.stderr)
        sys.exit(1)

    if args.grosor_min > args.grosor_max:
        print("Error: El grosor mínimo no puede ser mayor que el máximo", file=sys.stderr)
        sys.exit(1)

    try:
        generar_svg_circular(
            args.imagen,
            args.num_lineas,
            args.grosor_min,
            args.grosor_max,
            args.contraste,
            args.centro_x,
            args.centro_y,
            args.output,
            dividir_paneles=not args.no_dividir
        )
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo '{args.imagen}'", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
