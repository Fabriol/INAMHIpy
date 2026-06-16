# app/services/pdf_service.py
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

def generar_documento_paz_salvo(solicitud, ex_funcionario, respuestas_por_area, ruta_salida):
    doc = SimpleDocTemplate(ruta_salida, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elementos = []
    estilos = getSampleStyleSheet()
    
    # Estilo Justificado para el Art 110 LOSEP
    estilo_justificado = ParagraphStyle(name='Justificado', parent=estilos['Normal'], alignment=TA_JUSTIFY, fontSize=10)
    estilo_titulo = ParagraphStyle(name='Titulo', parent=estilos['Heading1'], alignment=TA_CENTER, fontSize=12, spaceAfter=10)

    # --- ENCABEZADO ---
    elementos.append(Paragraph("<b>INSTITUTO NACIONAL DE METEOROLOGÍA E HIDROLOGÍA (INAMHI)</b>", estilo_titulo))
    elementos.append(Paragraph("<b>FORMULARIO PAZ Y SALVO PARA EL PAGO DE LIQUIDACIÓN DE HABERES</b>", estilo_titulo))
    elementos.append(Spacer(1, 20))

    # --- DATOS PERSONALES ---
    # (Mantener tu tabla aquí...)

    # --- RESPUESTAS DINÁMICAS (Con protección de salto de página) ---
    for area_nombre, lista_respuestas in respuestas_por_area.items():
        # Verificamos si queda espacio (simple check de seguridad)
        elementos.append(Paragraph(f"<b>ÁREA: {area_nombre.upper()}</b>", estilos['Heading3']))
        
        datos_tabla = [['Pregunta', 'Respuesta', 'Observación']]
        for resp in lista_respuestas:
            datos_tabla.append([
                Paragraph(resp['pregunta'], estilos['Normal']), 
                resp['valor'], 
                Paragraph(resp['observacion'] or '-', estilos['Normal'])
            ])
            
        tabla = Table(datos_tabla, colWidths=[240, 60, 150], repeatRows=1)
        tabla.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F2F2F2')),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        elementos.append(tabla)
        elementos.append(Spacer(1, 10))

    # --- LEGAL (Corregido con estilo justificado) ---
    elementos.append(Spacer(1, 30))
    elementos.append(Paragraph("<b>AUTORIZACIÓN (Art. 110 LOSEP)</b>", estilos['Heading4']))
    texto_legal = """Conforme lo establecido en el artículo 110 del Reglamento General a la Ley Orgánica de Servicio Público (LOSEP), 
    quien suscribe el presente formulario de "Paz y Salvo para la liquidación de haberes que me corresponde", 
    AUTORIZO a la DIRECCIÓN ADMINISTRATIVA FINANCIERA del INAMHI, para que efectúe los descuentos detallados 
    en el presente documento por reintegro de valores o bienes que se hayan encontrado a mi cargo."""
    elementos.append(Paragraph(texto_legal, estilo_justificado))
    
    doc.build(elementos)