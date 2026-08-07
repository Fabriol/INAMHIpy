import os
import math
import unicodedata
import pikepdf
from flask import render_template
from weasyprint import HTML, CSS
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils import generic

_MARGEN_PDF_PT = 24
_ALTO_CAMPO_EDITABLE_PT = 10
_TAM_FUENTE_MIN_PT = 4.5

# Migración a "casillas de formulario PDF reales": estos campos ya se pueden
# llenar antes O después de cualquier firma, sin romper firmas ya estampadas,
# porque se actualizan con una revisión incremental (nunca se regenera el PDF
# completo). Ver hoja_espejo.html: cada uno tiene su propio marcador
# id="espejo_campo_<nombre>".
#
# Etapa 2 (ampliación): originalmente solo se migraron los campos con una
# celda de tabla completa para ellos solos, porque WeasyPrint solo reporta
# una posición confiable para bookmark-label/bookmark-level del ÚNICO
# marcador dentro de cada celda/bloque: en cuanto hay un SEGUNDO marcador
# compartiendo esa celda (misma línea, o incluso otra línea tras un <br>
# pero dentro de la misma celda), su posición reportada queda mal — a veces
# apenas desplazada (el campo se ve truncado de más) y a veces tan mal que
# ni siquiera es mayor que la posición del campo anterior, lo que hace
# fallar la detección de límite y termina extendiendo esa casilla casi
# hasta el margen de la página, tapando columnas vecinas (incluida la de
# FIRMA ELECTRÓNICA — probado con admin_valor_bienes).
#
# Etapa 3: en vez de resignarse a dejar esos campos sin migrar, se separó
# cada "Etiqueta: <span>" de una celda combinada en su propio contenedor
# inline-block (clase .ep-inl en hoja_espejo.html). Con eso cada campo
# vuelve a ser el ÚNICO marcador dentro de SU bloque (aunque varios bloques
# convivan uno al lado del otro en la misma celda/línea visual), así que su
# posición vuelve a ser confiable — verificado comparando la posición
# reportada por el marcador contra la posición real del texto renderizado.
# Con esto se migró el 100% de los campos de hoja_espejo.html.
CAMPOS_ANCHO_COMPLETO = {
    'nombres_apellidos', 'cedula', 'modalidad', 'fecha_ingreso', 'fecha_salida', 'email1', 'email2',
    'direccion', 'numero_domicilio', 'provincia', 'canton', 'celular', 'emergencia',
    'lugar_trabajo', 'grupo_ocupacional', 'unidad', 'cargo',
    'tramites_nombre_resp1', 'tramites_nombre_resp2', 'tramites_nombre_resp3', 'tramites_nombre_responsable',
    'tramites_admin_contrato', 'tramites_desc_contrato', 'tramites_memo',
    'tramites_jefe_inmediato', 'tramites_servidor_recibe', 'tramites_obs',
    'admin_nombre_resp1', 'admin_nombre_resp2', 'admin_nombre_resp3', 'admin_nombre_resp4', 'admin_responsable',
    'admin_es_contrato', 'admin_valor_bienes', 'admin_acta_bienes', 'admin_deducibles_valor', 'admin_pasajes_valor',
    'tic_nombre_resp1', 'tic_nombre_resp2', 'tic_nombre_resp3', 'tic_nombre_resp4', 'tic_responsable',
    'tic_ip_fija', 'tic_liberacion', 'tic_obs1', 'tic_ruta_backup',
    'tic_cierre_correo', 'tic_quipux', 'tic_esigef', 'tic_spryn', 'tic_esbye', 'tic_obs',
    'fin_nombre_resp1', 'fin_nombre_resp2', 'fin_nombre_resp3', 'fin_nombre_resp4', 'fin_director',
    'fin_saldos_valor', 'fin_obs1', 'fin_anticipo_valor', 'fin_obs2',
    'fin_recuperacion_valor', 'fin_obs3', 'fin_devolucion_valor', 'fin_obs4',
    'seg_nombre_resp1', 'seg_nombre_resp2', 'seg_responsable', 'seg_entrega_copia', 'seg_verificacion_info', 'seg_oficial',
    'rrhh_resp_capacitacion', 'rrhh_resp_evaluacion', 'rrhh_resp_viajes', 'rrhh_resp_siith',
    'rrhh_resp_vacaciones', 'rrhh_resp_juramentada', 'rrhh_resp_credencial2', 'rrhh_resp_acta', 'rrhh_director',
    'rrhh_cursos_eval', 'rrhh_num_certificado', 'rrhh_num_declaracion',
    'rrhh_respaldo_cd', 'rrhh_ropa_trabajo',
    'recepcion_fecha', 'recepcion_hojas', 'recepcion_servidor', 'recepcion_cargo',
    'cedula_firmante', 'fecha_firma',
}

# Badges Sí/No que deben conservar el color (ver .ep-yn / .ep-yn--s /
# .ep-yn--n en hoja_espejo.html). Ancho fijo (34pt): su contenido siempre es
# "SI" o "NO", nunca varía de longitud, así que nunca chocan con nada.
CAMPOS_SI_NO_COLOR = {
    'tramites_informe', 'tramites_quipux_cero', 'tramites_fe_presentacion',
    'tramites_claves_asignadas', 'tramites_losep', 'tramites_acta_claves',
    'admin_informe', 'admin_bienes', 'admin_deducibles', 'admin_pasajes',
    'tic_verificacion', 'tic_backup', 'tic_retiro_acceso', 'tic_tarjeta_cuentas',
    'fin_saldos', 'fin_anticipo', 'fin_recuperacion', 'fin_devolucion',
    'seg_archivos', 'seg_archivos_fisicos',
    'rrhh_capacitacion', 'rrhh_evaluacion', 'rrhh_viajes', 'rrhh_siith',
    'rrhh_juramentada', 'rrhh_credencial', 'rrhh_acta_bienes',
}

# Campos de ancho fijo corto (no son Sí/No, pero su valor siempre es un
# número pequeño — ej. días de vacaciones). 'rrhh_vacaciones' ocupa la
# posición de la columna S/N pero con un dato real; el siguiente marcador
# de su fila (rrhh_num_certificado) queda DESPUÉS de la etiqueta "Cert:",
# así que acotar contra él (como se hace para el resto de campos de ancho
# completo) deja esa etiqueta dentro de la casilla. Con ancho fijo chico,
# alcanza de sobra para 1-3 dígitos y nunca necesita ese límite.
CAMPOS_ANCHO_FIJO_CORTO = {'rrhh_vacaciones'}

# Límite derecho manual para campos que cierran la ÚLTIMA línea de su celda
# antes de un <br> (ej. "...Memo: X<br>Jefe Inmediato: ..."): el siguiente
# marcador en el documento queda en la línea de ABAJO (Y distinto), así que
# _inyectar_campos_editables no lo acepta como límite de la misma fila y esa
# casilla cae al modo "extender casi hasta el margen", invadiendo la columna
# RESPONSABLE de su fila. Acá se indica explícitamente contra qué campo
# RESPONSABLE (siempre confiable: único marcador de su celda) debe acotarse
# cada uno de estos campos, sin depender de que su Y coincida con el de nadie.
LIMITE_DERECHO_MANUAL = {
    'tramites_memo': 'tramites_nombre_responsable',
    'tramites_obs': 'tramites_nombre_responsable',
    'tic_liberacion': 'tic_nombre_resp1',
    'tic_obs1': 'tic_nombre_resp1',
    'tic_quipux': 'tic_nombre_resp3',
    'tic_spryn': 'tic_nombre_resp3',
    'tic_esbye': 'tic_nombre_resp3',
    # 'cedula_firmante' -> marcador-guía 'fecha_firma_b': en esta línea (fuera
    # de una tabla, a font-size:8px) el span vacío reporta un Y ~8pt distinto
    # al de sus vecinos — por encima de TOLERANCIA_MISMA_FILA_PT — así que la
    # detección automática lo descarta aunque su X sí sea confiable.
    'cedula_firmante': 'fecha_firma_b',
}

CAMPOS_EDITABLES_ACROFORM = CAMPOS_ANCHO_COMPLETO | CAMPOS_SI_NO_COLOR | CAMPOS_ANCHO_FIJO_CORTO


def _valor_o_defecto(valor):
    """Replica el 'default(...)' que usa hoja_espejo.html para cada campo
    (ver partials/hoja_espejo.html): si no hay valor, se muestra '-'. Sin
    esto, un campo vacío se dibuja como una casilla en blanco invisible en
    vez del guion que el usuario espera ver. Se usa '-' (no '—') porque la
    apariencia se codifica en latin-1 y el guion largo no es representable."""
    valor = (valor or '').strip() if valor else ''
    return valor if valor else '-'

# Colores exactos de .ep-yn--s / .ep-yn--n en hoja_espejo.html, convertidos a RGB 0-1
_COLOR_BADGE_SI = ((0.863, 0.988, 0.906), (0.133, 0.773, 0.369), (0.086, 0.396, 0.204))
_COLOR_BADGE_NO = ((0.996, 0.886, 0.886), (0.937, 0.267, 0.267), (0.6, 0.106, 0.106))
_COLOR_BADGE_NEUTRO = ((1, 1, 1), (0.792, 0.835, 0.882), (0, 0, 0))

# Anchos aproximados de Helvetica (tabla AFM estándar, en 1/1000 em) para poder
# calcular cuánto mide un texto ANTES de dibujarlo: el BBox del Form XObject
# de cada casilla recorta (clip) cualquier trazo que se pase de su ancho, así
# que sin esta tabla un nombre largo en una columna angosta (ej. RESPONSABLE)
# se dibuja igual pero la mitad queda invisible fuera del recorte.
_ANCHO_HELV_1000 = {
    ' ': 278, '!': 278, '"': 333, '#': 556, '$': 556, '%': 889, '&': 722, "'": 191,
    '(': 333, ')': 333, '*': 389, '+': 584, ',': 278, '-': 333, '.': 278, '/': 278,
    '0': 556, '1': 556, '2': 556, '3': 556, '4': 556, '5': 556, '6': 556, '7': 556,
    '8': 556, '9': 556, ':': 333, ';': 278, '<': 584, '=': 584, '>': 584, '?': 556,
    '@': 1015,
    'A': 667, 'B': 667, 'C': 722, 'D': 722, 'E': 667, 'F': 611, 'G': 778, 'H': 722,
    'I': 278, 'J': 500, 'K': 667, 'L': 556, 'M': 833, 'N': 722, 'O': 778, 'P': 667,
    'Q': 778, 'R': 722, 'S': 667, 'T': 611, 'U': 722, 'V': 667, 'W': 944, 'X': 667,
    'Y': 667, 'Z': 611,
    '[': 278, '\\': 278, ']': 278, '^': 469, '_': 556,
    'a': 556, 'b': 556, 'c': 500, 'd': 556, 'e': 556, 'f': 278, 'g': 556, 'h': 556,
    'i': 222, 'j': 222, 'k': 500, 'l': 222, 'm': 833, 'n': 556, 'o': 556, 'p': 556,
    'q': 556, 'r': 333, 's': 500, 't': 278, 'u': 556, 'v': 500, 'w': 722, 'x': 500,
    'y': 500, 'z': 500,
}
_ANCHO_HELV_DEFECTO = 600


def _ancho_texto_1000(texto):
    """Ancho aproximado de 'texto' en Helvetica, en unidades de 1/1000 em. Los
    caracteres acentuados (á, ñ, ü...) no están en la tabla: se normalizan a
    su letra base (NFKD) porque el ancho real difiere en menos de un 5%,
    suficiente para decidir cuánto encoger la fuente."""
    total = 0
    for ch in texto:
        ancho = _ANCHO_HELV_1000.get(ch)
        if ancho is None:
            base = unicodedata.normalize('NFKD', ch)[:1]
            ancho = _ANCHO_HELV_1000.get(base, _ANCHO_HELV_DEFECTO)
        total += ancho
    return total


def _ancho_texto_pt(texto, tam_fuente):
    return _ancho_texto_1000(texto) * tam_fuente / 1000.0


# CMap /ToUnicode para la fuente Helvetica/WinAnsiEncoding de las casillas:
# sin esto, el texto dibujado a mano en cada apariencia se ve bien pero no es
# "texto real" para un lector de PDF — copiar/buscar/verificar accesibilidad
# no recupera los caracteres (equivale a una imagen para esas herramientas).
# Mapeo identidad 0x20-0xFF: WinAnsiEncoding coincide con Latin-1/Unicode en
# todo el rango que esta app realmente usa (letras, números, puntuación,
# vocales acentuadas y ñ/Ñ del español), así que no hace falta una tabla más
# fina. No cambia el aspecto del PDF ni toca nada relacionado con la firma.
_CMAP_TOUNICODE_LATIN1 = b'''/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def
/CMapName /Adobe-Identity-UCS def
/CMapType 2 def
1 begincodespacerange
<20><FF>
endcodespacerange
1 beginbfrange
<20><FF> <0020>
endbfrange
endcmap
CMapName currentdict /CMap defineresource pop
end
end'''


def _contenido_apariencia_campo(ancho, alto, texto, es_badge):
    """
    Genera el contenido de una apariencia de PDF (texto plano en fondo
    blanco, o badge de color para Sí/No) dibujado a mano, SIN depender de
    NeedAppearances. Esto evita que quede transparente y se vea el texto
    viejo por debajo cuando se actualiza un campo despues de generado.
    Devuelve bytes listos para un Form XObject con BBox [0 0 ancho alto].
    """
    texto = (texto or '').strip()
    if es_badge:
        texto_norm = texto.upper()
        if texto_norm == 'SI':
            bg, borde, color_txt = _COLOR_BADGE_SI
        elif texto_norm == 'NO':
            bg, borde, color_txt = _COLOR_BADGE_NO
        else:
            bg, borde, color_txt = _COLOR_BADGE_NEUTRO
    else:
        texto_norm = texto
        bg, borde, color_txt = (1, 1, 1), None, (0, 0, 0)

    lineas = ['q', f'{bg[0]:.3f} {bg[1]:.3f} {bg[2]:.3f} rg']
    if borde:
        lineas.append(f'{borde[0]:.3f} {borde[1]:.3f} {borde[2]:.3f} RG')
        lineas.append('0.6 w')
        lineas.append(f'0.3 0.3 {max(0.1, ancho - 0.6):.2f} {max(0.1, alto - 0.6):.2f} re')
        lineas.append('B')
    else:
        lineas.append(f'0 0 {ancho:.2f} {alto:.2f} re')
        lineas.append('f')
    lineas.append('Q')

    if texto_norm:
        tam_fuente_max = round(alto * 0.62, 2)
        texto_dibujar = texto_norm

        if es_badge:
            # Los badges siempre son "SI"/"NO": nunca necesitan encogerse.
            tam_fuente = tam_fuente_max
        else:
            # El BBox del Form XObject recorta cualquier trazo que se pase de
            # 'ancho' (es el comportamiento normal de un PDF, no un bug del
            # visor), así que un valor largo en una casilla angosta (ej. el
            # responsable de una fila) se dibujaba a tamaño fijo y quedaba
            # cortado a la mitad sin avisar. Primero se encoge la fuente
            # hasta que quepa completo; si ni al tamaño mínimo legible entra,
            # recién ahí se trunca con "..." (mejor un recorte visible que
            # texto invisible perdido).
            ancho_util = max(ancho - 4.0, 4.0)  # 2pt de aire a cada lado
            ancho_1000 = _ancho_texto_1000(texto_dibujar)
            tam_fuente = tam_fuente_max
            if ancho_1000 and (ancho_1000 * tam_fuente_max / 1000.0) > ancho_util:
                # floor (no round) a 2 decimales: redondear al más cercano
                # puede pasarse por una centésima de punto del ancho real
                # disponible y disparar el truncado de más abajo con texto
                # que en realidad SÍ cabía completo.
                tam_ideal = math.floor(ancho_util * 1000.0 / ancho_1000 * 100) / 100
                tam_fuente = max(_TAM_FUENTE_MIN_PT, min(tam_fuente_max, tam_ideal))
            if _ancho_texto_pt(texto_dibujar, tam_fuente) > ancho_util:
                elipsis = '...'
                ancho_elipsis = _ancho_texto_pt(elipsis, tam_fuente)
                recorte = texto_dibujar
                while recorte and _ancho_texto_pt(recorte, tam_fuente) + ancho_elipsis > ancho_util:
                    recorte = recorte[:-1]
                texto_dibujar = (recorte.rstrip() + elipsis) if recorte else texto_dibujar[:1]

        texto_escapado = texto_dibujar.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')
        y_texto = max(1.0, (alto - tam_fuente) / 2 + tam_fuente * 0.14)
        if es_badge:
            ancho_texto_aprox = _ancho_texto_pt(texto_dibujar, tam_fuente)
            x_texto = max(1.0, (ancho - ancho_texto_aprox) / 2)
        else:
            x_texto = 2.0
        lineas += [
            'BT', f'/Helv {tam_fuente} Tf',
            f'{color_txt[0]:.3f} {color_txt[1]:.3f} {color_txt[2]:.3f} rg',
            f'{x_texto:.2f} {y_texto:.2f} Td', f'({texto_escapado}) Tj', 'ET',
        ]

    return '\n'.join(lineas).encode('latin-1', errors='replace')


def _ancho_campo(nombre_campo, x, ancho_pagina, limite_derecho=None):
    """
    Ancho de la casilla: los badges Sí/No y los campos de ancho fijo corto
    (ver CAMPOS_SI_NO_COLOR / CAMPOS_ANCHO_FIJO_CORTO) usan un ancho fijo
    pequeño, ignorando cualquier límite calculado. Los campos de celda
    completa usan el borde izquierdo del siguiente elemento de su misma fila
    (otra celda de datos o la columna FIRMA ELECTRÓNICA) como límite (ver
    limites_derecho en _inyectar_campos_editables) cuando existe; si son la
    última celda de su fila (ej. UNIDAD, CARGO), se extienden casi hasta el
    margen de la página.
    """
    if nombre_campo in CAMPOS_SI_NO_COLOR:
        return 34
    if nombre_campo in CAMPOS_ANCHO_FIJO_CORTO:
        return 20
    if limite_derecho is not None:
        return max(30, limite_derecho - x - 4)
    return max(60, (ancho_pagina - _MARGEN_PDF_PT) - x - 2)


def _inyectar_campos_editables(ruta_pdf, datos_diccionario):
    """
    Convierte cada celda marcada con id="espejo_campo_<nombre>" (ver CSS
    bookmark-label en generar_documento_paz_salvo) en una casilla de
    formulario PDF real (AcroForm text field), con el valor actual ya
    guardado en la base de datos. A partir de aquí, ese campo se puede
    seguir llenando con actualizar_campo_pdf_incremental() sin volver a
    generar el documento — así que puede llenarse antes O después de
    cualquier firma, sin arriesgar las firmas ya estampadas.
    """
    with pikepdf.open(ruta_pdf, allow_overwriting_input=True) as pdf:
        outline = pdf.open_outline()

        def recorrer(items):
            for item in items:
                yield item
                yield from recorrer(item.children)

        # Se recorren TODOS los marcadores (espejo_campo_ Y espejo_firma_) en
        # el orden en que aparecen en el documento: cada celda de datos va
        # seguida, en la misma fila, de otra celda o de la columna FIRMA
        # ELECTRÓNICA (ver firma_espejo() macro). Así se puede acotar el
        # ancho de la casilla al límite real de su columna en vez de
        # extenderla hasta el margen de la página, que termina pintando su
        # fondo blanco encima del contenido vecino.
        marcadores = []
        for item in recorrer(outline.root):
            if not item.title or not item.destination:
                continue
            if not (item.title.startswith('espejo_campo_') or item.title.startswith('espejo_firma_')):
                continue
            dest = item.destination
            pagina = pdf.pages.index(dest[0])
            marcadores.append((item.title, pagina, float(dest[2]), float(dest[3])))

        # Umbral para decidir si dos celdas de DATOS (no firma) están en la
        # misma fila: se calibró con las filas reales de hoja_espejo.html,
        # donde el desfase Y entre celdas vecinas de una misma fila es de
        # ~0-6pt (variación de fuente/peso), mientras que entre una fila y
        # la siguiente hay al menos ~12pt. Para el caso "campo seguido de su
        # columna FIRMA ELECTRÓNICA" no se aplica este umbral (ver abajo):
        # la caja de firma mide 60px de alto y puede desplazar su marcador
        # bastante más que eso dentro de la misma fila.
        TOLERANCIA_MISMA_FILA_PT = 6

        posiciones = {}
        # Todas las posiciones espejo_campo_* (migradas o no, incluidos los
        # marcadores-guía "_th"/"_b" sin dato propio): LIMITE_DERECHO_MANUAL
        # necesita poder referenciar un marcador-guía, que nunca aparece en
        # 'posiciones' porque no tiene casilla propia.
        todas_posiciones = {}
        limites_derecho = {}
        for i, (titulo, pagina, x, y) in enumerate(marcadores):
            if not titulo.startswith('espejo_campo_'):
                continue
            nombre_campo = titulo[len('espejo_campo_'):]
            todas_posiciones[nombre_campo] = (pagina, x, y)
            # Solo se inyecta casilla para los campos migrados (ver
            # CAMPOS_EDITABLES_ACROFORM); el resto de marcadores en
            # hoja_espejo.html quedan como texto normal, sin tocar
            if nombre_campo not in CAMPOS_EDITABLES_ACROFORM:
                continue
            posiciones[nombre_campo] = (pagina, x, y)

            if i + 1 < len(marcadores):
                sig_titulo, sig_pagina, sig_x, sig_y = marcadores[i + 1]
                es_firma = sig_titulo.startswith('espejo_firma_')
                # El siguiente marcador acota el ancho de la casilla si está
                # en la misma fila, a su derecha — sea la columna de FIRMA
                # ELECTRÓNICA (comportamiento original, sin chequeo de Y: la
                # caja de firma es alta y su marcador se desplaza dentro de
                # la fila) o la siguiente celda de datos (ej. CÉDULA seguida
                # de MODALIDAD, o LUGAR TRABAJO seguida de GRUPO OCUPACIONAL,
                # acotadas con TOLERANCIA_MISMA_FILA_PT). Antes solo se
                # consideraba una firma como límite, así que esos otros
                # campos se extendían de más y su fondo blanco terminaba
                # pisando la celda vecina.
                misma_fila = sig_pagina == pagina and sig_x > x and (
                    es_firma or abs(sig_y - y) <= TOLERANCIA_MISMA_FILA_PT
                )
                if misma_fila:
                    limites_derecho[nombre_campo] = sig_x

        # Ver LIMITE_DERECHO_MANUAL: casos conocidos donde el límite
        # automático (arriba) no aplica, sea porque el siguiente marcador
        # queda en otra línea dentro de la misma celda, o porque un
        # marcador-guía vacío quedó fuera de TOLERANCIA_MISMA_FILA_PT.
        for nombre_campo, campo_referencia in LIMITE_DERECHO_MANUAL.items():
            ref = todas_posiciones.get(campo_referencia)
            propio = posiciones.get(nombre_campo)
            if ref is not None and propio is not None and ref[0] == propio[0]:
                limites_derecho[nombre_campo] = ref[1]

        if not posiciones:
            return

        root = pdf.Root
        if '/AcroForm' not in root:
            root.AcroForm = pdf.make_indirect(pikepdf.Dictionary(Fields=pikepdf.Array([]), SigFlags=3))
        root.AcroForm.NeedAppearances = False  # la apariencia se dibuja a mano, no se delega al visor

        tounicode = pikepdf.Stream(pdf, _CMAP_TOUNICODE_LATIN1)
        fuente_helv = pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name('/Font'), Subtype=pikepdf.Name('/Type1'),
            BaseFont=pikepdf.Name('/Helvetica'), Encoding=pikepdf.Name('/WinAnsiEncoding'),
            ToUnicode=pdf.make_indirect(tounicode),
        ))

        for nombre_campo, (pagina, x, y) in posiciones.items():
            pagina_obj = pdf.pages[pagina]
            ancho_pagina = float(pagina_obj.MediaBox[2])
            es_badge = nombre_campo in CAMPOS_SI_NO_COLOR
            ancho_campo = _ancho_campo(nombre_campo, x, ancho_pagina, limites_derecho.get(nombre_campo))
            alto_campo = _ALTO_CAMPO_EDITABLE_PT
            rect = pikepdf.Array([x, y - alto_campo, x + ancho_campo, y])

            valor_actual = _valor_o_defecto(datos_diccionario.get(nombre_campo))

            contenido = _contenido_apariencia_campo(ancho_campo, alto_campo, valor_actual, es_badge)
            apariencia = pikepdf.Stream(pdf, contenido)
            apariencia.Type = pikepdf.Name('/XObject')
            apariencia.Subtype = pikepdf.Name('/Form')
            apariencia.BBox = pikepdf.Array([0, 0, ancho_campo, alto_campo])
            apariencia.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(Helv=fuente_helv))

            widget = pdf.make_indirect(pikepdf.Dictionary(
                Type=pikepdf.Name('/Annot'),
                Subtype=pikepdf.Name('/Widget'),
                FT=pikepdf.Name('/Tx'),
                T=nombre_campo,
                V=str(valor_actual),
                DA='/Helv 7 Tf 0 g',
                Rect=rect,
                AP=pikepdf.Dictionary(N=pdf.make_indirect(apariencia)),
                MK=pikepdf.Dictionary(BG=pikepdf.Array([1, 1, 1])),  # fondo blanco explícito: ningún visor debe inventarle un resaltado propio
                BS=pikepdf.Dictionary(W=0, S=pikepdf.Name('/N')),  # sin borde: evita que algún visor dibuje uno por defecto
                F=4,  # bandera "Print": se imprime pero no se ve como caja editable en pantalla
                Ff=1,  # bandera "ReadOnly": nadie edita el campo a mano abriendo el PDF
            ))

            if '/Annots' not in pagina_obj:
                pagina_obj.Annots = pdf.make_indirect(pikepdf.Array([]))
            pagina_obj.Annots.append(widget)
            root.AcroForm.Fields.append(widget)

        pdf.save(ruta_pdf)


def actualizar_campo_pdf_incremental(ruta_pdf, campo_formulario, valor):
    """
    Actualiza el valor de UNA casilla de formulario PDF ya existente
    (creada por _inyectar_campos_editables) usando una actualización
    incremental real: solo AGREGA una revisión nueva al final del archivo,
    nunca reescribe ni toca las firmas ya estampadas antes. Si el campo no
    existe como casilla de formulario en este PDF (porque todavía no se ha
    migrado a la Etapa 1), no hace nada y devuelve False.
    """
    if not os.path.exists(ruta_pdf):
        return False

    ruta_temporal = ruta_pdf + '.tmp'
    with open(ruta_pdf, 'rb') as inf:
        w = IncrementalPdfFileWriter(inf)

        if '/AcroForm' not in w.root:
            return False
        campos = w.root['/AcroForm'].get('/Fields')
        if campos is None:
            return False

        encontrado = False
        for campo_ref in campos:
            campo_obj = campo_ref.get_object()
            if campo_obj.get('/T') == campo_formulario:
                valor_texto = _valor_o_defecto(str(valor) if valor is not None else '')
                campo_obj['/V'] = generic.TextStringObject(valor_texto)

                rect = campo_obj.get('/Rect')
                ancho_campo = float(rect[2]) - float(rect[0]) if rect else 100.0
                alto_campo = float(rect[3]) - float(rect[1]) if rect else _ALTO_CAMPO_EDITABLE_PT
                es_badge = campo_formulario in CAMPOS_SI_NO_COLOR

                contenido = _contenido_apariencia_campo(ancho_campo, alto_campo, valor_texto, es_badge)
                tounicode_ref = w.add_object(generic.StreamObject(
                    dict_data={}, stream_data=_CMAP_TOUNICODE_LATIN1,
                ))
                fuente_ref = w.add_object(generic.DictionaryObject({
                    generic.NameObject('/Type'): generic.NameObject('/Font'),
                    generic.NameObject('/Subtype'): generic.NameObject('/Type1'),
                    generic.NameObject('/BaseFont'): generic.NameObject('/Helvetica'),
                    generic.NameObject('/Encoding'): generic.NameObject('/WinAnsiEncoding'),
                    generic.NameObject('/ToUnicode'): tounicode_ref,
                }))
                apariencia_ref = w.add_object(generic.StreamObject(
                    dict_data={
                        generic.NameObject('/Type'): generic.NameObject('/XObject'),
                        generic.NameObject('/Subtype'): generic.NameObject('/Form'),
                        generic.NameObject('/BBox'): generic.ArrayObject([
                            generic.NumberObject(0), generic.NumberObject(0),
                            generic.NumberObject(ancho_campo), generic.NumberObject(alto_campo),
                        ]),
                        generic.NameObject('/Resources'): generic.DictionaryObject({
                            generic.NameObject('/Font'): generic.DictionaryObject({
                                generic.NameObject('/Helv'): fuente_ref,
                            }),
                        }),
                    },
                    stream_data=contenido,
                ))
                campo_obj['/AP'] = generic.DictionaryObject({generic.NameObject('/N'): apariencia_ref})
                campo_obj['/MK'] = generic.DictionaryObject({
                    generic.NameObject('/BG'): generic.ArrayObject([
                        generic.NumberObject(1), generic.NumberObject(1), generic.NumberObject(1),
                    ]),
                })

                w.mark_update(campo_ref)
                encontrado = True
                break

        if not encontrado:
            return False

        with open(ruta_temporal, 'wb') as outf:
            w.write(outf)

    os.replace(ruta_temporal, ruta_pdf)
    return True


def _inicializar_acroform_firmaec(ruta_pdf):
    """
    WeasyPrint no crea /AcroForm en el /Root. FirmaEC exige que ese
    diccionario exista con /SigFlags 3 (SignaturesExist | AppendOnly)
    para reconocer los widgets de firma que pyhanko inyecta después
    de forma incremental; si no está, FirmaEC reporta "Documento sin firmas".
    """
    with pikepdf.open(ruta_pdf, allow_overwriting_input=True) as pdf:
        root = pdf.Root
        if '/AcroForm' not in root:
            root.AcroForm = pdf.make_indirect(pikepdf.Dictionary(
                Fields=pikepdf.Array([]),
                SigFlags=3
            ))
        else:
            root.AcroForm.SigFlags = 3
            if '/Fields' not in root.AcroForm:
                root.AcroForm.Fields = pikepdf.Array([])
        pdf.save(ruta_pdf)

def localizar_posicion_firma(ruta_pdf, campo_firma):
    """
    Busca el marcador 'espejo_firma_<campo>' (ver bookmark-label en
    generar_documento_paz_salvo) y devuelve (pagina, x, y, ancho_pagina) del
    punto donde empieza esa celda en el PDF ya renderizado. Devuelve None si
    no se encuentra, para que el llamador pueda usar una firma invisible
    como respaldo sin romper el flujo de firma.
    """
    with pikepdf.open(ruta_pdf) as pdf:
        outline = pdf.open_outline()

        def recorrer(items):
            for item in items:
                yield item
                yield from recorrer(item.children)

        objetivo = f"espejo_firma_{campo_firma}"
        for item in recorrer(outline.root):
            if item.title == objetivo and item.destination:
                dest = item.destination
                pagina = pdf.pages.index(dest[0])
                ancho_pagina = float(pdf.pages[pagina].MediaBox[2])
                return pagina, float(dest[2]), float(dest[3]), ancho_pagina
    return None

def generar_documento_paz_salvo(solicitud, ex_funcionario, respuestas_db, ruta_salida):
    """
    Convierte la plantilla HTML 'hoja_espejo.html' en un documento PDF A4 perfecto.
    """
    # 1. Preparar el diccionario de datos
    datos_diccionario = {}
    for respuesta in respuestas_db:
        if respuesta.campo_formulario:
            datos_diccionario[respuesta.campo_formulario] = respuesta.valor_respuesta

    # 2. Renderizar el HTML de la hoja espejo
    html_interno = render_template(
        'paz_salvo/partials/hoja_espejo.html',
        solicitud=solicitud,
        datos=datos_diccionario,
        current_user=ex_funcionario
    )

    # 3. Envolver en una estructura HTML completa para evitar fallos de renderizado
    html_completo = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Paz y Salvo</title>
    </head>
    <body>
        {html_interno}
    </body>
    </html>
    """

    # 4. Estilos en línea obligatorios para la impresión perfecta en A4.
    # El texto/badge original de cada campo YA MIGRADO (ver CAMPOS_EDITABLES_ACROFORM)
    # se dibuja invisible SOLO en este PDF (nunca en la pantalla web, esta hoja de
    # estilos no se usa ahí): la casilla de formulario que se inyecta después dibuja
    # su propio valor encima. Los campos NO migrados (celdas combinadas) se dejan
    # con su texto normal, visible, como siempre.
    selectores_ocultar = ', '.join(f'#espejo_campo_{c}' for c in CAMPOS_EDITABLES_ACROFORM)
    estilos_base = CSS(string=f'''
        @page {{ size: A4 portrait; margin: 8mm; }}
        body {{ font-family: Arial, sans-serif; background: #fff; margin: 0; padding: 0; }}
        * {{ -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }}
        .ep-tabla tr {{ page-break-inside: avoid; }}
        .ep-bloque__head {{ page-break-after: avoid; }}
        .ep-firma-box, .firmaec-sello {{ page-break-inside: avoid; }}
        /* Marcadores internos (invisibles) para ubicar cada celda de firma al momento de firmar,
           y cada celda de dato editable (espejo_campo_) para convertirla en casilla de
           formulario PDF real que se puede seguir llenando aunque el documento ya tenga firmas */
        [id^="espejo_firma_"], [id^="espejo_campo_"] {{ bookmark-level: 1; bookmark-label: attr(id); }}
        span[id^="espejo_campo_"] {{ display: inline-block; }}
        /* white-space:nowrap: un valor largo NO debe envolver a 2 líneas aquí:
           aunque sea invisible, seguiría ocupando espacio y haría crecer el
           alto de toda la fila, empujando verticalmente (vertical-align:middle)
           a la celda vecina hasta la altura de esta casilla de 1 sola línea,
           quedando tapada por su fondo blanco. Como el valor real lo dibuja la
           casilla PDF (que ya se autoajusta a su ancho), este texto oculto no
           necesita envolver nunca. */
        {selectores_ocultar} {{ color: transparent !important; background: transparent !important; border-color: transparent !important; white-space: nowrap !important; overflow: hidden !important; }}
    ''')

    # 5. Generar el PDF final vectorizado
    pdf_creador = HTML(string=html_completo)
    pdf_creador.write_pdf(ruta_salida, stylesheets=[estilos_base])

    # 6. Esqueleto /AcroForm obligatorio para que FirmaEC detecte las firmas de pyhanko
    _inicializar_acroform_firmaec(ruta_salida)

    # 7. Casillas de formulario reales para los campos ya migrados (Etapa 1):
    # de aquí en adelante se pueden seguir llenando de forma incremental,
    # antes o después de cualquier firma, sin regenerar este documento
    _inyectar_campos_editables(ruta_salida, datos_diccionario)

    return True
