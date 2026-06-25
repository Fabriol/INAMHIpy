from app import db
from flask_login import UserMixin
from datetime import datetime

# ==========================================
# 1. TABLA DE AUDITORÍA (Rastreo Total)
# ==========================================
class Auditoria(db.Model):
    __tablename__ = 'auditoria'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, nullable=True) 
    accion = db.Column(db.String(50), nullable=False) 
    tabla_modificada = db.Column(db.String(50), nullable=False)
    registro_id = db.Column(db.Integer, nullable=False)
    detalles = db.Column(db.Text, nullable=True) 
    fecha = db.Column(db.DateTime, default=datetime.now)

# ==========================================
# 2. TABLA DE ROLES
# ==========================================
class Rol(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    usuarios = db.relationship('Usuario', backref='rol', lazy=True)

# ==========================================
# 3. TABLA DE USUARIOS
# ==========================================
class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    rol_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    cedula = db.Column(db.String(10), unique=True, nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=True) 
    nombres = db.Column(db.String(100), nullable=False)
    apellidos = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    activo = db.Column(db.Boolean, default=True)

# ==========================================
# 4. TABLAS DE PREGUNTAS (Sistema Legacy)
# ==========================================
class Pregunta(db.Model):
    __tablename__ = 'preguntas'
    id = db.Column(db.Integer, primary_key=True)
    rol_asignado_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    enunciado = db.Column(db.String(255), nullable=False)
    tipo_respuesta = db.Column(db.String(50), nullable=False) 
    activa = db.Column(db.Boolean, default=True)

# ==========================================
# 5. TABLA DEL PROCESO DE PAZ Y SALVO
# ==========================================
class SolicitudPazSalvo(db.Model):
    __tablename__ = 'solicitudes'
    id = db.Column(db.Integer, primary_key=True)
    ex_funcionario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    estado = db.Column(db.String(50), default='CREADO', nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.now)
    fecha_cierre = db.Column(db.DateTime, nullable=True)
    pdf_generado_path = db.Column(db.String(255), nullable=True)
    pdf_firmado_path = db.Column(db.String(255), nullable=True)
    certificado_valido = db.Column(db.Boolean, default=False)
    certificado_metadata = db.Column(db.Text, nullable=True) 
    observacion_rechazo = db.Column(db.Text, nullable=True)

# ==========================================
# 6. TABLA DE RESPUESTAS (ACTUALIZADA PARA EL NUEVO SISTEMA)
# ==========================================
class Respuesta(db.Model):
    __tablename__ = 'respuestas'
    id = db.Column(db.Integer, primary_key=True)
    solicitud_id = db.Column(db.Integer, db.ForeignKey('solicitudes.id'), nullable=False)
    
    # NUEVO: Guarda el ID del campo HTML exacto (Ej: 'tic_backup', 'admin_r1')
    campo_formulario = db.Column(db.String(100), nullable=False) 
    
    # NUEVO: A quién le delegó el Administrador llenar este campo
    usuario_asignado_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True) 
    
    # Ahora puede ser nulo al inicio, porque el admin lo asigna vacío hasta que el usuario lo llene
    valor_respuesta = db.Column(db.String(255), nullable=True) 
    
    observacion = db.Column(db.String(255), nullable=True)
    fecha_respuesta = db.Column(db.DateTime, default=datetime.now)


# ==========================================
# 7. LOGS DE AUDITORÍA
# ==========================================
class LogAuditoria(db.Model):
    __tablename__ = 'log_auditoria'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    modulo = db.Column(db.String(100), nullable=False)
    accion = db.Column(db.String(100), nullable=False)
    detalle = db.Column(db.Text, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    usuario = db.relationship('Usuario', backref=db.backref('logs', lazy=True))