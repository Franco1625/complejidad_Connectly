## Este archivo contiene la lógica de la aplicación web Connectly, que es una red social simple que permite a los usuarios registrarse, seguirse entre sí, publicar publicaciones, comentar y chatear en tiempo real. La aplicación utiliza Flask para el backend y la base de datos MySQL para almacenar los datos de los usuarios, publicaciones y mensajes. También utiliza Flask-SocketIO para la funcionalidad de chat en tiempo real.
import os, uuid
from pyvis.network import Network
from flask import Flask, g, render_template, redirect, url_for, request, session, send_from_directory, jsonify
from flask_cors import CORS
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime
from community_connection.script.community_data import CommunityData

## Crear la aplicación Flask
app = Flask(__name__)
app.secret_key = 'supersecretkey'
CORS(app, supports_credentials=True)

# configuración de Flask-SocketIO para el manejo de mensajes en tiempo real entre seguidores
socketio = SocketIO(app)

# Conexión a la base de datos y creación de instancias de CommunityData
db_url = 'mysql+mysqlconnector://root:root@localhost:3306/prueba2'
community_data_instance = CommunityData(db_url)
engine = create_engine(db_url)
SessionLocal = sessionmaker(bind=engine)

# Crear la carpeta de almacenamiento para las imágenes de chat y posts
STORAGE_FOLDER = os.path.join(os.path.dirname(__file__), 'storage')
os.makedirs(STORAGE_FOLDER, exist_ok=True)

## Rutas de la aplicación
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/admin_dashboard')
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    return render_template('admin_dashboard.html', user_id=session.get('user_id'))

@app.route('/view_all_users', methods=['GET'])
def view_all_users():
    if not session.get('is_admin'):
        return redirect(url_for('login'))

    # Obtener el interés seleccionado del parámetro GET
    selected_interest = request.args.get('interest', '')

    # Obtener todos los intereses únicos
    interests = sorted(set(user['interest'] for user in community_data_instance.user_groups.values()))

    # Filtrar los usuarios según el interés seleccionado
    if selected_interest:
        users = [
            user for user in community_data_instance.user_groups.values()
            if user['interest'] == selected_interest
        ]
    else:
        users = community_data_instance.user_groups.values()

    return render_template(
        'view_all_users.html',
        users=users,
        interests=interests,
        selected_interest=selected_interest
    )

@app.route('/admin_graph', methods=['GET'])
def admin_graph():
    if not session.get('is_admin'):
        return redirect(url_for('login'))

    # Limitar la cantidad de nodos desde los parámetros GET
    limit = request.args.get('limit', 300, type=int)

    # Ruta del archivo donde se generará el grafo
    graph_file = os.path.join(STORAGE_FOLDER, "admin_graph.html")

    # Generar el grafo con PyVis
    community_data_instance.generate_pyvis_graph(graph_file, max_nodes=limit)

    return render_template("admin_graph.html", graph_file=f"storage/admin_graph.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    # user y password del admin
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "admin"

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Validar si es el usuario administrador
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['user_id'] = "admin"
            session['is_admin'] = True 
            session.permanent = True
            return redirect(url_for('admin_dashboard'))

        query = text("""
            SELECT UserID, password 
            FROM social_media_users 
            WHERE username = :username
        """)

        with engine.connect() as connection:
            result = connection.execute(query, {"username": username}).fetchone()

            if result:
                user_id, stored_password = result
                if stored_password == password:
                    session['user_id'] = int(user_id)
                    session['is_admin'] = False
                    session.permanent = True
                    return redirect(url_for('profile', user_id=user_id))
                else:
                    return render_template('login.html', error="Contraseña incorrecta. Intente nuevamente.")
            else:
                return render_template('login.html', error="Usuario no encontrado. Intente nuevamente.")
    
    return render_template('login.html')

@app.route('/profile/<int:user_id>')
def profile(user_id):
    current_user_id = session.get('user_id')
    is_own_profile = (current_user_id == user_id)

    # Obtener datos del perfil
    user_data, same_interest_users = community_data_instance.get_user_profile(user_id)
    post_count = community_data_instance.get_post_count(user_id)
    follower_count = community_data_instance.get_follower_count(user_id)
    following_count = community_data_instance.get_following_count(user_id)

    # obtener el interés principal del usuario actual
    user_interest = user_data['interest'] if user_data else None

    # Filtro de genero con interes
    gender_filter = request.args.get('gender')
    if gender_filter and user_interest:
        same_interest_users = community_data_instance.get_users_by_gender_and_interest(
            gender_filter, user_interest, current_user_id
        )

    # recomendaciones de usuarios (solo para el perfil propio)
    recommended_users = community_data_instance.get_user_recommendations(user_id) if is_own_profile else []

    # Verificar si el usuario autenticado sigue al perfil visitado
    is_following = community_data_instance.is_following(current_user_id, user_id) if current_user_id else False

    # Obtener seguidores y seguidos del perfil visitado
    followers = community_data_instance.get_followers(user_id, current_user_id)
    following = community_data_instance.get_following(user_id, current_user_id)

    for similar_user in same_interest_users:
        similar_user['is_following'] = community_data_instance.is_following(
            current_user_id, similar_user['user_id']
        ) if current_user_id else False

    query = text("""
        SELECT PostID, Content, PostDate, Image
        FROM posts
        WHERE UserID = :user_id
        ORDER BY PostDate DESC
    """)
    with engine.connect() as connection:
        user_posts = connection.execute(query, {"user_id": user_id}).fetchall()

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

@app.route('/get_second_interest/<int:user_id>', methods=['GET'])
def get_second_interest_endpoint(user_id):
    """
    Endpoint para obtener el segundo interés de un usuario dado su ID.
    """
    # Usar la instancia de CommunityData para obtener el segundo interés
    second_interest = community_data_instance.get_second_interest(user_id)
    
    if second_interest:
        return jsonify({"success": True, "second_interest": second_interest})
    
    return jsonify({"success": False, "message": "No se encontró un segundo interés para este usuario."}), 404


## Ruta para el registro de nuevos usuarios
@app.route('/filter_users', methods=['GET'])
def filter_users():
    gender = request.args.get('gender')
    country = request.args.get('country')
    profile_user_id = request.args.get('profile_user_id', type=int)
    current_user_id = session.get('user_id')

    user_data, _ = community_data_instance.get_user_profile(profile_user_id)
    user_interest = user_data['interest'] if user_data else None

    filtered_users = [
        user for user in community_data_instance.user_groups.values()
        if (not gender or user["gender"] == gender)
        and (not country or user.get("country") == country)
        and (not user_interest or user["interest"] == user_interest) 
        and user["user_id"] != profile_user_id 
    ]

    for user in filtered_users:
        user["is_following"] = community_data_instance.is_following(current_user_id, user["user_id"])

    return jsonify({"filtered_users": filtered_users})

@app.route('/get_filter_counts_for_profile/<int:profile_user_id>', methods=['GET'])
def get_filter_counts_for_profile(profile_user_id):
    filter_counts = community_data_instance.get_filter_counts_for_profile(profile_user_id)
    return jsonify(filter_counts)



@app.route('/get_countries', methods=['GET'])
def get_countries():
    countries = community_data_instance.get_unique_countries()
    return jsonify({"countries": countries})
 
@app.route('/create_post', methods=['GET', 'POST'])
def create_post():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        content = request.form.get('content')
        image = request.files.get('image')
        user_id = session['user_id']
        
        image_path = None
        if image:
            filename = f"{user_id}_{int(datetime.timestamp(datetime.now()))}_{image.filename}"
            image_path = os.path.join(STORAGE_FOLDER, filename)
            try:
                image.save(image_path)
                image_path = f"/storage/{filename}"
            except Exception as e:
                user_data, _ = community_data_instance.get_user_profile(user_id)
                return render_template('post_form.html', error="Error al guardar la imagen. Intente nuevamente.", user=user_data)

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
        
        return redirect(url_for('index'))
    
    user_data, _ = community_data_instance.get_user_profile(session['user_id'])
    return render_template('post_form.html', user=user_data)


@app.route('/delete_post/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    query = text("""
        SELECT Image, UserID
        FROM posts
        WHERE PostID = :post_id
    """)
    
    with engine.connect() as connection:
        post = connection.execute(query, {"post_id": post_id}).fetchone()
        
        if not post:
            return redirect(url_for('profile', user_id=user_id))
        
        post_image_path, post_user_id = post
        
        if post_user_id != user_id:
            return redirect(url_for('profile', user_id=user_id))

        if post_image_path and os.path.exists(post_image_path):
            os.remove(post_image_path)

    delete_query = text("DELETE FROM posts WHERE PostID = :post_id")
    with SessionLocal() as db_session:
        db_session.execute(delete_query, {"post_id": post_id})
        db_session.commit()
    
    return redirect(url_for('profile', user_id=user_id))


@app.route('/followers/<int:user_id>')
def followers(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    current_user_id = session['user_id']
    followers_list = community_data_instance.get_followers(user_id, current_user_id)
    user_data, _ = community_data_instance.get_user_profile(user_id)

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



@app.route('/following/<int:user_id>')
def following(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    current_user_id = session['user_id']
    following_list = community_data_instance.get_following(user_id, current_user_id)
    user_data, _ = community_data_instance.get_user_profile(user_id)
    is_own_profile = (current_user_id == user_id)

    return render_template('following.html', following=following_list, user=user_data, is_own_profile=is_own_profile)



@app.route('/follow/<int:user_id>', methods=['POST'])
def follow(user_id):
    if 'user_id' not in session:
        return jsonify(success=False, error="Usuario no autenticado.")

    follower_id = session['user_id']

    if follower_id == user_id:
        return jsonify(success=False, error="No puedes seguirte a ti mismo.")

    success = community_data_instance.follow_user(follower_id, user_id)

    if success:
        return jsonify(
            success=True,
            is_profile_visited=(follower_id != user_id),
            is_logged_in_user=(follower_id == session['user_id'])
        )
    else:
        return jsonify(success=False, error="No se pudo seguir al usuario.")

@app.route('/unfollow/<int:user_id>', methods=['POST'])
def unfollow(user_id):
    if 'user_id' not in session:
        return jsonify(success=False, error="Usuario no autenticado.")

    follower_id = session['user_id']

    if follower_id == user_id:
        return jsonify(success=False, error="No puedes dejar de seguirte a ti mismo.")

    success = community_data_instance.unfollow_user(follower_id, user_id)

    if success:
        return jsonify(
            success=True,
            is_profile_visited=(follower_id != user_id),
            is_logged_in_user=(follower_id == session['user_id'])
        )
    else:
        return jsonify(success=False, error="No se pudo dejar de seguir al usuario.")

    
@app.route('/get_comments/<int:post_id>', methods=['GET'])
def get_comments(post_id):
    comments = community_data_instance.get_comments_for_post(post_id)
    return jsonify(comments)

@app.route('/like_post/<int:post_id>', methods=['POST'])
def like_post(post_id):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    user_id = session['user_id']
    community_data_instance.like_post(post_id, user_id)
    like_count = community_data_instance.get_like_count(post_id)
    return jsonify({"success": True, "like_count": like_count})

@app.route('/unlike_post/<int:post_id>', methods=['POST'])
def unlike_post(post_id):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    user_id = session['user_id']
    community_data_instance.unlike_post(post_id, user_id)
    like_count = community_data_instance.get_like_count(post_id)
    return jsonify({"success": True, "like_count": like_count})


@app.route('/add_comment/<int:post_id>', methods=['POST'])
def add_comment(post_id):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    content = request.form.get('comment_content')
    user_id = session['user_id']

    if content:
        community_data_instance.add_comment(post_id, user_id, content)
        return jsonify({"success": True})
    
    return jsonify({"error": "No content provided"}), 400

@app.route('/send_message', methods=['POST'])
def send_message():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    sender_id = session['user_id']
    receiver_id = request.form.get('receiver_id')
    content = request.form.get('content')
    image_file = request.files.get('image')

    query = text("SELECT profile_image FROM social_media_users WHERE UserID = :sender_id")
    with engine.connect() as connection:
        result = connection.execute(query, {"sender_id": sender_id}).fetchone()
        profile_image = result.profile_image if result else None

    image_path = None
    if image_file:
        filename = f"{sender_id}_{int(datetime.timestamp(datetime.now()))}_{uuid.uuid4().hex}.png"
        image_path = os.path.join(STORAGE_FOLDER, filename)
        image_file.save(image_path)
        image_path = f"/storage/{filename}"

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




@socketio.on('join')
def on_join(data):
    user_id = data['user_id']
    selected_user_id = data.get('selected_user_id')
    if selected_user_id:
        room = f'chat_{min(user_id, selected_user_id)}_{max(user_id, selected_user_id)}'
        join_room(room)

@app.route('/get_messages/<int:user_id>', methods=['GET'])
def get_messages(user_id):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    current_user_id = session['user_id']

    if not (community_data_instance.is_following(current_user_id, user_id) and community_data_instance.is_following(user_id, current_user_id)):
        return jsonify({"error": "You need to follow each other to chat"}), 403

    query = text("""
        SELECT sender_id, receiver_id, content, sent_at
        FROM messages
        WHERE (sender_id = :current_user_id AND receiver_id = :user_id) 
           OR (sender_id = :user_id AND receiver_id = :current_user_id)
        ORDER BY sent_at ASC
    """)
    with engine.connect() as connection:
        messages = connection.execute(query, {"current_user_id": current_user_id, "user_id": user_id}).fetchall()
        messages_data = [
            {"sender_id": msg.sender_id, "receiver_id": msg.receiver_id, "content": msg.content, "sent_at": msg.sent_at.isoformat()}
            for msg in messages
        ]
    
    return jsonify(messages_data)

@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id:
        query = text("SELECT UserID, username, profile_image FROM social_media_users WHERE UserID = :user_id")
        with engine.connect() as connection:
            user = connection.execute(query, {"user_id": user_id}).fetchone()
            if user:
                g.user = {
                    "user_id": user.UserID,
                    "username": user.username,
                    "profile_image": user.profile_image
                }
    else:
        g.user = None

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    current_user_id = session['user_id']
    mutual_followers = community_data_instance.get_mutual_followers(current_user_id)

    selected_user_id = request.args.get('user_id', type=int)
    messages = []

    if selected_user_id:
        messages = community_data_instance.get_messages_between_users(current_user_id, selected_user_id)

    return render_template('chat.html', mutual_followers=mutual_followers, messages=messages, selected_user_id=selected_user_id)

@app.route('/search', methods=['GET'])
def search():
    term = request.args.get('term', '').strip()
    current_user_id = session.get('user_id')
    results = []

    if term:
        results = [
            {
                "user_id": user["user_id"],
                "name": user["name"],
                "interest": user["interest"],
                "profile_image": user["profile_image"],
            }
            for user in community_data_instance.user_groups.values()
            if term.lower() in user["interest"].lower() and user["user_id"] != current_user_id
        ]
    
    return render_template('search.html', term=term, results=results)

@app.route('/home')
def index():
    user_id = session.get('user_id')
    user_data, _ = community_data_instance.get_user_profile(user_id) if user_id else (None, None)

    query = text("""
        SELECT p.PostID, p.Content, p.PostDate, p.Image, u.Name, u.profile_image, u.UserID, u.Interests
        FROM posts p
        JOIN social_media_users u ON p.UserID = u.UserID
        ORDER BY p.PostDate DESC
    """)
    with engine.connect() as connection:
        posts_raw = connection.execute(query).fetchall()

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

    return render_template('home.html', posts=posts, user=user_data)


@app.route('/storage/<path:filename>')
def serve_image(filename):
    return send_from_directory(STORAGE_FOLDER, filename)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)