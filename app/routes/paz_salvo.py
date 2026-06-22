from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, abort
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
import os

from app.models.base import db, Usuario, Rol, SolicitudPazSalvo, Respuesta, Pregunta, LogAuditoria
from app.services.pdf_service import generar_documento_paz_salvo
from app.services.firma_service import validar_firma_p12

paz_salvo_bp = Blueprint('paz_salvo', __name__)

# ==========================================
# 1. RUTA: INICIAR SOLICITUD
# ==========================================
# Reemplaza solo esta función en tu app/routes/paz_salvo.py

@paz_salvo_bp.route('/paz-salvo/nueva', methods=['GET', 'POST'])
@login_required
def nueva_solicitud():
    if current_user.rol.nombre not in ['Administrador', 'Talento Humano - Recepción Documentos']:
        flash('Acceso denegado. No tiene permisos para gestionar este módulo.', 'danger')
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        cedula = request.form.get('cedula', '').strip()
        username_input = request.form.get('username', '').strip()
        email_input = request.form.get('email', '').strip()

        # VALIDACIÓN 1: Verificamos si la cédula ya existe en la base de datos
        usuario = Usuario.query.filter_by(cedula=cedula).first()
        
        if not usuario:
            # VALIDACIÓN 2: Verificamos que el correo generado no pertenezca a OTRO usuario
            correo_existente = Usuario.query.filter_by(email=email_input).first()
            if correo_existente:
                flash(f'El correo {email_input} ya está asignado a otro funcionario. Por favor, modifique manualmente el nombre de usuario (Ej: agregue un número al final).', 'danger')
                return redirect(url_for('paz_salvo.nueva_solicitud'))

            rol_ex = Rol.query.filter_by(nombre='Ex Funcionario').first()
            
            # Guardamos el usuario con el nuevo campo username y el correo institucional
            usuario = Usuario(
                rol_id=rol_ex.id, 
                cedula=cedula, 
                nombres=request.form.get('nombres', '').upper(),
                apellidos=request.form.get('apellidos', '').upper(),
                username=username_input,   # <-- NUEVO DATO GUARDADO
                email=email_input,         # <-- CORREO AUTOCOMPLETADO
                password_hash=generate_password_hash(cedula), 
                activo=True
            )
            db.session.add(usuario)
            db.session.commit()

        # VALIDACIÓN 3: Prevenir duplicidad de trámites (Que no tenga 2 trámites abiertos)
        tramite_creado = SolicitudPazSalvo.query.filter_by(ex_funcionario_id=usuario.id, estado='CREADO').first()
        tramite_proceso = SolicitudPazSalvo.query.filter_by(ex_funcionario_id=usuario.id, estado='EN_PROGRESO').first()
        
        if tramite_creado or tramite_proceso:
            flash('Este ex funcionario ya cuenta con un trámite activo en el sistema. Utilice el botón "Abrir y Llenar Formulario" en la tabla inferior.', 'warning')
            return redirect(url_for('paz_salvo.nueva_solicitud'))

        # Si pasa todas las validaciones, se crea el expediente
        nueva_solicitud = SolicitudPazSalvo(ex_funcionario_id=usuario.id, estado='CREADO')
        db.session.add(nueva_solicitud)
        
        log = LogAuditoria(
            usuario_id=current_user.id, modulo='Formularios', accion='NUEVO EXPEDIENTE', 
            detalle=f"Creó expediente de Paz y Salvo para CI: {usuario.cedula} ({usuario.email})"
        )
        db.session.add(log)
        db.session.commit()
        
        flash('Expediente institucional creado exitosamente. Proceda con el llenado de datos.', 'success')
        return redirect(url_for('paz_salvo.llenar_formulario', solicitud_id=nueva_solicitud.id))

    # Renderiza la vista y envía la lista de solicitudes para la tabla inferior
    solicitudes_db = SolicitudPazSalvo.query.order_by(SolicitudPazSalvo.id.desc()).all()
    for sol in solicitudes_db:
        sol.usuario_data = Usuario.query.get(sol.ex_funcionario_id)
        
    return render_template('paz_salvo/crear.html', solicitudes=solicitudes_db)

# ==========================================
# 2. RUTA: FORMULARIO DINÁMICO
# ==========================================
@paz_salvo_bp.route('/paz-salvo/llenar/<int:solicitud_id>', methods=['GET'])
@login_required
def llenar_formulario(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
    
    if current_user.id != solicitud.ex_funcionario_id and current_user.rol.nombre != 'Administrador':
        abort(403)
        
    preguntas = Pregunta.query.all()
    # SOLUCIÓN: Buscamos el nombre del rol manualmente y se lo pegamos a la pregunta
    for p in preguntas:
        rol_obj = Rol.query.get(p.rol_asignado_id)
        p.area_nombre = rol_obj.nombre if rol_obj else 'ÁREA TÉCNICA'
        
    return render_template('paz_salvo/llenar_formulario.html', solicitud=solicitud, preguntas=preguntas)


# ==========================================
# 3. RUTA: AUTOGUARDADO HTMX
# ==========================================
@paz_salvo_bp.route('/actualizar-espejo', methods=['POST'])
@login_required
def actualizar_espejo():
    datos = request.form.to_dict()
    solicitud_id = datos.get('solicitud_id')
    solicitud = SolicitudPazSalvo.query.get(solicitud_id)
    cambios_registrados = []
    
    if solicitud:
        solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
        
        if datos.get('celular'):
            solicitud.ex_funcionario.celular = datos.get('celular')
        if datos.get('direccion'):
            solicitud.ex_funcionario.direccion = datos.get('direccion')

        for key, value in datos.items():
            if key.startswith('pregunta_'):
                pregunta_id = key.split('_')[1]
                respuesta = Respuesta.query.filter_by(solicitud_id=solicitud_id, pregunta_id=pregunta_id).first()
                
                if respuesta:
                    if respuesta.valor_respuesta != value:
                        cambios_registrados.append(f"P{pregunta_id} a '{value}'")
                        respuesta.valor_respuesta = value
                else:
                    cambios_registrados.append(f"P{pregunta_id} respondida '{value}'")
                    db.session.add(Respuesta(solicitud_id=solicitud_id, pregunta_id=pregunta_id, valor_respuesta=value))
        
        if cambios_registrados:
            log = LogAuditoria(
                usuario_id=current_user.id, modulo='Formularios', accion='EDICIÓN CAMPOS', 
                detalle=f"Tramite #{solicitud_id} actualizado: {', '.join(cambios_registrados)}"
            )
            db.session.add(log)
            
        db.session.commit()
    
    # SOLUCIÓN: Volvemos a enviar las preguntas al actualizar para que no desaparezcan de la tabla
    preguntas = Pregunta.query.all()
    for p in preguntas:
        rol_obj = Rol.query.get(p.rol_asignado_id)
        p.area_nombre = rol_obj.nombre if rol_obj else 'ÁREA TÉCNICA'
    
    return render_template('paz_salvo/partials/hoja_espejo.html', datos=datos, solicitud=solicitud, preguntas=preguntas)


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
    
    # SOLUCIÓN: Buscar el rol manualmente en la generación del PDF para evitar colapsos
    for r in respuestas_db:
        rol_obj = Rol.query.get(r.pregunta.rol_asignado_id)
        nombre_area = rol_obj.nombre if rol_obj else 'ÁREA TÉCNICA'
        respuestas_por_area.setdefault(nombre_area, []).append({'pregunta': r.pregunta.enunciado, 'valor': r.valor_respuesta})

    directorio_temp = os.path.join('app', 'static', 'temp')
    os.makedirs(directorio_temp, exist_ok=True)
    ruta_pdf = os.path.join(directorio_temp, f'PazSalvo_{solicitud.id}.pdf')
    
    log = LogAuditoria(usuario_id=current_user.id, modulo='Reportes', accion='DESCARGA PDF', detalle=f"Descargó borrador PDF del trámite #{solicitud.id}")
    db.session.add(log)
    db.session.commit()
    
    try:
        usuario_obj = Usuario.query.get(solicitud.ex_funcionario_id)
        generar_documento_paz_salvo(solicitud, usuario_obj, respuestas_por_area, ruta_pdf)
    except Exception as e:
        flash(f'Ocurrió un error al generar el PDF: {str(e)}', 'danger')
        return redirect(url_for('paz_salvo.llenar_formulario', solicitud_id=solicitud.id))
    
    return send_file(ruta_pdf, as_attachment=True, download_name=f"Paz_y_Salvo_{solicitud.id}.pdf")


# ==========================================
# 5. RUTA: VALIDACIÓN Y SUBIDA DE FIRMA
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
        solicitud.pdf_firmado_path = ruta_final
        
        log = LogAuditoria(
            usuario_id=current_user.id, modulo='Firma Digital', accion='FIRMA APROBADA', 
            detalle=f"FirmaEC validada para trámite #{solicitud.id}. Metadata: {mensaje}"
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f'¡Trámite finalizado con éxito! {mensaje}', 'success')
    else:
        if os.path.exists(ruta_final):
            os.remove(ruta_final)
        
        log = LogAuditoria(usuario_id=current_user.id, modulo='Seguridad', accion='ALERTA FIRMA', detalle=f"Intento de firma inválida en trámite #{solicitud.id}")
        db.session.add(log)
        db.session.commit()
            
        flash(mensaje, 'danger')
            
    return redirect(url_for('dashboard.index'))