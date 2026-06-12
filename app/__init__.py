from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()

login_manager.login_view = 'auth.login'
login_manager.login_message = 'Por favor, inicie sesión para acceder a esta página.'
login_manager.login_message_category = 'warning'

def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')
    
    db.init_app(app)
    login_manager.init_app(app)
    
    from app.models.base import Usuario
    @login_manager.user_loader
    def load_user(user_id):
        return Usuario.query.get(int(user_id))
        
    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp)
    
    from app.routes.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp)
    
    # --- NUEVO: Registramos la ruta de Paz y Salvo ---
    from app.routes.paz_salvo import paz_salvo_bp
    app.register_blueprint(paz_salvo_bp)

    # --- NUEVO: Registramos la ruta del Ex Funcionario ---
    from app.routes.ex_funcionario import ex_funcionario_bp
    app.register_blueprint(ex_funcionario_bp)
    
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))
    
    return app