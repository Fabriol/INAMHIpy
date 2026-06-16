from app import create_app
from app.models.base import db, Rol, Usuario
from werkzeug.security import generate_password_hash

# Inicializamos la aplicación para poder hablar con la base de datos
app = create_app()

with app.app_context():
    print("Iniciando la restauración de usuarios...")

    # 1. Asegurarnos de que todos los roles existan
    roles_institucionales = [
        'Administrador',
        'Talento Humano - Recepción Documentos',
        'Administrativa',
        'TICs',
        'Financiera',
        'Seguridad',
        'Ex Funcionario'
    ]
    
    for nombre_rol in roles_institucionales:
        rol = Rol.query.filter_by(nombre=nombre_rol).first()
        if not rol:
            nuevo_rol = Rol(nombre=nombre_rol, activa=True)
            db.session.add(nuevo_rol)
    
    # Guardamos los roles primero para poder usarlos en el paso 2
    db.session.commit()

    # 2. Diccionario con los usuarios que vamos a crear
    usuarios_prueba = [
        {'email': 'admin@inamhi.gob.ec', 'cedula': '0000000001', 'nombres': 'Super', 'apellidos': 'Administrador', 'rol': 'Administrador'},
        {'email': 'th@inamhi.gob.ec', 'cedula': '0000000002', 'nombres': 'Director', 'apellidos': 'Talento Humano', 'rol': 'Talento Humano - Recepción Documentos'},
        {'email': 'admin_area@inamhi.gob.ec', 'cedula': '0000000003', 'nombres': 'Jefe', 'apellidos': 'Administrativa', 'rol': 'Administrativa'},
        {'email': 'tics@inamhi.gob.ec', 'cedula': '0000000004', 'nombres': 'Soporte', 'apellidos': 'TICs', 'rol': 'TICs'},
        {'email': 'finanzas@inamhi.gob.ec', 'cedula': '0000000005', 'nombres': 'Auditor', 'apellidos': 'Financiera', 'rol': 'Financiera'},
        {'email': 'seguridad@inamhi.gob.ec', 'cedula': '0000000006', 'nombres': 'Oficial', 'apellidos': 'Seguridad', 'rol': 'Seguridad'},
    ]

    # 3. Insertar a los usuarios si no existen
    for u_data in usuarios_prueba:
        # Buscamos el ID del rol recién creado/verificado
        rol = Rol.query.filter_by(nombre=u_data['rol']).first()
        
        # Revisamos si el usuario ya existe por su correo
        usuario_existente = Usuario.query.filter_by(email=u_data['email']).first()
        
        if not usuario_existente:
            nuevo_usuario = Usuario(
                nombres=u_data['nombres'],
                apellidos=u_data['apellidos'],
                cedula=u_data['cedula'],
                email=u_data['email'],
                # Todos tendrán la misma contraseña inicial
                password_hash=generate_password_hash('admin123'),
                rol_id=rol.id,
                activo=True
            )
            db.session.add(nuevo_usuario)
            print(f"✅ Usuario creado: {u_data['email']} ({u_data['rol']})")
        else:
            print(f"⚠️ El usuario {u_data['email']} ya existía en la base.")

    # Guardamos todos los cambios definitivos
    db.session.commit()
    print("\n¡Proceso finalizado! Ya puedes iniciar sesión.")