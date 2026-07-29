from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models.base import db, Usuario, SolicitudPazSalvo, LogAuditoria, Respuesta

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def index():
    # Calcular métricas reales para las tarjetas informativas
    stats = {
        # Trámites que aún no tienen veredicto final de RRHH (siguen "en curso")
        'tramites_activos': SolicitudPazSalvo.query.filter(
            SolicitudPazSalvo.estado.notin_(['APROBADO', 'NEGADO'])
        ).count(),
        # Solo los Aprobados cuentan como expediente cerrado exitosamente
        'tramites_completados': SolicitudPazSalvo.query.filter_by(estado='APROBADO').count(),
        'total_usuarios': Usuario.query.filter_by(activo=True).count(),
        'areas_control': 8,
        # Cuenta firmas PAdES reales estampadas (campos marcados FIRMADO), no el
        # campo pdf_firmado_path que solo usa el flujo antiguo de subida manual
        'firmas_validadas': Respuesta.query.filter_by(valor_respuesta='FIRMADO').count(),
        'logs_auditoria': LogAuditoria.query.count()
    }
    
    # Alerta visible e imposible de pasar por alto para el Ex Funcionario
    # cuando su trámite fue Negado por RRHH
    tramite_negado = None
    if current_user.rol.nombre == 'Ex Funcionario':
        tramite_negado = SolicitudPazSalvo.query.filter_by(
            ex_funcionario_id=current_user.id, estado='NEGADO'
        ).first()

    return render_template('dashboard/index.html', stats=stats, tramite_negado=tramite_negado)