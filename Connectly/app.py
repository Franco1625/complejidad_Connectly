import os, uuid
from flask import Flask, g, render_template, redirect, url_for, request, session, send_from_directory, jsonify
from flask_cors import CORS
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime
from community_connection.script.community_data import CommunityData

# Crear instancia de Flask
app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Llave secreta para manejar sesiones
CORS(app, supports_credentials=True)  # Habilitar CORS para manejo de cookies

# Configuración de Flask-SocketIO para comunicación en tiempo real
socketio = SocketIO(app)

# Configuración de conexión a la base de datos
db_url = 'mysql+mysqlconnector://root:nicolas20@localhost:3306/connectly'
community_data_instance = CommunityData(db_url)  # Instancia para manejar datos comunitarios
engine = create_engine(db_url)  # Motor SQLAlchemy
SessionLocal = sessionmaker(bind=engine)  # Sesiones para interacciones con la base de datos

# Crear carpeta para almacenar imágenes subidas
STORAGE_FOLDER = os.path.join(os.path.dirname(__file__), 'storage')
os.makedirs(STORAGE_FOLDER, exist_ok=True)  # Crear carpeta si no existe

# Ruta de inicio, redirige al login
@app.route('/')
def home():
    return redirect(url_for('login'))

# Ruta para el inicio de sesión
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':  # Procesar formulario de inicio de sesión
        username = request.form.get('username')
        password = request.form.get('password')

        query = text("""
            SELECT UserID, password 
            FROM social_media_users 
            WHERE username = :username
        """)

        with engine.connect() as connection:
            result = connection.execute(query, {"username": username}).fetchone()

            if result:
                user_id, stored_password = result
                if stored_password == password:  # Validar contraseña
                    session['user_id'] = int(user_id)  # Guardar usuario en sesión
                    session.permanent = True  # Mantener sesión activa
                    return redirect(url_for('profile', user_id=user_id))
                else:
                    return render_template('login.html', error="Contraseña incorrecta. Intente nuevamente.")
            else:
                return render_template('login.html', error="Usuario no encontrado. Intente nuevamente.")
    
    return render_template('login.html')  # Mostrar formulario de login

# Ruta para el perfil de usuario
@app.route('/profile/<int:user_id>')
def profile(user_id):
    current_user_id = session.get('user_id')  # Obtener usuario autenticado
    is_own_profile = (current_user_id == user_id)  # Verificar si es el perfil propio

    # Obtener datos del perfil y estadísticas
    user_data, same_interest_users = community_data_instance.get_user_profile(user_id)
    post_count = community_data_instance.get_post_count(user_id)
    follower_count = community_data_instance.get_follower_count(user_id)
    following_count = community_data_instance.get_following_count(user_id)

    # Filtro de usuarios según género e interés
    user_interest = user_data['interest'] if user_data else None
    gender_filter = request.args.get('gender')
    if gender_filter and user_interest:
        same_interest_users = community_data_instance.get_users_by_gender_and_interest(
            gender_filter, user_interest, current_user_id
        )

    # Obtener recomendaciones de usuarios (solo para perfiles propios)
    recommended_users = community_data_instance.get_user_recommendations(user_id) if is_own_profile else []

    # Verificar si el usuario autenticado sigue al perfil visitado
    is_following = community_data_instance.is_following(current_user_id, user_id) if current_user_id else False

    # Obtener listas de seguidores y seguidos
    followers = community_data_instance.get_followers(user_id, current_user_id)
    following = community_data_instance.get_following(user_id, current_user_id)

    for similar_user in same_interest_users:  # Verificar estado de seguimiento para usuarios similares
        similar_user['is_following'] = community_data_instance.is_following(
            current_user_id, similar_user['user_id']
        ) if current_user_id else False

    # Obtener publicaciones del usuario visitado
    query = text("""
        SELECT PostID, Content, PostDate, Image
        FROM posts
        WHERE UserID = :user_id
        ORDER BY PostDate DESC
    """)
    with engine.connect() as connection:
        user_posts = connection.execute(query, {"user_id": user_id}).fetchall()

    # Renderizar plantilla del perfil con los datos obtenidos
    return render_template(
        'profile.html',
        user=user_data,
        similar_users=same_interest_users,
        user_posts=user_posts,
        recommended_users=recommended_users,
        post_count=post_count,
        follower_count=follower_count,
        following_count=following_count,
        is_own_profile=is_own_profile,
        is_following=is_following,
        followers=followers,
        following=following,
        chat_user_id=user_id
    )


# Ruta para filtrar usuarios según género y país
@app.route('/filter_users', methods=['GET'])
def filter_users():
    gender = request.args.get('gender')  # Obtener filtro de género
    country = request.args.get('country')  # Obtener filtro de país
    profile_user_id = request.args.get('profile_user_id', type=int)  # ID del perfil visitado
    current_user_id = session.get('user_id')  # ID del usuario autenticado

    # Obtener perfil del usuario visitado y sus intereses
    user_data, _ = community_data_instance.get_user_profile(profile_user_id)
    user_interest = user_data['interest'] if user_data else None

    # Filtrar usuarios según género, país e intereses
    filtered_users = [
        user for user in community_data_instance.user_groups.values()
        if (not gender or user["gender"] == gender)
        and (not country or user.get("country") == country)
        and (not user_interest or user["interest"] == user_interest) 
        and user["user_id"] != profile_user_id  # Excluir al perfil visitado
    ]

    # Verificar si los usuarios filtrados están siendo seguidos
    for user in filtered_users:
        user["is_following"] = community_data_instance.is_following(current_user_id, user["user_id"])

    return jsonify({"filtered_users": filtered_users})  # Devolver usuarios filtrados como JSON

# Ruta para obtener conteos de filtros (género, país, etc.) para un perfil específico
@app.route('/get_filter_counts_for_profile/<int:profile_user_id>', methods=['GET'])
def get_filter_counts_for_profile(profile_user_id):
    filter_counts = community_data_instance.get_filter_counts_for_profile(profile_user_id)  # Obtener conteos
    return jsonify(filter_counts)

# Ruta para obtener países únicos de los usuarios
@app.route('/get_countries', methods=['GET'])
def get_countries():
    countries = community_data_instance.get_unique_countries()  # Obtener lista de países únicos
    return jsonify({"countries": countries})

# Ruta para crear una nueva publicación
@app.route('/create_post', methods=['GET', 'POST'])
def create_post():
    if 'user_id' not in session:  # Verificar si el usuario está autenticado
        return redirect(url_for('login'))
    
    if request.method == 'POST':  # Procesar formulario para crear publicación
        content = request.form.get('content')  # Obtener contenido de la publicación
        image = request.files.get('image')  # Obtener imagen de la publicación (opcional)
        user_id = session['user_id']

        # Guardar imagen en la carpeta de almacenamiento
        image_path = None
        if image:
            filename = f"{user_id}_{int(datetime.timestamp(datetime.now()))}_{image.filename}"
            image_path = os.path.join(STORAGE_FOLDER, filename)
            try:
                image.save(image_path)  # Guardar imagen localmente
                image_path = f"/storage/{filename}"  # Ruta relativa para acceso público
            except Exception as e:
                user_data, _ = community_data_instance.get_user_profile(user_id)
                return render_template('post_form.html', error="Error al guardar la imagen. Intente nuevamente.", user=user_data)

        # Insertar nueva publicación en la base de datos
        try:
            query = text("""
                INSERT INTO posts (UserID, Content, Image, PostDate)
                VALUES (:user_id, :content, :image, :post_date)
            """)
            with SessionLocal() as db_session:
                db_session.execute(query, {
                    "user_id": user_id,
                    "content": content,
                    "image": image_path,
                    "post_date": datetime.now()
                })
                db_session.commit()
        except Exception as e:
            user_data, _ = community_data_instance.get_user_profile(user_id)
            return render_template('post_form.html', error="Error al crear la publicación. Intente nuevamente.", user=user_data)
        
        return redirect(url_for('index'))  # Redirigir a la página de inicio
    
    # Mostrar formulario para crear publicación
    user_data, _ = community_data_instance.get_user_profile(session['user_id'])
    return render_template('post_form.html', user=user_data)

# Ruta para eliminar una publicación
@app.route('/delete_post/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    if 'user_id' not in session:  # Verificar autenticación
        return redirect(url_for('login'))
    
    user_id = session['user_id']

    # Consultar información de la publicación
    query = text("""
        SELECT Image, UserID
        FROM posts
        WHERE PostID = :post_id
    """)
    
    with engine.connect() as connection:
        post = connection.execute(query, {"post_id": post_id}).fetchone()
        
        if not post:  # Verificar si la publicación existe
            return redirect(url_for('profile', user_id=user_id))
        
        post_image_path, post_user_id = post
        
        if post_user_id != user_id:  # Verificar si el usuario es el dueño de la publicación
            return redirect(url_for('profile', user_id=user_id))

        if post_image_path and os.path.exists(post_image_path):  # Eliminar la imagen asociada
            os.remove(post_image_path)

    # Eliminar la publicación de la base de datos
    delete_query = text("DELETE FROM posts WHERE PostID = :post_id")
    with SessionLocal() as db_session:
        db_session.execute(delete_query, {"post_id": post_id})
        db_session.commit()
    
    return redirect(url_for('profile', user_id=user_id))  # Redirigir al perfil

# Ruta para obtener la lista de seguidores de un usuario
@app.route('/followers/<int:user_id>')
def followers(user_id):
    if 'user_id' not in session:  # Verificar si el usuario está autenticado
        return redirect(url_for('login'))

    current_user_id = session['user_id']  # Usuario autenticado
    followers_list = community_data_instance.get_followers(user_id, current_user_id)  # Obtener seguidores del usuario
    user_data, _ = community_data_instance.get_user_profile(user_id)  # Obtener información del usuario

    # Procesar lista de seguidores para incluir información adicional
    processed_followers = []
    for follower in followers_list:
        follower_data = {
            "user_id": follower["user_id"],
            "name": follower["name"],
            "profile_image": follower["profile_image"],
            "is_following": community_data_instance.is_following(current_user_id, follower["user_id"]),
            "follows_authenticated_user": community_data_instance.is_following(follower["user_id"], current_user_id)
        }
        processed_followers.append(follower_data)

    return render_template('followers.html', followers=processed_followers, user=user_data)

# Ruta para obtener la lista de usuarios que un usuario sigue
@app.route('/following/<int:user_id>')
def following(user_id):
    if 'user_id' not in session:  # Verificar autenticación
        return redirect(url_for('login'))

    current_user_id = session['user_id']  # Usuario autenticado
    following_list = community_data_instance.get_following(user_id, current_user_id)  # Obtener lista de seguidos
    user_data, _ = community_data_instance.get_user_profile(user_id)  # Información del perfil visitado
    is_own_profile = (current_user_id == user_id)  # Verificar si el perfil es del usuario autenticado

    return render_template('following.html', following=following_list, user=user_data, is_own_profile=is_own_profile)

# Ruta para seguir a un usuario
@app.route('/follow/<int:user_id>', methods=['POST'])
def follow(user_id):
    if 'user_id' not in session:  # Verificar autenticación
        return jsonify(success=False, error="Usuario no autenticado.")

    follower_id = session['user_id']  # Usuario autenticado

    if follower_id == user_id:  # No se puede seguir a uno mismo
        return jsonify(success=False, error="No puedes seguirte a ti mismo.")

    success = community_data_instance.follow_user(follower_id, user_id)  # Ejecutar acción de seguimiento

    if success:
        return jsonify(
            success=True,
            is_profile_visited=(follower_id != user_id),
            is_logged_in_user=(follower_id == session['user_id'])
        )
    else:
        return jsonify(success=False, error="No se pudo seguir al usuario.")

# Ruta para dejar de seguir a un usuario
@app.route('/unfollow/<int:user_id>', methods=['POST'])
def unfollow(user_id):
    if 'user_id' not in session:  # Verificar autenticación
        return jsonify(success=False, error="Usuario no autenticado.")

    follower_id = session['user_id']  # Usuario autenticado

    if follower_id == user_id:  # No se puede dejar de seguir a uno mismo
        return jsonify(success=False, error="No puedes dejar de seguirte a ti mismo.")

    success = community_data_instance.unfollow_user(follower_id, user_id)  # Ejecutar acción de dejar de seguir

    if success:
        return jsonify(
            success=True,
            is_profile_visited=(follower_id != user_id),
            is_logged_in_user=(follower_id == session['user_id'])
        )
    else:
        return jsonify(success=False, error="No se pudo dejar de seguir al usuario.")

# Ruta para obtener los comentarios de una publicación
@app.route('/get_comments/<int:post_id>', methods=['GET'])
def get_comments(post_id):
    comments = community_data_instance.get_comments_for_post(post_id)  # Obtener lista de comentarios
    return jsonify(comments)  # Devolver los comentarios como JSON

# Ruta para dar like a una publicación
@app.route('/like_post/<int:post_id>', methods=['POST'])
def like_post(post_id):
    if 'user_id' not in session:  # Verificar autenticación
        return jsonify({"error": "Unauthorized"}), 401
    
    user_id = session['user_id']  # Usuario autenticado
    community_data_instance.like_post(post_id, user_id)  # Ejecutar acción de dar like
    like_count = community_data_instance.get_like_count(post_id)  # Obtener el conteo de likes actual
    return jsonify({"success": True, "like_count": like_count})

# Ruta para quitar un like de una publicación
@app.route('/unlike_post/<int:post_id>', methods=['POST'])
def unlike_post(post_id):
    if 'user_id' not in session:  # Verificar autenticación
        return jsonify({"error": "Unauthorized"}), 401
    
    user_id = session['user_id']  # Usuario autenticado
    community_data_instance.unlike_post(post_id, user_id)  # Ejecutar acción de quitar like
    like_count = community_data_instance.get_like_count(post_id)  # Obtener el conteo de likes actual
    return jsonify({"success": True, "like_count": like_count})

# Ruta para agregar un comentario a una publicación
@app.route('/add_comment/<int:post_id>', methods=['POST'])
def add_comment(post_id):
    if 'user_id' not in session:  # Verificar autenticación
        return jsonify({"error": "Unauthorized"}), 401

    content = request.form.get('comment_content')  # Obtener contenido del comentario
    user_id = session['user_id']  # Usuario autenticado

    if content:
        community_data_instance.add_comment(post_id, user_id, content)  # Agregar el comentario
        return jsonify({"success": True})
    
    return jsonify({"error": "No content provided"}), 400  # Error si no hay contenido

# Ruta para enviar un mensaje directo a otro usuario
@app.route('/send_message', methods=['POST'])
def send_message():
    if 'user_id' not in session:  # Verificar autenticación
        return jsonify({"error": "Unauthorized"}), 401

    sender_id = session['user_id']  # ID del remitente
    receiver_id = request.form.get('receiver_id')  # ID del receptor
    content = request.form.get('content')  # Contenido del mensaje
    image_file = request.files.get('image')  # Archivo de imagen opcional

    # Obtener imagen de perfil del remitente
    query = text("SELECT profile_image FROM social_media_users WHERE UserID = :sender_id")
    with engine.connect() as connection:
        result = connection.execute(query, {"sender_id": sender_id}).fetchone()
        profile_image = result.profile_image if result else None

    # Guardar imagen asociada al mensaje
    image_path = None
    if image_file:
        filename = f"{sender_id}_{int(datetime.timestamp(datetime.now()))}_{uuid.uuid4().hex}.png"
        image_path = os.path.join(STORAGE_FOLDER, filename)
        image_file.save(image_path)
        image_path = f"/storage/{filename}"

    # Insertar el mensaje en la base de datos
    query = text("""
        INSERT INTO messages (sender_id, receiver_id, content, image, sent_at)
        VALUES (:sender_id, :receiver_id, :content, :image, NOW())
    """)
    with SessionLocal() as db_session:
        db_session.execute(query, {
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "content": content,
            "image": image_path
        })
        db_session.commit()

    # Emitir el mensaje a través de SocketIO
    socketio.emit('receive_message', {
        'sender_id': sender_id,
        'receiver_id': receiver_id,
        'content': content,
        'image': image_path,
        'profile_image': profile_image,
        'sent_at': datetime.now().isoformat()
    }, room=f'chat_{min(sender_id, int(receiver_id))}_{max(sender_id, int(receiver_id))}')

    return jsonify({"success": True})


# Evento de SocketIO para unirse a una sala de chat
@socketio.on('join')
def on_join(data):
    user_id = data['user_id']  # ID del usuario que se une
    selected_user_id = data.get('selected_user_id')  # ID del usuario seleccionado para chatear
    if selected_user_id:
        # Crear un identificador único para la sala basado en los IDs de los usuarios
        room = f'chat_{min(user_id, selected_user_id)}_{max(user_id, selected_user_id)}'
        join_room(room)  # Unirse a la sala de chat

# Ruta para obtener mensajes entre el usuario autenticado y otro usuario
@app.route('/get_messages/<int:user_id>', methods=['GET'])
def get_messages(user_id):
    if 'user_id' not in session:  # Verificar si el usuario está autenticado
        return jsonify({"error": "Unauthorized"}), 401

    current_user_id = session['user_id']  # ID del usuario autenticado

    # Verificar si ambos usuarios se siguen mutuamente
    if not (community_data_instance.is_following(current_user_id, user_id) and community_data_instance.is_following(user_id, current_user_id)):
        return jsonify({"error": "You need to follow each other to chat"}), 403

    # Consultar mensajes entre los usuarios ordenados por fecha de envío
    query = text("""
        SELECT sender_id, receiver_id, content, sent_at
        FROM messages
        WHERE (sender_id = :current_user_id AND receiver_id = :user_id) 
           OR (sender_id = :user_id AND receiver_id = :current_user_id)
        ORDER BY sent_at ASC
    """)
    with engine.connect() as connection:
        messages = connection.execute(query, {"current_user_id": current_user_id, "user_id": user_id}).fetchall()
        # Formatear los mensajes en una lista de diccionarios
        messages_data = [
            {"sender_id": msg.sender_id, "receiver_id": msg.receiver_id, "content": msg.content, "sent_at": msg.sent_at.isoformat()}
            for msg in messages
        ]
    
    return jsonify(messages_data)  # Devolver los mensajes como JSON

# Middleware para cargar el usuario autenticado en cada solicitud
@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')  # Obtener ID del usuario autenticado
    if user_id:
        # Consultar datos del usuario autenticado
        query = text("SELECT UserID, username, profile_image FROM social_media_users WHERE UserID = :user_id")
        with engine.connect() as connection:
            user = connection.execute(query, {"user_id": user_id}).fetchone()
            if user:
                # Guardar datos del usuario en la variable global `g`
                g.user = {
                    "user_id": user.UserID,
                    "username": user.username,
                    "profile_image": user.profile_image
                }
    else:
        g.user = None  # No hay usuario autenticado

# Ruta para acceder a la página de chat
@app.route('/chat')
def chat():
    if 'user_id' not in session:  # Verificar autenticación
        return redirect(url_for('login'))

    current_user_id = session['user_id']  # ID del usuario autenticado
    mutual_followers = community_data_instance.get_mutual_followers(current_user_id)  # Seguidores mutuos

    selected_user_id = request.args.get('user_id', type=int)  # Usuario seleccionado para chatear
    messages = []

    if selected_user_id:
        # Obtener mensajes entre los usuarios seleccionados
        messages = community_data_instance.get_messages_between_users(current_user_id, selected_user_id)

    return render_template('chat.html', mutual_followers=mutual_followers, messages=messages, selected_user_id=selected_user_id)

# Ruta para mostrar el feed de publicaciones en la página principal
@app.route('/home')
def index():
    user_id = session.get('user_id')  # ID del usuario autenticado
    user_data, _ = community_data_instance.get_user_profile(user_id) if user_id else (None, None)  # Datos del usuario autenticado

    # Consultar publicaciones recientes con información del autor
    query = text("""
        SELECT p.PostID, p.Content, p.PostDate, p.Image, u.Name, u.profile_image, u.UserID, u.Interests
        FROM posts p
        JOIN social_media_users u ON p.UserID = u.UserID
        ORDER BY p.PostDate DESC
    """)
    with engine.connect() as connection:
        posts_raw = connection.execute(query).fetchall()

    # Procesar las publicaciones para incluir conteo de likes e información adicional
    posts = [
        {
            "PostID": post[0],
            "Content": post[1],
            "PostDate": post[2],
            "Image": post[3],
            "Name": post[4],
            "profile_image": post[5],
            "UserID": post[6],
            "interest": post[7].split(', ')[0].strip(" '\""),
            "like_count": community_data_instance.get_like_count(post[0]),
            "is_post_liked": community_data_instance.is_post_liked(post[0], user_id) if user_id else False
        }
        for post in posts_raw
    ]

    return render_template('home.html', posts=posts, user=user_data)  # Renderizar el feed

# Ruta para servir imágenes almacenadas
@app.route('/storage/<path:filename>')
def serve_image(filename):
    return send_from_directory(STORAGE_FOLDER, filename)  # Enviar imagen desde la carpeta de almacenamiento

# Ruta para cerrar sesión
@app.route('/logout')
def logout():
    session.pop('user_id', None)  # Eliminar usuario de la sesión
    return redirect(url_for('login'))  # Redirigir al login

# Punto de entrada principal
if __name__ == '__main__':
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)  # Ejecutar la aplicación con soporte para SocketIO
    
    
