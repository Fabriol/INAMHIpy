import os

class Config:
    # Clave secreta para proteger las sesiones y las cookies (Requisito de seguridad)
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'clave-super-secreta-inamhi-2026'
    
    # ==========================================
    # CONFIGURACIÓN DE CONEXIÓN A MYSQL 8
    # ==========================================
    # Formato: mysql+pymysql://usuario:contraseña@servidor/nombre_base_datos
    # Cambia 'tu_contraseña_aqui' por tu contraseña real de MySQL
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'mysql+pymysql://root:root@localhost/paz_salvo_db'
    
    # Desactivamos esta opción porque consume mucha memoria innecesariamente
    SQLALCHEMY_TRACK_MODIFICATIONS = False