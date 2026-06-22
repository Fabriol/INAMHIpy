from app import db
from flask_login import UserMixin
from datetime import datetime
import json

# ==========================================
# 1. TABLA DE AUDITORÍA (Rastreo Total)
# ==========================================
class Auditoria(db.Model):
    __tablename__ = 'auditoria'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, nullable=True) # Quién hizo el cambio
    accion = db.Column(db.String(50), nullable=False) # INSERT, UPDATE, LOGIN
    tabla_modificada = db.Column(db.String(50), nullable=False)
    registro_id = db.Column(db.Integer, nullable=False)
    detalles = db.Column(db.Text, nullable=True) # Qué cambió exactamente
    fecha = db.Column(db.DateTime, default=datetime.now)

# ==========================================
# 2. TABLA DE ROLES (Los 7 Oficiales)
# ==========================================
class Rol(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    
    # Relación: Un rol puede tener muchos usuarios
    usuarios = db.relationship('Usuario', backref='rol', lazy=True)

# ==========================================
# 3. TABLA DE USUARIOS (Login y Seguridad)
# UserMixin ayuda a Flask-Login a manejar las sesiones
# ==========================================
class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    rol_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    cedula = db.Column(db.String(10), unique=True, nullable=False)
    
    # Asegúrate de tener esta línea para guardar el usuario generado:
    username = db.Column(db.String(50), unique=True, nullable=True) 
    
    nombres = db.Column(db.String(100), nullable=False)
    apellidos = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    activo = db.Column(db.Boolean, default=True)
# ==========================================
# 4. TABLAS DEL FORMULARIO Y PREGUNTAS DINÁMICAS
# ==========================================
class Pregunta(db.Model):
    __tablename__ = 'preguntas'
    id = db.Column(db.Integer, primary_key=True)
    # A qué área/rol pertenece esta pregunta (Ej. TICs, Financiera)
    rol_asignado_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    enunciado = db.Column(db.String(255), nullable=False) # Ej: "¿Entregó la Laptop?"
    tipo_respuesta = db.Column(db.String(50), nullable=False) # Ej: "SI_NO", "TEXTO", "NUMERO"
    activa = db.Column(db.Boolean, default=True)

# ==========================================
# 5. TABLA DEL PROCESO DE PAZ Y SALVO (El Flujo)
# ==========================================
class SolicitudPazSalvo(db.Model):
    __tablename__ = 'solicitudes'
    id = db.Column(db.Integer, primary_key=True)
    ex_funcionario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    
    # Estados del Flujo: CREADO, EN_PROGRESO, REVISION_TH, APROBADO, NEGADO
    estado = db.Column(db.String(50), default='CREADO', nullable=False)
    
    # Fechas de control
    fecha_creacion = db.Column(db.DateTime, default=datetime.now)
    fecha_cierre = db.Column(db.DateTime, nullable=True)
    
    # Archivos y Firmas (Rutas donde se guardará el PDF)
    pdf_generado_path = db.Column(db.String(255), nullable=True)
    pdf_firmado_path = db.Column(db.String(255), nullable=True)
    
    # Aquí guardaremos la metadata que PyHanko extraiga de FirmaEC (el .p12)
    certificado_valido = db.Column(db.Boolean, default=False)
    certificado_metadata = db.Column(db.Text, nullable=True) 
    observacion_rechazo = db.Column(db.Text, nullable=True)

# ==========================================
# 6. TABLA DE RESPUESTAS (Cada área llena sus campos aquí)
# ==========================================
class Respuesta(db.Model):
    __tablename__ = 'respuestas'
    id = db.Column(db.Integer, primary_key=True)
    solicitud_id = db.Column(db.Integer, db.ForeignKey('solicitudes.id'), nullable=False)
    pregunta_id = db.Column(db.Integer, db.ForeignKey('preguntas.id'), nullable=False)
    usuario_responde_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    
    valor_respuesta = db.Column(db.String(255), nullable=False) # Obligatorio, no puede quedar vacío
    observacion = db.Column(db.String(255), nullable=True)
    fecha_respuesta = db.Column(db.DateTime, default=datetime.now)


class LogAuditoria(db.Model):
    __tablename__ = 'log_auditoria'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    modulo = db.Column(db.String(100), nullable=False)
    accion = db.Column(db.String(100), nullable=False)
    detalle = db.Column(db.Text, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

    # Relación para acceder a los datos del usuario que hizo la acción
    usuario = db.relationship('Usuario', backref=db.backref('logs', lazy=True))