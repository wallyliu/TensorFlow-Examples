"""
Download a bike network wide enough to draw a word twice as large.

POC 14 left two explanations competing for why nobody can read these routes:
the links between letters, or the size. Three raters reading the same route as
"UT" points at the links; nobody reading the single-stroke version points at
size. The size arm needs a canvas the current one cannot hold - LIT at its
n_min is already 4.5 km wide against a 9 km network - so this widens it.
"""
from heart_route_poc import download_walk_graph
from heart_route_poc3 import SEARCH_LAT, SEARCH_LON

HALF_SIZE_M = 7000.0

if __name__ == "__main__":
    g = download_walk_graph(SEARCH_LAT, SEARCH_LON, HALF_SIZE_M, mode="bike")
    print(f"{g.number_of_nodes():,} nodes, {g.number_of_edges():,} edges")
