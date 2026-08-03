import os
import pikepdf
from flask import render_template
from weasyprint import HTML, CSS
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils import generic

_MARGEN_PDF_PT = 24
_ALTO_CAMPO_EDITABLE_PT = 10

# Etapa 1 de la migración a "casillas de formulario PDF reales": estos campos
# ya se pueden llenar antes O después de cualquier firma, sin romper firmas
# ya estampadas, porque se actualizan con una revisión incremental (nunca se
# regenera el PDF completo). Ver hoja_espejo.html: cada uno tiene su propio
# marcador id="espejo_campo_<nombre>". Quedan pendientes de migrar los ~27
# campos Sí/No con color (badge verde/rojo), que necesitan un tratamiento
# especial para no perder ese estilo visual — ver Etapa 3.
CAMPOS_EDITABLES_ACROFORM = {
    # Etapa 1 — datos personales y "responsables" de cada sección
    'nombres_apellidos', 'cedula', 'modalidad', 'fecha_ingreso', 'fecha_salida', 'email1', 'email2',
    'lugar_trabajo', 'grupo_ocupacional', 'unidad', 'cargo',
    'tramites_nombre_resp1', 'tramites_nombre_resp2', 'tramites_nombre_resp3', 'tramites_nombre_responsable',
    'admin_nombre_resp1', 'admin_nombre_resp2', 'admin_nombre_resp3', 'admin_nombre_resp4', 'admin_responsable',
    'tic_nombre_resp1', 'tic_nombre_resp2', 'tic_nombre_resp3', 'tic_nombre_resp4', 'tic_responsable',
    'fin_nombre_resp1', 'fin_nombre_resp2', 'fin_nombre_resp3', 'fin_nombre_resp4', 'fin_director',
    'seg_nombre_resp1', 'seg_nombre_resp2', 'seg_responsable',
    'rrhh_resp_capacitacion', 'rrhh_resp_evaluacion', 'rrhh_resp_viajes', 'rrhh_resp_siith',
    'rrhh_resp_vacaciones', 'rrhh_resp_juramentada', 'rrhh_resp_credencial2', 'rrhh_resp_acta', 'rrhh_director',
    # Etapa 2 — texto simple y celdas combinadas (sin estilo de color)
    'direccion', 'numero_domicilio', 'provincia', 'canton', 'celular', 'emergencia',
    'tramites_admin_contrato', 'tramites_desc_contrato', 'tramites_memo',
    'tramites_jefe_inmediato', 'tramites_servidor_recibe', 'tramites_obs',
    'admin_es_contrato', 'admin_valor_bienes', 'admin_acta_bienes', 'admin_deducibles_valor', 'admin_pasajes_valor',
    'tic_ip_fija', 'tic_liberacion', 'tic_obs1', 'tic_ruta_backup',
    'tic_cierre_correo', 'tic_quipux', 'tic_esigef', 'tic_spryn', 'tic_esbye', 'tic_obs',
    'fin_saldos_valor', 'fin_obs1', 'fin_anticipo_valor', 'fin_obs2',
    'fin_recuperacion_valor', 'fin_obs3', 'fin_devolucion_valor', 'fin_obs4',
    'seg_entrega_copia', 'seg_verificacion_info', 'seg_oficial',
    'rrhh_cursos_eval', 'rrhh_vacaciones', 'rrhh_num_certificado', 'rrhh_num_declaracion',
    'rrhh_respaldo_cd', 'rrhh_ropa_trabajo',
    'recepcion_fecha', 'recepcion_hojas', 'recepcion_servidor', 'recepcion_cargo',
    'cedula_firmante', 'fecha_firma',
}

# Etapa 3 — campos Sí/No que deben conservar el badge de color (ver .ep-yn /
# .ep-yn--s / .ep-yn--n en hoja_espejo.html). Es un subconjunto de
# CAMPOS_EDITABLES_ACROFORM: además de ser editables de forma incremental,
# su apariencia se dibuja a mano (ver _contenido_apariencia_campo) para que
# se sigan viendo con fondo verde/rojo igual que el resto del documento.
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
CAMPOS_EDITABLES_ACROFORM |= CAMPOS_SI_NO_COLOR

# Colores exactos de .ep-yn--s / .ep-yn--n en hoja_espejo.html, convertidos a RGB 0-1
_COLOR_BADGE_SI = ((0.863, 0.988, 0.906), (0.133, 0.773, 0.369), (0.086, 0.396, 0.204))
_COLOR_BADGE_NO = ((0.996, 0.886, 0.886), (0.937, 0.267, 0.267), (0.6, 0.106, 0.106))
_COLOR_BADGE_NEUTRO = ((1, 1, 1), (0.792, 0.835, 0.882), (0, 0, 0))


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
        texto_escapado = texto_norm.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')
        tam_fuente = round(alto * 0.62, 2)
        y_texto = max(1.0, (alto - tam_fuente) / 2 + tam_fuente * 0.14)
        if es_badge:
            ancho_texto_aprox = len(texto_norm) * tam_fuente * 0.6
            x_texto = max(1.0, (ancho - ancho_texto_aprox) / 2)
        else:
            x_texto = 2.0
        lineas += [
            'BT', f'/Helv {tam_fuente} Tf',
            f'{color_txt[0]:.3f} {color_txt[1]:.3f} {color_txt[2]:.3f} rg',
            f'{x_texto:.2f} {y_texto:.2f} Td', f'({texto_escapado}) Tj', 'ET',
        ]

    return '\n'.join(lineas).encode('latin-1', errors='replace')


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

        posiciones = {}
        for item in recorrer(outline.root):
            if item.title and item.title.startswith('espejo_campo_') and item.destination:
                nombre_campo = item.title[len('espejo_campo_'):]
                dest = item.destination
                pagina = pdf.pages.index(dest[0])
                posiciones[nombre_campo] = (pagina, float(dest[2]), float(dest[3]))

        if not posiciones:
            return

        root = pdf.Root
        if '/AcroForm' not in root:
            root.AcroForm = pdf.make_indirect(pikepdf.Dictionary(Fields=pikepdf.Array([]), SigFlags=3))
        root.AcroForm.NeedAppearances = False  # la apariencia se dibuja a mano, no se delega al visor

        fuente_helv = pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name('/Font'), Subtype=pikepdf.Name('/Type1'),
            BaseFont=pikepdf.Name('/Helvetica'), Encoding=pikepdf.Name('/WinAnsiEncoding'),
        ))

        for nombre_campo, (pagina, x, y) in posiciones.items():
            pagina_obj = pdf.pages[pagina]
            ancho_pagina = float(pagina_obj.MediaBox[2])
            es_badge = nombre_campo in CAMPOS_SI_NO_COLOR
            ancho_campo = 34 if es_badge else max(60, (ancho_pagina - _MARGEN_PDF_PT) - x - 2)
            alto_campo = _ALTO_CAMPO_EDITABLE_PT
            rect = pikepdf.Array([x, y - alto_campo, x + ancho_campo, y])

            valor_actual = datos_diccionario.get(nombre_campo) or ''

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
                valor_texto = str(valor) if valor is not None else ''
                campo_obj['/V'] = generic.TextStringObject(valor_texto)

                rect = campo_obj.get('/Rect')
                ancho_campo = float(rect[2]) - float(rect[0]) if rect else 100.0
                alto_campo = float(rect[3]) - float(rect[1]) if rect else _ALTO_CAMPO_EDITABLE_PT
                es_badge = campo_formulario in CAMPOS_SI_NO_COLOR

                contenido = _contenido_apariencia_campo(ancho_campo, alto_campo, valor_texto, es_badge)
                fuente_ref = w.add_object(generic.DictionaryObject({
                    generic.NameObject('/Type'): generic.NameObject('/Font'),
                    generic.NameObject('/Subtype'): generic.NameObject('/Type1'),
                    generic.NameObject('/BaseFont'): generic.NameObject('/Helvetica'),
                    generic.NameObject('/Encoding'): generic.NameObject('/WinAnsiEncoding'),
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

    # 4. Estilos en línea obligatorios para la impresión perfecta en A4
    estilos_base = CSS(string='''
        @page { size: A4 portrait; margin: 8mm; }
        body { font-family: Arial, sans-serif; background: #fff; margin: 0; padding: 0; }
        * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
        .ep-tabla tr { page-break-inside: avoid; }
        .ep-bloque__head { page-break-after: avoid; }
        .ep-firma-box, .firmaec-sello { page-break-inside: avoid; }
        /* Marcadores internos (invisibles) para ubicar cada celda de firma al momento de firmar,
           y cada celda de dato editable (espejo_campo_) para convertirla en casilla de
           formulario PDF real que se puede seguir llenando aunque el documento ya tenga firmas */
        [id^="espejo_firma_"], [id^="espejo_campo_"] { bookmark-level: 1; bookmark-label: attr(id); }
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
