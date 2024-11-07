import pandas as pd
from sqlalchemy import create_engine
import networkx as nx

class CommunityData:
    def __init__(self, db_url):
        self.engine = create_engine(db_url)
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

    def get_communities(self):
        communities_data = {
            interest: [{"user_id": user, "name": self.user_groups[user]["name"], "profile_image": self.user_groups[user]["profile_image"]}
                       for user in users]
            for interest, users in self.interest_groups.items()
        }
        return communities_data

    def get_user_profile(self, user_id):
        if user_id in self.user_groups:
            user_data = self.user_groups[user_id]
            return user_data, user_data["similar_users"]
        return None, []
