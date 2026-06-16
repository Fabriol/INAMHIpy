from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models.base import Usuario, SolicitudPazSalvo

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def index():
    # Consultamos datos reales de la base de datos para el banner del Dashboard
    total_usuarios = Usuario.query.filter_by(activo=True).count()
    total_documentos = SolicitudPazSalvo.query.count()
    
    return render_template(
        'dashboard/index.html', 
        total_usuarios=total_usuarios, 
        total_documentos=total_documentos
    )