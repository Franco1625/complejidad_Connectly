import pandas as pd
from sqlalchemy import create_engine

## Cargar el dataset
df = pd.read_csv('data/SocialMediaUsersDataset.csv').head(1500) 

## Conexión a la base de datos
db_url = 'mysql+mysqlconnector://root:password@localhost:3306/connectly' 
engine = create_engine(db_url)

## Insertar el dataset en la base de datos
columns_to_store = ['UserID', 'Name', 'Gender', 'DOB', 'Interests', 'City', 'Country']

df[columns_to_store].to_sql('social_media_users', con=engine, if_exists='replace', index=False)

## Mensaje de confirmación
print("El dataset ha sido insertado correctamente en la base de datos MySQL.")