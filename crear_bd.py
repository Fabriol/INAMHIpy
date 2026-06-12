from app import create_app, db
from app.models.base import Rol, Usuario
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    print("Iniciando inyección de datos básicos...")
    db.create_all()

    # 1. Asegurar roles
    roles = ["Administrador", "Talento Humano - Recepción Documentos", "Ex Funcionario", 
             "Administrativa", "Financiera", "TICs", "Seguridad"]
    
    for nombre_rol in roles:
        if not Rol.query.filter_by(nombre=nombre_rol).first():
            db.session.add(Rol(nombre=nombre_rol))
    db.session.commit()

    # 2. Crear al primer Usuario Administrador para que puedas entrar
    rol_admin = Rol.query.filter_by(nombre="Administrador").first()
    
    if not Usuario.query.filter_by(email="admin@inamhi.gob.ec").first():
        admin = Usuario(
            rol_id=rol_admin.id,
            cedula="0000000000",
            nombres="Administrador",
            apellidos="Del Sistema",
            email="admin@inamhi.gob.ec",
            password_hash=generate_password_hash("admin123") # Contraseña segura
        )
        db.session.add(admin)
        db.session.commit()
        print("¡Usuario Administrador creado con éxito!")
        print("-> Correo: admin@inamhi.gob.ec")
        print("-> Clave: admin123")
    else:
        print("El Administrador ya existía en la base de datos.")

    print("Proceso terminado.")