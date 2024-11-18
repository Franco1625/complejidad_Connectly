import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt

df = pd.read_csv('data/SocialMediaUsersDataset.csv').head(1500)

G = nx.DiGraph()

interest_groups = {}

# Agregar nodos al grafo y agrupar por interés
for i, user in df.iterrows():
    primary_interest = user['Interests'].split(', ')[0]
    user_id = user['UserID']
    
    G.add_node(user_id, name=user['Name'], interest=primary_interest)
    
    if primary_interest not in interest_groups:
        interest_groups[primary_interest] = []
    interest_groups[primary_interest].append(user_id)

for interest, users in interest_groups.items():
    for i in range(len(users)):
        for j in range(i + 1, len(users)):
            G.add_edge(users[i], users[j])
            G.add_edge(users[j], users[i])

# Implementación del algoritmo de Kosaraju

# Paso 1: Realizar DFS y almacenar el orden de finalización en un stack
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
        transposed.add_edge(v, u)  # Invertir la dirección de las aristas
    return transposed

# Paso 3: Realizar DFS en el grafo transpuesto para encontrar componentes
def kosaraju_dfs_transposed(graph, node, visited, component):
    visited[node] = True
    component.append(node)
    for neighbor in graph.neighbors(node):
        if not visited[neighbor]:
            kosaraju_dfs_transposed(graph, neighbor, visited, component)

# Aplicar el algoritmo de Kosaraju
def kosaraju_algorithm(graph):
    stack = []
    visited = {node: False for node in graph.nodes}

    # Paso 1: Llenar el stack con el orden de finalización
    for node in graph.nodes:
        if not visited[node]:
            kosaraju_dfs(graph, node, visited, stack)

    # Paso 2: Transponer el grafo
    transposed_graph = transpose_graph(graph)

    # Paso 3: Obtener componentes fuertemente conectados
    visited = {node: False for node in graph.nodes}
    strongly_connected_components = []

    while stack:
        node = stack.pop()
        if not visited[node]:
            component = []
            kosaraju_dfs_transposed(transposed_graph, node, visited, component)
            strongly_connected_components.append(component)

    return strongly_connected_components

# Ejecutar el algoritmo de Kosaraju y mostrar los componentes fuertemente conectados
scc = kosaraju_algorithm(G)

# Mostrar los componentes fuertemente conectados
print("\nComponentes fuertemente conectados basados en el interés primario:")
for i, component in enumerate(scc, start=1):
    print(f"\nComponente {i}:")
    for user_id in component:
        print(f"- {G.nodes[user_id]['name']}")

plt.figure(figsize=(15, 10))
pos = nx.spring_layout(G, k=0.5)

nx.draw(G, pos, with_labels=False, node_size=600, node_color="skyblue", edge_color="gray")

labels = {node: G.nodes[node]['name'] for node in G.nodes()}
nx.draw_networkx_labels(G, pos, labels=labels, font_size=8, font_weight="bold", verticalalignment="bottom")

plt.title("Grafo de Comunidad de Usuarios")
plt.show()
