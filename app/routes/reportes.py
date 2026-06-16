import os
import os
from flask import Blueprint, send_file, flash, redirect, url_for, render_template
from flask_login import login_required, current_user
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from app.models.base import db, SolicitudPazSalvo, Usuario





reportes_bp = Blueprint('reportes', __name__)

@reportes_bp.route('/reportes')
@login_required
def vista_reportes():
    return render_template('admin/reportes.html')

@reportes_bp.route('/auditoria')
@login_required
def vista_auditoria():
    return render_template('admin/auditoria.html')


@reportes_bp.route('/admin/exportar-excel')
@login_required
def exportar_excel():
    # 1. Seguridad: Solo Administrador o Talento Humano pueden sacar reportes globales
    roles_permitidos = ['Administrador', 'Talento Humano - Recepción Documentos']
    if current_user.rol.nombre not in roles_permitidos:
        flash('Acceso denegado. No tiene permisos para generar reportes.', 'danger')
        return redirect(url_for('dashboard.index'))

    # 2. Creamos el libro de Excel en memoria
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte Paz y Salvo"

    # 3. Definimos estilos corporativos para la cabecera
    estilo_cabecera = PatternFill(start_color="003366", end_color="003366", fill_type="solid")
    fuente_cabecera = Font(color="FFFFFF", bold=True)
    alineacion_centro = Alignment(horizontal="center", vertical="center")

    # 4. Escribimos los títulos de las columnas
    columnas = [
        "Nro. Trámite", "Cédula", "Nombres Completos", "Correo Electrónico", 
        "Estado del Proceso", "Fecha de Creación", "Fecha de Cierre", "Firma Criptográfica"
    ]
    
    ws.append(columnas)
    
    # Aplicamos el estilo a la primera fila
    for celda in ws[1]:
        celda.fill = estilo_cabecera
        celda.font = fuente_cabecera
        celda.alignment = alineacion_centro

    # Ajustamos el ancho de las columnas
    ws.column_dimensions['B'].width = 15
    ws.column_dimensions['C'].width = 30
    ws.column_dimensions['D'].width = 25
    ws.column_dimensions['E'].width = 20
    ws.column_dimensions['F'].width = 20
    ws.column_dimensions['H'].width = 40

    # 5. Traemos los datos de la Base de Datos (Join entre Solicitud y Usuario)
    solicitudes = SolicitudPazSalvo.query.all()
    
    for sol in solicitudes:
        ex_func = Usuario.query.get(sol.ex_funcionario_id)
        
        fecha_creacion = sol.fecha_creacion.strftime('%Y-%m-%d %H:%M') if sol.fecha_creacion else 'N/A'
        fecha_cierre = sol.fecha_cierre.strftime('%Y-%m-%d %H:%M') if sol.fecha_cierre else 'Pendiente'
        validez_firma = "VÁLIDA (FirmaEC)" if sol.certificado_valido else "Pendiente / Sin validar"

        fila = [
            sol.id,
            ex_func.cedula,
            f"{ex_func.nombres} {ex_func.apellidos}",
            ex_func.email,
            sol.estado,
            fecha_creacion,
            fecha_cierre,
            validez_firma
        ]
        ws.append(fila)

    # 6. Guardamos el archivo temporalmente
    directorio_temp = os.path.join('app', 'static', 'temp')
    os.makedirs(directorio_temp, exist_ok=True)
    
    ruta_excel = os.path.join(directorio_temp, 'Reporte_General_Paz_Salvo.xlsx')
    wb.save(ruta_excel)

    # 7. Enviamos el archivo al navegador
    return send_file(
        f"../{ruta_excel}", 
        as_attachment=True, 
        download_name="Reporte_Paz_Salvo_INAMHI.xlsx",
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )