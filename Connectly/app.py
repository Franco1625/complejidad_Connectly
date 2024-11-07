import os
from flask import Flask, render_template, redirect, url_for, request, session, send_from_directory
from flask_cors import CORS
from community_connection.script.community_data import CommunityData
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'supersecretkey' 
CORS(app)

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
                    return redirect(url_for('profile', user_id=user_id))
                else:
                    return render_template('login.html', error="Contraseña incorrecta. Intente nuevamente.")
            else:
                return render_template('login.html', error="Usuario no encontrado. Intente nuevamente.")
    
    return render_template('login.html')

@app.route('/profile/<int:user_id>')
def profile(user_id):
    if 'user_id' not in session or session['user_id'] != user_id:
        return redirect(url_for('login'))

    user_data, same_interest_users = community_data_instance.get_user_profile(user_id)

    query = text("""
        SELECT PostID, Content, PostDate, Image
        FROM posts
        WHERE UserID = :user_id
        ORDER BY PostDate DESC
    """)
    
    with engine.connect() as connection:
        user_posts = connection.execute(query, {"user_id": user_id}).fetchall()

    return render_template('profile.html', user=user_data, similar_users=same_interest_users, user_posts=user_posts)


@app.context_processor
def inject_user():
    user_id = session.get('user_id')
    if user_id:
        user_data = community_data_instance.get_user_profile(user_id)[0]
        return {'user': user_data}
    return {'user': None}


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
            print(f"Imagen recibida: {image.filename}") 
            filename = f"{user_id}_{int(datetime.timestamp(datetime.now()))}_{image.filename}"
            image_path = os.path.join(STORAGE_FOLDER, filename)
            try:
                image.save(image_path) 
                print(f"Imagen guardada en: {image_path}") 
                image_path = f"/storage/{filename}"
            except Exception as e:
                print(f"Error al guardar la imagen: {e}")
                return render_template('post_form.html', error="Error al guardar la imagen. Intente nuevamente.")
        else:
            print("No se recibió ninguna imagen.")

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
            print("Publicación creada exitosamente en la base de datos")
        except Exception as e:
            print(f"Error al crear la publicación en la base de datos: {e}")
            return render_template('post_form.html', error="Error al crear la publicación. Intente nuevamente.")

        return redirect(url_for('index'))
    
    return render_template('post_form.html')

@app.route('/home')
def index():
    query = text("""
        SELECT p.PostID, p.Content, p.PostDate, p.Image, u.Name, u.profile_image
        FROM posts p
        JOIN social_media_users u ON p.UserID = u.UserID
        ORDER BY p.PostDate DESC
    """)
    with engine.connect() as connection:
        posts = connection.execute(query).fetchall()
    
    return render_template('home.html', posts=posts)

@app.route('/storage/<path:filename>')
def serve_image(filename):
    return send_from_directory(STORAGE_FOLDER, filename)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
