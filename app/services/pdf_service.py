import os
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

def generar_documento_paz_salvo(solicitud, ex_funcionario, respuestas_por_area, ruta_salida):
    doc = SimpleDocTemplate(ruta_salida, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elementos = []
    estilos = getSampleStyleSheet()
    
    # Estilos de texto personalizados
    estilo_titulo = ParagraphStyle(name='Titulo', parent=estilos['Heading1'], alignment=TA_CENTER, fontSize=12, spaceAfter=10)
    estilo_normal = estilos['Normal']

    # --- ENCABEZADO INSTITUCIONAL ---
    elementos.append(Paragraph("<b>INSTITUTO NACIONAL DE METEOROLOGÍA E HIDROLOGÍA (INAMHI)</b>", estilo_titulo))
    elementos.append(Paragraph("<b>DIRECCIÓN DE ADMINISTRACIÓN DE RECURSOS HUMANOS</b>", estilo_titulo))
    elementos.append(Paragraph("FORMULARIO PAZ Y SALVO PARA EL PAGO DE LIQUIDACIÓN DE HABERES", estilo_titulo))
    elementos.append(Spacer(1, 10))

    # --- 1. DATOS PERSONALES DEL EX FUNCIONARIO ---
    datos_personales = [
        ['DATOS PERSONALES', '', '', ''],
        ['NOMBRES Y APELLIDOS:', f'{ex_funcionario.nombres} {ex_funcionario.apellidos}', 'CÉDULA:', ex_funcionario.cedula],
        ['CORREO ELECTRÓNICO:', ex_funcionario.email, 'TRÁMITE NRO:', f'#{solicitud.id}']
    ]
    
    tabla_personales = Table(datos_personales, colWidths=[120, 180, 70, 130])
    tabla_personales.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.black),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('SPAN', (0, 0), (3, 0)), # Combinar título
    ]))
    elementos.append(tabla_personales)
    elementos.append(Spacer(1, 20))

    # --- 2. RESPUESTAS DINÁMICAS POR ÁREAS ---
    for area_nombre, lista_respuestas in respuestas_por_area.items():
        # Título del Área
        datos_area = [[f'ÁREA: {area_nombre}']]
        
        # Cabeceras de la tabla del área
        datos_area.append(['Detalle (Pregunta)', 'Respuesta', 'Observación'])
        
        # Llenamos las respuestas de esa área
        for resp in lista_respuestas:
            # resp["pregunta"] es el enunciado, resp["valor"] es la respuesta guardada
            datos_area.append([resp['pregunta'], resp['valor'], resp['observacion'] or 'Ninguna'])
            
        tabla_area = Table(datos_area, colWidths=[250, 100, 150])
        tabla_area.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003366')), # Azul institucional
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BACKGROUND', (0, 1), (-1, 1), colors.lightgrey), # Cabeceras
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 1), (1, -1), 'CENTER'), # Centrar los SÍ/NO
            ('FONTNAME', (0, 0), (-1, 1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('SPAN', (0, 0), (2, 0)), # Combinar título del área
        ]))
        elementos.append(tabla_area)
        elementos.append(Spacer(1, 15))

    # --- 3. SECCIÓN LEGAL Y ESPACIO PARA FIRMAEC ---
    elementos.append(Spacer(1, 40))
    elementos.append(Paragraph("<b>AUTORIZACIÓN (Art. 110 LOSEP)</b>", estilo_titulo))
    texto_legal = """Conforme lo establecido en el artículo 110 del Reglamento a la Ley Orgánica de Servicio Público (LOSEP), 
    quien suscribe el presente formulario autoriza a la DIRECCIÓN ADMINISTRATIVA FINANCIERA para que efectúe los descuentos 
    detallados en el presente documento."""
    elementos.append(Paragraph(texto_legal, estilo_normal))
    
    elementos.append(Spacer(1, 50))
    
    # Cuadro de firma (Solo texto y líneas, CERO imágenes)
    datos_firma = [
        ['___________________________________________________'],
        [f'FIRMA DEL SERVIDOR SALIENTE: {ex_funcionario.nombres} {ex_funcionario.apellidos}'],
        ['C.C: ' + ex_funcionario.cedula],
        ['(Documento a ser firmado digitalmente mediante FirmaEC)']
    ]
    tabla_firma = Table(datos_firma, colWidths=[300])
    tabla_firma.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 3), (0, 3), colors.gray),
    ]))
    elementos.append(tabla_firma)

    # Construir el PDF
    doc.build(elementos)
    return ruta_salida