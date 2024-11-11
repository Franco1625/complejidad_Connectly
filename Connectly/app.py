import os
from flask import Flask, render_template, redirect, url_for, request, session, send_from_directory, jsonify
from flask_cors import CORS
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from community_connection.script.community_data import CommunityData

app = Flask(__name__)
app.secret_key = 'supersecretkey'
CORS(app, supports_credentials=True)

db_url = 'mysql+mysqlconnector://root:root@localhost:3306/prueba2'
community_data_instance = CommunityData(db_url)
engine = create_engine(db_url)
SessionLocal = sessionmaker(bind=engine)

STORAGE_FOLDER = os.path.join(os.path.dirname(__file__), 'storage')
os.makedirs(STORAGE_FOLDER, exist_ok=True)

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
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
                if stored_password == password:
                    session['user_id'] = int(user_id)
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

    # Obtener datos del perfil visitado
    user_data, same_interest_users = community_data_instance.get_user_profile(user_id)
    post_count = community_data_instance.get_post_count(user_id)
    follower_count = community_data_instance.get_follower_count(user_id)
    following_count = community_data_instance.get_following_count(user_id)

    # Recomendaciones de usuarios (solo para el perfil propio)
    recommended_users = community_data_instance.get_user_recommendations(user_id) if is_own_profile else []

    # Verificar si el usuario autenticado sigue al perfil visitado
    is_following = community_data_instance.is_following(current_user_id, user_id) if current_user_id else False

    # Obtener seguidores y seguidos del perfil visitado
    followers = community_data_instance.get_followers(user_id, current_user_id)
    following = community_data_instance.get_following(user_id, current_user_id)

    # Verificar si el usuario autenticado sigue a usuarios con intereses similares
    for similar_user in same_interest_users:
        similar_user['is_following'] = community_data_instance.is_following(current_user_id, similar_user['user_id']) if current_user_id else False

    # Obtener publicaciones del usuario visitado
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
        following=following
    )



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

    # Asegura que cada seguidor tenga el estado 'follows_authenticated_user' y 'is_following'
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

    # Evitar que el usuario se siga a sí mismo
    if follower_id == user_id:
        return jsonify(success=False, error="No puedes seguirte a ti mismo.")

    success = community_data_instance.follow_user(follower_id, user_id)

    if success:
        return jsonify(
            success=True,
            is_profile_visited=(follower_id != user_id),  # True si el usuario está viendo otro perfil
            is_logged_in_user=(follower_id == session['user_id'])  # True si el usuario es el autenticado
        )
    else:
        return jsonify(success=False, error="No se pudo seguir al usuario.")

@app.route('/unfollow/<int:user_id>', methods=['POST'])
def unfollow(user_id):
    if 'user_id' not in session:
        return jsonify(success=False, error="Usuario no autenticado.")

    follower_id = session['user_id']

    # Evitar que el usuario se deje de seguir a sí mismo
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
            "UserID": post[6],  # Incluye el UserID aquí
            "interest": post[7].split(', ')[0].strip(" '\""),  # Solo el primer interés
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
    app.run(debug=True)
