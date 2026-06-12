from app import create_app, db

# Llamamos a la fábrica para crear nuestra aplicación
app = create_app()

# Este bloque asegura que el servidor solo se encienda si ejecutamos este archivo directamente
if __name__ == '__main__':
    # debug=True hace que el servidor se reinicie solo cada vez que guardas un cambio en el código
    app.run(debug=True, port=5000)