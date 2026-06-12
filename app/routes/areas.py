from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.base import db, SolicitudPazSalvo, Pregunta, Respuesta

areas_bp = Blueprint('areas', __name__)

@areas_bp.route('/areas/tareas')
@login_required
def mis_tareas():
    # 1. Validamos que solo las áreas resolutivas puedan acceder
    roles_areas = ['Administrativa', 'Financiera', 'TICs', 'Seguridad']
    if current_user.rol.nombre not in roles_areas:
        flash('Acceso denegado. No perteneces a un área de validación.', 'danger')
        return redirect(url_for('dashboard.index'))

    # 2. Mostramos los procesos que el Ex Funcionario ya llenó y están listos para revisión
    solicitudes = SolicitudPazSalvo.query.filter_by(estado='EN_PROGRESO').all()
    return render_template('areas/pendientes.html', solicitudes=solicitudes)

@areas_bp.route('/areas/responder/<int:solicitud_id>', methods=['GET', 'POST'])
@login_required
def responder_preguntas(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    
    # 3. FILTRO MÁGICO: Traemos SOLO las preguntas que el Admin asignó al ROL ACTUAL
    preguntas = Pregunta.query.filter_by(rol_asignado_id=current_user.rol_id, activa=True).all()

    if request.method == 'POST':
        for pregunta in preguntas:
            valor = request.form.get(f'pregunta_{pregunta.id}')
            observacion = request.form.get(f'observacion_{pregunta.id}')
            
            # REGLA ESTRICTA: Ningún campo puede quedar vacío
            if not valor:
                flash(f'Error de integridad: Debe responder a la pregunta "{pregunta.enunciado}".', 'danger')
                return redirect(url_for('areas.responder_preguntas', solicitud_id=solicitud.id))
            
            # Guardamos la respuesta asociando la solicitud, la pregunta y quién respondió
            nueva_respuesta = Respuesta(
                solicitud_id=solicitud.id,
                pregunta_id=pregunta.id,
                usuario_responde_id=current_user.id,
                valor_respuesta=valor,
                observacion=observacion
            )
            db.session.add(nueva_respuesta)
        
        db.session.commit()
        flash('Información guardada. Su validación departamental ha finalizado para este trámite.', 'success')
        return redirect(url_for('areas.mis_tareas'))

    return render_template('areas/responder.html', solicitud=solicitud, preguntas=preguntas)