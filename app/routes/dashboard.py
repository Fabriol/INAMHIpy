from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models.base import db, Usuario, SolicitudPazSalvo, LogAuditoria

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def index():
    # Calcular métricas reales para las tarjetas informativas
    stats = {
        'tramites_activos': SolicitudPazSalvo.query.filter(SolicitudPazSalvo.estado != 'COMPLETADO').count(),
        'tramites_completados': SolicitudPazSalvo.query.filter_by(estado='COMPLETADO').count(),
        'total_usuarios': Usuario.query.filter_by(activo=True).count(),
        'areas_control': 8,
        # SOLUCIÓN AQUÍ: Se cambió a pdf_firmado_path
        'firmas_validadas': SolicitudPazSalvo.query.filter(SolicitudPazSalvo.pdf_firmado_path.isnot(None)).count(),
        'logs_auditoria': LogAuditoria.query.count()
    }
    
    return render_template('dashboard/index.html', stats=stats)