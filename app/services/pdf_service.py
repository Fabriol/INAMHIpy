import os
from flask import render_template, current_app
from weasyprint import HTML, CSS

def generar_documento_paz_salvo(solicitud, ex_funcionario, respuestas_db, ruta_salida):
    """
    Convierte la plantilla HTML 'hoja_espejo.html' en un documento PDF A4 perfecto.
    Utiliza WeasyPrint para garantizar que el diseño de impresión coincida
    milimétricamente con la vista previa del navegador, incluyendo los bloques
    de FirmaEC PAdES.
    """
    
    # 1. Preparar el diccionario de datos tal como lo espera la hoja espejo.
    # Recorremos la tabla Respuesta y mapeamos el nombre del campo con su valor.
    datos_diccionario = {}
    for respuesta in respuestas_db:
        if respuesta.campo_formulario:
            datos_diccionario[respuesta.campo_formulario] = respuesta.valor_respuesta

    # 2. Renderizar el HTML usando el contexto completo
    html_renderizado = render_template(
        'paz_salvo/partials/hoja_espejo.html',
        solicitud=solicitud,
        datos=datos_diccionario,
        current_user=ex_funcionario
    )

    # 3. Estilos en línea obligatorios para la impresión perfecta en A4
    # Garantiza que los fondos oscuros se impriman y respeta los cortes de página.
    estilos_base = CSS(string='''
        @page { size: A4 portrait; margin: 10mm; }
        body { font-family: Arial, sans-serif; background: #fff; }
        * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
        .ep-tabla tr { page-break-inside: avoid; }
        .ep-bloque__head { page-break-after: avoid; }
        .ep-firma-box, .firmaec-sello { page-break-inside: avoid; }
    ''')

    # 4. Generar el PDF final en la ruta indicada
    pdf_creador = HTML(string=html_renderizado)
    pdf_creador.write_pdf(ruta_salida, stylesheets=[estilos_base])
    
    return True