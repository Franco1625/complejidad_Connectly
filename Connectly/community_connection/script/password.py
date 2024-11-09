import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import random

db_url = 'mysql+mysqlconnector://root:root@localhost:3306/prueba2'
engine = create_engine(db_url)
Session = sessionmaker(bind=engine)

df = pd.read_sql('SELECT * FROM social_media_users LIMIT 1500', con=engine)

def generate_username(name, user_id):
    first_name = name.split()[0]  
    return f"{first_name}{user_id}"  

def generate_random_profile_image(gender, user_id):
    image_id = user_id % 99 + 1 
    gender_path = 'men' if gender.lower() == 'male' else 'women'
    return f"https://randomuser.me/api/portraits/{gender_path}/{image_id}.jpg"

df['username'] = df.apply(lambda row: generate_username(row['Name'], row['UserID']), axis=1)
df['password'] = df['username']
df['profile_image'] = df.apply(lambda row: generate_random_profile_image(row['Gender'], row['UserID']), axis=1)

batch_size = 100
total_records = len(df)
for start in range(0, total_records, batch_size):
    session = Session()
    
    batch_df = df.iloc[start:start + batch_size]

    for index, row in batch_df.iterrows():
        query = text("""
            UPDATE social_media_users
            SET username = :username, password = :password, profile_image = :profile_image
            WHERE UserID = :user_id
        """)
        session.execute(query, {
            "username": row['username'],
            "password": row['password'],
            "profile_image": row['profile_image'],
            "user_id": int(row['UserID'])
        })
    
    session.commit()
    session.close()
    
    print(f"Bloque {start // batch_size + 1} de registros procesado")

print("Usernames, contraseñas e imágenes de perfil generados y actualizados exitosamente para los primeros 1500 usuarios.")
