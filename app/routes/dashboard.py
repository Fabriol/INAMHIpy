from flask import Blueprint, render_template
from flask_login import login_required
from app.models.base import Usuario, SolicitudPazSalvo

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def index():
    # Consultas para llenar tus tarjetas
    usuarios_activos = Usuario.query.filter_by(activo=True).count()
    doc_registrados = SolicitudPazSalvo.query.count()
    
    stats = {
        'usuarios_activos': usuarios_activos,
        'doc_registrados': doc_registrados
    }
    
    return render_template('dashboard/index.html', stats=stats)