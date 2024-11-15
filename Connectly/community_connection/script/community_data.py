## Description: This script contains the class CommunityData that is used to interact with the database and retrieve data for the community connection feature.
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import networkx as nx
import matplotlib.pyplot as plt
import os




## Clase CommunityData
class CommunityData:
    def __init__(self, db_url):
        self.engine = create_engine(db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.user_groups = self._load_user_groups(limit=1500)
 

## Cargar los grupos de usuarios
    def _load_user_groups(self, limit=1500):
         df = pd.read_sql(
             f'SELECT UserID, Name, Interests, Gender, Country, profile_image FROM social_media_users LIMIT {limit}',
             con=self.engine
         )

         # Crear el grafo dirigido
         G = nx.DiGraph()
         interest_groups = {}

         # Agregar nodos al grafo y agrupar por intereses
         for _, user in df.iterrows():
             primary_interest = user['Interests'].split(', ')[0].strip("'\"")
             user_id = user['UserID']

             G.add_node(user_id,
                        name=user['Name'],
                        interest=primary_interest,
                        gender=user['Gender'],
                        country=user['Country'],
                        profile_image=user['profile_image'])

             if primary_interest not in interest_groups:
                 interest_groups[primary_interest] = []
             interest_groups[primary_interest].append(user_id)

         # Conectar usuarios con el mismo interés
         for interest, users in interest_groups.items():
             for i in range(len(users)):
                 for j in range(i + 1, len(users)):
                     # Agregar conexiones bidireccionales
                     G.add_edge(users[i], users[j])
                     G.add_edge(users[j], users[i])

         # Implementación del algoritmo de Kosaraju

         # Paso 1: DFS para obtener el orden de finalización
         def kosaraju_dfs(graph, node, visited, stack):
             visited[node] = True
             for neighbor in graph.neighbors(node):
                 if not visited[neighbor]:
                     kosaraju_dfs(graph, neighbor, visited, stack)
             stack.append(node)

         # Paso 2: Transponer el grafo
         def transpose_graph(graph):
             transposed = nx.DiGraph()
             for node in graph.nodes:
                 transposed.add_node(node)
             for u, v in graph.edges:
                 transposed.add_edge(v, u)  # Invertir dirección de las aristas
             return transposed

         # Paso 3: DFS en el grafo transpuesto
         def kosaraju_dfs_transposed(graph, node, visited, component):
             visited[node] = True
             component.append(node)
             for neighbor in graph.neighbors(node):
                 if not visited[neighbor]:
                     kosaraju_dfs_transposed(graph, neighbor, visited, component)

         # Algoritmo principal de Kosaraju
         def kosaraju_algorithm(graph):
             stack = []
             visited = {node: False for node in graph.nodes}

             # Paso 1: DFS en el grafo original para llenar el stack
             for node in graph.nodes:
                 if not visited[node]:
                     kosaraju_dfs(graph, node, visited, stack)

             # Paso 2: Transponer el grafo
             transposed_graph = transpose_graph(graph)

             # Paso 3: Encontrar componentes fuertemente conectados
             visited = {node: False for node in graph.nodes}
             strongly_connected_components = []

             while stack:
                 node = stack.pop()
                 if not visited[node]:
                     component = []
                     kosaraju_dfs_transposed(transposed_graph, node, visited, component)
                     strongly_connected_components.append(component)

             return strongly_connected_components

         # Ejecutar el algoritmo de Kosaraju
         scc = kosaraju_algorithm(G)

         # Crear la estructura de salida
         user_groups = {
             user_id: {
                 "user_id": user_id,
                 "name": G.nodes[user_id]['name'],
                 "interest": G.nodes[user_id]['interest'],
                 "gender": G.nodes[user_id]['gender'],
                 "country": G.nodes[user_id]['country'],
                 "profile_image": G.nodes[user_id]['profile_image'],
                 "similar_users": [
                     {
                         "user_id": similar_user,
                         "name": G.nodes[similar_user]['name'],
                         "profile_image": G.nodes[similar_user]['profile_image']
                     }
                     for component in scc if user_id in component
                     for similar_user in component if similar_user != user_id
                 ]
             }
             for user_id in G.nodes
         }

         self.interest_groups = interest_groups
         return user_groups


## Obtener los conteos de filtros para un perfil de usuario
    def get_filter_counts_for_profile(self, profile_user_id):
        profile_data = self.user_groups.get(profile_user_id)
    
        if not profile_data:
            return {
                "gender_counts": {},
                "country_counts": {}
            }
    
        user_interest = profile_data["interest"]
    
        related_users = [
            user for user in self.user_groups.values()
            if user["interest"] == user_interest and user["user_id"] != profile_user_id
        ]
    
        gender_counts = {}
        country_counts = {}
    
        for user in related_users:
            gender = user.get("gender")
            if gender:
                gender_counts[gender] = gender_counts.get(gender, 0) + 1
    
            country = user.get("country")
            if country:
                country_counts[country] = country_counts.get(country, 0) + 1
    
        return {
            "gender_counts": gender_counts,
            "country_counts": country_counts
        }
    
## Obtener los países únicos
    def get_unique_countries(self):
        countries = {user_data["country"] for user_data in self.user_groups.values() if user_data.get("country")}
        return sorted(countries)

## Obtener los géneros únicos
    def get_users_by_gender_and_interest(self, gender, current_interest, current_user_id):
        filtered_users = [
            {
                "user_id": user_data["user_id"],
                "name": user_data["name"],
                "interest": user_data["interest"],
                "profile_image": user_data["profile_image"],
            }
            for user_id, user_data in self.user_groups.items()
            if user_data["gender"] == gender
            and user_data["interest"] == current_interest
            and user_id != current_user_id
        ]
        return filtered_users
    
## Obtener los usuarios por país
    def get_users_by_country(self, country, current_user_id):
        filtered_users = [
            {
                "user_id": user_data["user_id"],
                "name": user_data["name"],
                "interest": user_data["interest"],
                "profile_image": user_data["profile_image"],
            }
            for user_id, user_data in self.user_groups.items()
            if user_data.get("country") == country
            and user_id != current_user_id 
        ]
        return filtered_users

## Obtener el perfil de un usuario
    def get_user_profile(self, user_id):
        if user_id in self.user_groups:
            user_data = self.user_groups[user_id]
            similar_users = user_data["similar_users"]
            return user_data, similar_users

        return None, []

## Obtener los usuarios similares
    def follow_user(self, follower_id, followed_id):
        if follower_id == followed_id:
            return False

        follow_query = text("""
            INSERT IGNORE INTO user_follows (follower_id, followed_id)
            VALUES (:follower_id, :followed_id)
        """)

        with self.SessionLocal() as session:
            session.execute(follow_query, {"follower_id": follower_id, "followed_id": followed_id})
            session.commit()
        
        return True
## Verificar si un usuario sigue a otro
    def is_following(self, follower_id, followed_id):
        query = text("""
            SELECT 1 FROM user_follows
            WHERE follower_id = :follower_id AND followed_id = :followed_id
        """)
        with self.engine.connect() as connection:
            result = connection.execute(query, {"follower_id": follower_id, "followed_id": followed_id}).fetchone()
        return result is not None
## Obtener las recomendaciones de usuarios para un usuario    
    def get_user_recommendations(self, user_id):
        query_recommendations = text("""
            SELECT DISTINCT uf2.follower_id AS recommended_user
            FROM user_follows AS uf1
            JOIN user_follows AS uf2 ON uf1.followed_id = uf2.followed_id
            WHERE uf1.follower_id = :user_id
              AND uf2.follower_id != :user_id
              AND uf2.follower_id NOT IN (
                SELECT followed_id 
                FROM user_follows 
                WHERE follower_id = :user_id
              )
        """)

        recommendations = []

        with self.SessionLocal() as session:
            recommended_users_raw = session.execute(query_recommendations, {"user_id": user_id}).fetchall()

            for rec_user in recommended_users_raw:
                recommended_user_id = rec_user[0]
                user_data_query = text("""
                    SELECT UserID, Name, profile_image
                    FROM social_media_users
                    WHERE UserID = :user_id
                """)
                user_data = session.execute(user_data_query, {"user_id": recommended_user_id}).fetchone()

                if user_data:
                    is_following_back = self.is_following(recommended_user_id, user_id)
                    recommendations.append({
                        "user_id": user_data.UserID,
                        "name": user_data.Name,
                        "profile_image": user_data.profile_image,
                        "is_following": False,
                        "is_following_back": is_following_back
                    })

        return recommendations
## Dejar de seguir a un usuario    
    def unfollow_user(self, follower_id, followed_id):
        if follower_id == followed_id:
            return False
    
        unfollow_query = text("""
            DELETE FROM user_follows
            WHERE follower_id = :follower_id AND followed_id = :followed_id
        """)
    
        with self.SessionLocal() as session:
            session.execute(unfollow_query, {"follower_id": follower_id, "followed_id": followed_id})
            session.commit()
        
        return True
    
## Obtener los posts de un usuario
    def get_post_count(self, user_id):
        query = text("SELECT COUNT(*) FROM posts WHERE UserID = :user_id")
        with self.engine.connect() as connection:
            result = connection.execute(query, {"user_id": user_id}).scalar()
        return result
## Obtener los seguidores de un usuario
    def get_follower_count(self, user_id):
        query = text("SELECT COUNT(*) FROM user_follows WHERE followed_id = :user_id")
        with self.engine.connect() as connection:
            result = connection.execute(query, {"user_id": user_id}).scalar()
        return result
## Obtener los seguidos de un usuario
    def get_following_count(self, user_id):
        query = text("SELECT COUNT(*) FROM user_follows WHERE follower_id = :user_id")
        with self.engine.connect() as connection:
            result = connection.execute(query, {"user_id": user_id}).scalar()
        return result
## Obtener los posts de un usuario    
    def get_followers(self, user_id, current_user_id):
        query = text("""
            SELECT u.UserID, u.Name, u.profile_image
            FROM social_media_users u
            JOIN user_follows f ON u.UserID = f.follower_id
            WHERE f.followed_id = :user_id
        """)
        with self.engine.connect() as connection:
            result = connection.execute(query, {"user_id": user_id})
            return [
                {
                    "user_id": row.UserID,
                    "name": row.Name,
                    "profile_image": row.profile_image,
                    "is_following": self.is_following(current_user_id, row.UserID) if current_user_id else False
                }
                for row in result
            ]
## Obtener los seguidos de un usuario
    def get_mutual_followers(self, user_id):
        query = text("""
            SELECT u.UserID, u.Name, u.profile_image, u.Interests
            FROM social_media_users u
            JOIN user_follows f1 ON f1.follower_id = :user_id AND f1.followed_id = u.UserID
            JOIN user_follows f2 ON f2.follower_id = u.UserID AND f2.followed_id = :user_id
        """)
        with self.engine.connect() as connection:
            result = connection.execute(query, {"user_id": user_id}).fetchall()
        return [
            {
                "user_id": row.UserID,
                "name": row.Name,
                "profile_image": row.profile_image,
                "interest": row.Interests.split(', ')[0].strip("'\"") if row.Interests else None  # Primer interés
            }
            for row in result
        ]

## Obtener los posts de un usuario
    def get_messages_between_users(self, user_id_1, user_id_2):
        query = text("""
            SELECT m.sender_id, m.receiver_id, m.content, m.image, m.sent_at, u.profile_image
            FROM messages m
            JOIN social_media_users u ON m.sender_id = u.UserID
            WHERE (m.sender_id = :user_id_1 AND m.receiver_id = :user_id_2) 
               OR (m.sender_id = :user_id_2 AND m.receiver_id = :user_id_1)
            ORDER BY m.sent_at ASC
        """)
        with self.engine.connect() as connection:
            result = connection.execute(query, {"user_id_1": user_id_1, "user_id_2": user_id_2}).fetchall()
        return [
            {
                "sender_id": row.sender_id,
                "receiver_id": row.receiver_id,
                "content": row.content,
                "image": row.image,
                "sent_at": row.sent_at,
                "profile_image": row.profile_image
            }
            for row in result
        ]

## Enviar un mensaje     
    def get_following(self, user_id, current_user_id):
        query = text("""
            SELECT u.UserID, u.Name, u.profile_image
            FROM social_media_users u
            JOIN user_follows f ON u.UserID = f.followed_id
            WHERE f.follower_id = :user_id
        """)
        with self.engine.connect() as connection:
            result = connection.execute(query, {"user_id": user_id})
            return [
                {
                    "user_id": row.UserID,
                    "name": row.Name,
                    "profile_image": row.profile_image,
                    "is_following": self.is_following(current_user_id, row.UserID) if current_user_id else False
                }
                for row in result
            ]
               
## Enviar un mensaje     
    def add_comment(self, post_id, user_id, content):
        query = text("""
            INSERT INTO comments (PostID, UserID, Content, CommentDate)
            VALUES (:post_id, :user_id, :content, NOW())
        """)
        with self.SessionLocal() as session:
            session.execute(query, {"post_id": post_id, "user_id": user_id, "content": content})
            session.commit()

    def get_comments_for_post(self, post_id):
        query = text("""
            SELECT c.CommentID, c.Content, c.CommentDate, u.Name, u.profile_image, u.UserID, u.Interests
            FROM comments c
            JOIN social_media_users u ON c.UserID = u.UserID
            WHERE c.PostID = :post_id
            ORDER BY c.CommentDate ASC
        """)
        with self.engine.connect() as connection:
            result = connection.execute(query, {"post_id": post_id}).fetchall()
            return [
                {
                    "CommentID": row.CommentID,
                    "UserID": row.UserID, 
                    "Content": row.Content,
                    "CommentDate": row.CommentDate,
                    "Name": row.Name,
                    "profile_image": row.profile_image,
                    "interest": row.Interests.split(', ')[0].strip("'\"") if row.Interests else None
                }
                for row in result
            ]


    def like_post(self, post_id: int, user_id: int):
        query = text("""
            INSERT IGNORE INTO post_likes (PostID, UserID)
            VALUES (:post_id, :user_id)
        """)
        with self.SessionLocal() as session:
            session.execute(query, {"post_id": post_id, "user_id": user_id})
            session.commit()
    
    def unlike_post(self, post_id: int, user_id: int):
        query = text("""
            DELETE FROM post_likes
            WHERE PostID = :post_id AND UserID = :user_id
        """)
        with self.SessionLocal() as session:
            session.execute(query, {"post_id": post_id, "user_id": user_id})
            session.commit()
    
    def is_post_liked(self, post_id: int, user_id: int):
        query = text("""
            SELECT 1 FROM post_likes
            WHERE PostID = :post_id AND UserID = :user_id
        """)
        with self.engine.connect() as connection:
            result = connection.execute(query, {"post_id": post_id, "user_id": user_id}).fetchone()
        return result is not None
    
    def get_like_count(self, post_id: int):
        query = text("SELECT COUNT(*) FROM post_likes WHERE PostID = :post_id")
        with self.engine.connect() as connection:
            result = connection.execute(query, {"post_id": post_id}).scalar()
        return result
    