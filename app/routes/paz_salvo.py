from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, abort
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
import os

# Importaciones de modelos
from app.models.base import db, Usuario, Rol, SolicitudPazSalvo, Respuesta, Pregunta

# Importaciones de servicios (Centralizadas)
from app.services.pdf_service import generar_documento_paz_salvo
from app.services.firma_service import validar_firma_p12

paz_salvo_bp = Blueprint('paz_salvo', __name__)

# ==========================================
# 1. RUTA: INICIAR SOLICITUD
# ==========================================
@paz_salvo_bp.route('/paz-salvo/nueva', methods=['GET', 'POST'])
@login_required
def nueva_solicitud():
    if current_user.rol.nombre not in ['Administrador', 'Talento Humano - Recepción Documentos']:
        flash('Acceso denegado. No tiene permisos para iniciar este trámite.', 'danger')
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        cedula = request.form.get('cedula', '').strip()
        usuario = Usuario.query.filter_by(cedula=cedula).first()
        
        if not usuario:
            # FIX: Email por defecto para evitar el IntegrityError en MySQL
            email_ingresado = request.form.get('email', '').lower().strip()
            email_seguro = email_ingresado if email_ingresado else f"{cedula}@inamhi.gob.ec"
            
            rol_ex = Rol.query.filter_by(nombre='Ex Funcionario').first()
            usuario = Usuario(
                rol_id=rol_ex.id, 
                cedula=cedula, 
                nombres=request.form.get('nombres', '').upper(),
                apellidos=request.form.get('apellidos', '').upper(),
                email=email_seguro,
                password_hash=generate_password_hash(cedula), 
                activo=True
            )
            db.session.add(usuario)
            db.session.commit()

        if SolicitudPazSalvo.query.filter_by(ex_funcionario_id=usuario.id, estado='CREADO').first():
            flash('Este usuario ya tiene un trámite activo.', 'info')
            return redirect(url_for('dashboard.index'))

        nueva_solicitud = SolicitudPazSalvo(ex_funcionario_id=usuario.id, estado='CREADO')
        db.session.add(nueva_solicitud)
        db.session.commit()
        
        return redirect(url_for('paz_salvo.llenar_formulario', solicitud_id=nueva_solicitud.id))

    return render_template('paz_salvo/crear.html')


# ==========================================
# 2. RUTA: FORMULARIO DINÁMICO (HOJA ESPEJO)
# ==========================================
@paz_salvo_bp.route('/paz-salvo/llenar/<int:solicitud_id>', methods=['GET'])
@login_required
def llenar_formulario(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    preguntas = Pregunta.query.all()
    return render_template('paz_salvo/llenar_formulario.html', solicitud=solicitud, preguntas=preguntas)


# ==========================================
# 3. RUTA: AUTOGUARDADO HTMX
# ==========================================
@paz_salvo_bp.route('/actualizar-espejo', methods=['POST'])
@login_required
def actualizar_espejo():
    datos = request.form.to_dict()
    solicitud_id = datos.get('solicitud_id')
    
    if solicitud_id:
        for key, value in datos.items():
            if key.startswith('pregunta_'):
                pregunta_id = key.split('_')[1]
                respuesta = Respuesta.query.filter_by(solicitud_id=solicitud_id, pregunta_id=pregunta_id).first()
                if respuesta:
                    respuesta.valor_respuesta = value
                else:
                    db.session.add(Respuesta(solicitud_id=solicitud_id, pregunta_id=pregunta_id, valor_respuesta=value))
        db.session.commit()
    
    return render_template('paz_salvo/partials/hoja_espejo.html', datos=datos)


# ==========================================
# 4. RUTA: GENERACIÓN Y DESCARGA DE PDF
# ==========================================
@paz_salvo_bp.route('/paz-salvo/descargar-pdf/<int:solicitud_id>')
@login_required
def descargar_pdf(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    
    if current_user.id != solicitud.ex_funcionario_id and current_user.rol.nombre != 'Administrador':
        abort(403)

    respuestas_db = Respuesta.query.filter_by(solicitud_id=solicitud.id).all()
    respuestas_por_area = {}
    for r in respuestas_db:
        nombre_area = r.pregunta.rol.nombre
        respuestas_por_area.setdefault(nombre_area, []).append({
            'pregunta': r.pregunta.enunciado, 
            'valor': r.valor_respuesta
        })

    directorio_temp = os.path.join('app', 'static', 'temp')
    os.makedirs(directorio_temp, exist_ok=True)
    ruta_pdf = os.path.join(directorio_temp, f'PazSalvo_{solicitud.id}.pdf')
    
    try:
        generar_documento_paz_salvo(solicitud, solicitud.ex_funcionario, respuestas_por_area, ruta_pdf)
    except Exception as e:
        flash(f'Ocurrió un error al generar el PDF: {str(e)}', 'danger')
        return redirect(url_for('paz_salvo.llenar_formulario', solicitud_id=solicitud.id))
    
    return send_file(ruta_pdf, as_attachment=True, download_name=f"Paz_y_Salvo_{solicitud.id}.pdf")


# ==========================================
# 5. RUTA: VALIDACIÓN Y SUBIDA DE FIRMA .P12
# ==========================================
@paz_salvo_bp.route('/paz-salvo/subir-firma/<int:solicitud_id>', methods=['POST'])
@login_required
def subir_firma_digital(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    archivo = request.files.get('pdf_firmado')
    
    if not archivo or not archivo.filename.endswith('.pdf'):
        flash('Por favor, suba un archivo PDF válido.', 'danger')
        return redirect(url_for('paz_salvo.llenar_formulario', solicitud_id=solicitud_id))

    ruta_final = os.path.join('app', 'static', 'documentos_firmados', f'Final_{solicitud.id}.pdf')
    os.makedirs(os.path.dirname(ruta_final), exist_ok=True)
    archivo.save(ruta_final)
    
    valido, mensaje = validar_firma_p12(ruta_final)
    
    if valido:
        solicitud.estado = 'COMPLETADO'
        solicitud.pdf_final_path = ruta_final
        db.session.commit()
        flash(f'¡Trámite finalizado con éxito! {mensaje}', 'success')
    else:
        if os.path.exists(ruta_final):
            os.remove(ruta_final)
        flash(mensaje, 'danger')
            
    return redirect(url_for('dashboard.index'))