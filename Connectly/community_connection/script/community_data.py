import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import networkx as nx

class CommunityData:
    def __init__(self, db_url):
        self.engine = create_engine(db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.user_groups = self._load_user_groups(limit=1500)

    def _load_user_groups(self, limit=1500):
        df = pd.read_sql(f'SELECT UserID, Name, Interests, profile_image FROM social_media_users LIMIT {limit}', con=self.engine)

        G = nx.Graph()
        interest_groups = {}

        for _, user in df.iterrows():
            primary_interest = user['Interests'].split(', ')[0]
            user_id = user['UserID']

            G.add_node(user_id, name=user['Name'], interest=primary_interest, profile_image=user['profile_image'])

            if primary_interest not in interest_groups:
                interest_groups[primary_interest] = []
            interest_groups[primary_interest].append(user_id)

        user_groups = {
            user_id: {
                "user_id": user_id,
                "name": G.nodes[user_id]['name'],
                "interest": G.nodes[user_id]['interest'],
                "profile_image": G.nodes[user_id]['profile_image'],
                "similar_users": [
                    {"user_id": similar_user, "name": G.nodes[similar_user]['name'], "profile_image": G.nodes[similar_user]['profile_image']}
                    for similar_user in interest_groups[G.nodes[user_id]['interest']]
                    if similar_user != user_id
                ]
            }
            for user_id in G.nodes
        }

        self.interest_groups = interest_groups
        return user_groups

    def get_user_profile(self, user_id):
        if user_id in self.user_groups:
            user_data = self.user_groups[user_id]
            similar_users = user_data["similar_users"]
            return user_data, similar_users

        return None, []

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

    def is_following(self, follower_id, followed_id):
        query = text("""
            SELECT 1 FROM user_follows
            WHERE follower_id = :follower_id AND followed_id = :followed_id
        """)
        with self.engine.connect() as connection:
            result = connection.execute(query, {"follower_id": follower_id, "followed_id": followed_id}).fetchone()
        return result is not None
    
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
    


    def get_post_count(self, user_id):
        query = text("SELECT COUNT(*) FROM posts WHERE UserID = :user_id")
        with self.engine.connect() as connection:
            result = connection.execute(query, {"user_id": user_id}).scalar()
        return result

    def get_follower_count(self, user_id):
        query = text("SELECT COUNT(*) FROM user_follows WHERE followed_id = :user_id")
        with self.engine.connect() as connection:
            result = connection.execute(query, {"user_id": user_id}).scalar()
        return result

    def get_following_count(self, user_id):
        query = text("SELECT COUNT(*) FROM user_follows WHERE follower_id = :user_id")
        with self.engine.connect() as connection:
            result = connection.execute(query, {"user_id": user_id}).scalar()
        return result
    
    def get_followers(self, user_id):
        query = text("""
            SELECT u.UserID, u.Name, u.profile_image
            FROM social_media_users u
            JOIN user_follows f ON u.UserID = f.follower_id
            WHERE f.followed_id = :user_id
        """)
        with self.engine.connect() as connection:
            result = connection.execute(query, {"user_id": user_id})
            return [row for row in result]


    def get_following(self, user_id):
        query = text("""
            SELECT u.UserID, u.Name, u.profile_image
            FROM social_media_users u
            JOIN user_follows f ON u.UserID = f.followed_id
            WHERE f.follower_id = :user_id
        """)
        with self.engine.connect() as connection:
            return connection.execute(query, {"user_id": user_id}).fetchall()
        
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
            SELECT c.CommentID, c.Content, c.CommentDate, u.Name, u.profile_image
            FROM comments c
            JOIN social_media_users u ON c.UserID = u.UserID
            WHERE c.PostID = :post_id
            ORDER BY c.CommentDate ASC
        """)
        with self.engine.connect() as connection:
            result = connection.execute(query, {"post_id": post_id}).fetchall()
            return [{"CommentID": row.CommentID, "Content": row.Content, "CommentDate": row.CommentDate, "Name": row.Name, "profile_image": row.profile_image} for row in result]