import os
import pikepdf
from flask import render_template
from weasyprint import HTML, CSS

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
    generar_documento_paz_salvo) y devuelve (pagina, x, y) del punto donde
    empieza esa celda en el PDF ya renderizado. Devuelve None si no se
    encuentra, para que el llamador pueda usar una firma invisible como
    respaldo sin romper el flujo de firma.
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
                return pagina, float(dest[2]), float(dest[3])
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
        /* Marcadores internos (invisibles) para ubicar cada celda de firma al momento de firmar */
        [id^="espejo_firma_"] { bookmark-level: 1; bookmark-label: attr(id); }
    ''')

    # 5. Generar el PDF final vectorizado
    pdf_creador = HTML(string=html_completo)
    pdf_creador.write_pdf(ruta_salida, stylesheets=[estilos_base])

    # 6. Esqueleto /AcroForm obligatorio para que FirmaEC detecte las firmas de pyhanko
    _inicializar_acroform_firmaec(ruta_salida)

    return True
