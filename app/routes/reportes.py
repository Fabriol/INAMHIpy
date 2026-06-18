import os
from datetime import datetime
from flask import Blueprint, send_file, flash, redirect, url_for, render_template, request, abort
from flask_login import login_required, current_user
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

# Librerías para el PDF de Auditoría
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

from app.models.base import db, SolicitudPazSalvo, Usuario, LogAuditoria

reportes_bp = Blueprint('reportes', __name__)

# Función auxiliar para filtrar los logs compartida entre la vista y las exportaciones
def obtener_logs_filtrados():
    query = LogAuditoria.query.join(Usuario)
    
    busqueda = request.args.get('usuario', '').strip()
    fecha_inicio = request.args.get('fecha_inicio', '').strip()
    fecha_fin = request.args.get('fecha_fin', '').strip()

    if busqueda:
        query = query.filter((Usuario.nombres.ilike(f'%{busqueda}%')) | (Usuario.cedula.ilike(f'%{busqueda}%')))
    if fecha_inicio:
        fecha_ini_obj = datetime.strptime(fecha_inicio, '%Y-%m-%d')
        query = query.filter(LogAuditoria.fecha >= fecha_ini_obj)
    if fecha_fin:
        fecha_fin_obj = datetime.strptime(f"{fecha_fin} 23:59:59", '%Y-%m-%d %H:%M:%S')
        query = query.filter(LogAuditoria.fecha <= fecha_fin_obj)

    return query.order_by(LogAuditoria.fecha.desc()).all()


@reportes_bp.route('/admin/auditoria')
@login_required
def vista_auditoria():
    if current_user.rol.nombre not in ['Administrador', 'Talento Humano - Recepción Documentos']:
        abort(403)
        
    logs = obtener_logs_filtrados()
    return render_template('admin/auditoria.html', logs=logs)


@reportes_bp.route('/admin/auditoria/exportar-excel')
@login_required
def exportar_auditoria_excel():
    logs = obtener_logs_filtrados()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Auditoría INAMHI"

    estilo_cabecera = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    fuente_cabecera = Font(color="FFFFFF", bold=True)
    
    columnas = ["ID", "USUARIO", "ROL", "MÓDULO", "ACCIÓN", "DETALLE", "FECHA"]
    ws.append(columnas)
    
    for celda in ws[1]:
        celda.fill = estilo_cabecera
        celda.font = fuente_cabecera
        celda.alignment = Alignment(horizontal="center")

    ws.column_dimensions['B'].width = 20
    ws.column_dimensions['C'].width = 20
    ws.column_dimensions['F'].width = 50
    ws.column_dimensions['G'].width = 20

    for log in logs:
        ws.append([
            f"#{log.id}", log.usuario.cedula, log.usuario.rol.nombre, 
            log.modulo, log.accion, log.detalle, log.fecha.strftime('%Y-%m-%d %H:%M')
        ])

    dir_temp = os.path.join('app', 'static', 'temp')
    os.makedirs(dir_temp, exist_ok=True)
    ruta_excel = os.path.join(dir_temp, 'Auditoria_INAMHI.xlsx')
    wb.save(ruta_excel)

    return send_file(os.path.abspath(ruta_excel), as_attachment=True, download_name="Auditoria_INAMHI.xlsx")


@reportes_bp.route('/admin/auditoria/exportar-pdf')
@login_required
def exportar_auditoria_pdf():
    logs = obtener_logs_filtrados()
    
    dir_temp = os.path.join('app', 'static', 'temp')
    os.makedirs(dir_temp, exist_ok=True)
    ruta_pdf = os.path.join(dir_temp, 'Auditoria_INAMHI.pdf')

    doc = SimpleDocTemplate(ruta_pdf, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    elementos = []
    estilos = getSampleStyleSheet()

    elementos.append(Paragraph("<b>REPORTE DE AUDITORÍA DEL SISTEMA - INAMHI</b>", estilos['Title']))
    elementos.append(Spacer(1, 15))

    datos_tabla = [["ID", "USUARIO", "ROL", "MÓDULO", "ACCIÓN", "FECHA"]]
    for log in logs:
        datos_tabla.append([
            f"#{log.id}", log.usuario.cedula, log.usuario.rol.nombre, 
            log.modulo, log.accion, log.fecha.strftime('%Y-%m-%d %H:%M')
        ])

    tabla = Table(datos_tabla, colWidths=[40, 100, 120, 100, 120, 100])
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
    ]))
    
    elementos.append(tabla)
    doc.build(elementos)

    return send_file(os.path.abspath(ruta_pdf), as_attachment=True, download_name="Auditoria_INAMHI.pdf")