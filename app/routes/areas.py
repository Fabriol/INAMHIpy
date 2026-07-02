from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

# Importamos Usuario y Rol que nos faltaban aquí
from app.models.base import db, SolicitudPazSalvo, Pregunta, Respuesta, LogAuditoria, Usuario, Rol

areas_bp = Blueprint('areas', __name__)

# ==========================================
# 1. RUTA: PANEL DE DOCUMENTOS / TAREAS
# ==========================================
@areas_bp.route('/areas/tareas')
@login_required
def mis_tareas():
    # Incluimos el rol de Talento Humano dentro de las áreas permitidas
    roles_areas = ['Administrativa', 'Financiera', 'TICs', 'Seguridad', 'Administrador', 'Talento Humano - Recepción Documentos']
    
    if current_user.rol.nombre not in roles_areas:
        flash('Acceso denegado. No perteneces a un área de validación.', 'danger')
        return redirect(url_for('dashboard.index'))

    if current_user.rol.nombre in ['Administrador', 'Talento Humano - Recepción Documentos']:
        solicitudes = SolicitudPazSalvo.query.order_by(SolicitudPazSalvo.fecha_creacion.desc()).all()
    else:
        solicitudes = SolicitudPazSalvo.query.filter_by(estado='EN_PROGRESO').all()
        
    # Inyectamos el usuario manualmente para quitar el "Dato No Vinculado"
    for sol in solicitudes:
        sol.usuario_data = Usuario.query.get(sol.ex_funcionario_id)
        
    return render_template('areas/pendientes.html', solicitudes=solicitudes)


# ==========================================
# 2. RUTA: VISTA PREVIA DEL DOCUMENTO
# ==========================================
@areas_bp.route('/areas/ver/<int:solicitud_id>')
@login_required
def vista_previa(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    
    # Preparamos los datos exactos que necesita la Hoja Espejo para dibujarse
    solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
    
    preguntas = Pregunta.query.all()
    for p in preguntas:
        rol_obj = Rol.query.get(p.rol_asignado_id)
        p.area_nombre = rol_obj.nombre if rol_obj else 'ÁREA TÉCNICA'
        
    return render_template('areas/vista_previa.html', solicitud=solicitud, preguntas=preguntas)


# ==========================================
# 3. RUTA: RESPONDER PREGUNTAS / EMITIR DICTAMEN FINAL
# ==========================================
@areas_bp.route('/areas/responder/<int:solicitud_id>', methods=['GET', 'POST'])
@login_required
def responder_preguntas(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
    
    if current_user.rol.nombre == 'Administrador':
        preguntas = Pregunta.query.filter_by(activa=True).all()
    else:
        preguntas = Pregunta.query.filter_by(rol_asignado_id=current_user.rol_id, activa=True).all()

    if request.method == 'POST':
        # Capturamos el dictamen final enviado por RRHH o Administrador
        estado_final = request.form.get('estado_final')
        observacion_final = request.form.get('observacion_final')

        # CASO 1: Es una validación final de Talento Humano o Administrador
        if estado_final:
            solicitud.estado = str(estado_final).upper()
            detalle_auditoria = f"Emitió veredicto final: {estado_final}."

            if estado_final == 'Negado':
                # Almacenamos la observación del rechazo en la solicitud
                solicitud.observacion_rechazo = str(observacion_final).upper()
                detalle_auditoria += f" Motivo: {observacion_final}"
                flash(f'Trámite negado de forma oficial. Se registró el motivo del rechazo.', 'warning')

            elif estado_final == 'Aprobado':
                # El usuario ex funcionario pasa a estado INHABILITADO y se bloquea su acceso
                ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
                if ex_funcionario:
                    ex_funcionario.activo = False # Bloqueo inmediato en la autenticación
                flash('Trámite Aprobado Exitosamente. El expediente se ha cerrado y el ex-funcionario fue inhabilitado.', 'success')

            # Registramos la acción en la tabla de auditoría del sistema
            log = LogAuditoria(
                usuario_id=current_user.id, 
                modulo='Validación de Áreas', 
                accion='DICTAMEN FINAL', 
                detalle=f"El usuario {current_user.rol.nombre} procesó el trámite #{solicitud.id}. {detalle_auditoria}"
            )
            db.session.add(log)
            db.session.commit()
            return redirect(url_for('areas.mis_tareas'))

        # CASO 2: Es una respuesta estándar a las preguntas del cuestionario por áreas
        respuestas_guardadas = []
        for pregunta in preguntas:
            valor = request.form.get(f'pregunta_{pregunta.id}')
            observacion = request.form.get(f'observacion_{pregunta.id}')
            
            if not valor:
                flash(f'Error de integridad: Debe responder a la pregunta "{pregunta.enunciado}".', 'danger')
                return redirect(url_for('areas.responder_preguntas', solicitud_id=solicitud.id))
            
            respuesta_existente = Respuesta.query.filter_by(solicitud_id=solicitud.id, pregunta_id=pregunta.id).first()
            if respuesta_existente:
                respuesta_existente.valor_respuesta = valor
                respuesta_existente.observacion = observacion
            else:
                nueva_respuesta = Respuesta(
                    solicitud_id=solicitud.id, 
                    pregunta_id=pregunta.id, 
                    usuario_responde_id=current_user.id, 
                    valor_respuesta=valor, 
                    observacion=observacion
                )
                db.session.add(nueva_respuesta)
            
            respuestas_guardadas.append(f"P{pregunta.id}:{valor}")
        
        log = LogAuditoria(
            usuario_id=current_user.id, 
            modulo='Validación de Áreas', 
            accion='ÁREA RESPONDE', 
            detalle=f"El área {current_user.rol.nombre} validó el trámite #{solicitud.id}. Respuestas: [{', '.join(respuestas_guardadas)}]"
        )
        db.session.add(log)
        db.session.commit()
        
        flash('Información guardada exitosamente.', 'success')
        return redirect(url_for('areas.mis_tareas'))

    return render_template('areas/responder.html', solicitud=solicitud, preguntas=preguntas)