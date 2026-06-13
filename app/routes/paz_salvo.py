from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from app.models.base import db, Usuario, Rol, SolicitudPazSalvo
import os
from flask import send_file
from app.models.base import Respuesta
from app.services.pdf_service import generar_documento_paz_salvo

paz_salvo_bp = Blueprint('paz_salvo', __name__)

@paz_salvo_bp.route('/paz-salvo/nueva', methods=['GET', 'POST'])
@login_required
def nueva_solicitud():
    # 1. Validación de Seguridad: Solo perfiles autorizados pueden crear trámites
    roles_permitidos = ['Administrador', 'Talento Humano - Recepción Documentos']
    if current_user.rol.nombre not in roles_permitidos:
        flash('Acceso denegado. No tienes permisos para iniciar un trámite.', 'danger')
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        cedula = request.form.get('cedula')
        nombres = request.form.get('nombres')
        apellidos = request.form.get('apellidos')
        email = request.form.get('email')

        # 2. Verificamos si el usuario ya existe en la base de datos
        usuario = Usuario.query.filter_by(cedula=cedula).first()

        if not usuario:
            # Si no existe, buscamos el rol oficial y lo creamos
            rol_ex = Rol.query.filter_by(nombre='Ex Funcionario').first()
            
            usuario = Usuario(
                rol_id=rol_ex.id,
                cedula=cedula,
                nombres=nombres,
                apellidos=apellidos,
                email=email,
                # La contraseña temporal será la misma cédula
                password_hash=generate_password_hash(cedula),
                activo=True
            )
            db.session.add(usuario)
            db.session.flush() # Guardamos temporalmente para obtener su ID

        # 3. Generamos el inicio del trámite de Paz y Salvo
        nueva_solicitud = SolicitudPazSalvo(
            ex_funcionario_id=usuario.id,
            estado='CREADO'
        )
        db.session.add(nueva_solicitud)
        db.session.commit()

        flash(f'Trámite iniciado correctamente para el ex funcionario {nombres} {apellidos}.', 'success')
        return redirect(url_for('dashboard.index'))

    return render_template('paz_salvo/crear.html')

@paz_salvo_bp.route('/paz-salvo/descargar-pdf/<int:solicitud_id>')
@login_required
def descargar_pdf(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
    
    # Extraemos todas las respuestas vinculadas a esta solicitud
    respuestas_db = Respuesta.query.filter_by(solicitud_id=solicitud.id).all()
    
    # Agrupamos las respuestas por el Área que las respondió (Ej: TICs, Financiera)
    # usando una comprensión de diccionarios
    respuestas_por_area = {}
    
    for r in respuestas_db:
        pregunta = r.pregunta # Relación SQLAlchemy
        nombre_area = pregunta.rol.nombre # Nombre del departamento
        
        if nombre_area not in respuestas_por_area:
            respuestas_por_area[nombre_area] = []
            
        respuestas_por_area[nombre_area].append({
            'pregunta': pregunta.enunciado,
            'valor': r.valor_respuesta,
            'observacion': r.observacion
        })

    # Aseguramos que exista una carpeta temporal para guardar el PDF
    directorio_temp = os.path.join('app', 'static', 'temp')
    os.makedirs(directorio_temp, exist_ok=True)
    
    # Nombre del archivo final
    ruta_pdf = os.path.join(directorio_temp, f'PazSalvo_{ex_funcionario.cedula}_{solicitud.id}.pdf')
    
    # Llamamos a nuestro motor ReportLab
    generar_documento_paz_salvo(solicitud, ex_funcionario, respuestas_por_area, ruta_pdf)
    
    # Guardamos la ruta en la base de datos por historial
    solicitud.pdf_generado_path = ruta_pdf
    db.session.commit()

    # Le enviamos el archivo al navegador del usuario para que lo descargue
    return send_file(
        f"../{ruta_pdf}", 
        as_attachment=True, 
        download_name=f"Formulario_Paz_Salvo_{ex_funcionario.cedula}.pdf",
        mimetype='application/pdf'
    )