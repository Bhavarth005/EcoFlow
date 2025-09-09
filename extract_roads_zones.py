import xml.etree.ElementTree as ET
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Polygon, Point
import numpy as np
import os

def parse_osm_roads(osm_file):
    tree = ET.parse(osm_file)
    root = tree.getroot()

    nodes = {node.attrib['id']: (float(node.attrib['lon']), float(node.attrib['lat'])) for node in root.findall('node')}

    roads = []
    for way in root.findall('way'):
        tags = {tag.attrib['k']: tag.attrib['v'] for tag in way.findall('tag')}
        if 'highway' in tags:
            nds = [nd.attrib['ref'] for nd in way.findall('nd')]
            try:
                coords = [nodes[nd] for nd in nds]
                line = LineString(coords)
                roads.append({'id': way.attrib['id'], 'highway': tags['highway'], 'geometry': line})
            except KeyError:
                # skip ways with missing nodes
                continue

    gdf = gpd.GeoDataFrame(roads, geometry='geometry')
    gdf.set_crs(epsg=4326, inplace=True)  # geographic CRS
    return gdf

def assign_zone(point, zones_gdf):
    for zone in zones_gdf.itertuples():
        if zone.geometry.contains(point):
            return zone.zone_id
    return None

def main():
    directory = "./osm files"  # Update this to your OSM files directory
    osm_files = [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith('.osm')]

    road_gdfs = []
    print("Parsing OSM files...")
    for f in osm_files:
        print(f"Parsing {f}...")
        gdf = parse_osm_roads(f)
        print(f"Road segments extracted: {len(gdf)}")
        road_gdfs.append(gdf)

    # Combine all roads
    roads_master = gpd.GeoDataFrame(pd.concat(road_gdfs, ignore_index=True), crs='EPSG:4326')

    # Drop duplicates by id and geometry
    roads_master = roads_master.drop_duplicates(subset=['id'])
    roads_master = roads_master.drop_duplicates(subset=['geometry'])

    print(f"Total master road segments: {len(roads_master)}")

    # Use hardcoded approximate Ahmedabad bounding box for consistent zone coverage
    minx, miny, maxx, maxy = roads_master.total_bounds
    buffer = 0.01  # degrees, adjust as needed
    minx, miny, maxx, maxy = minx - buffer, miny - buffer, maxx + buffer, maxy + buffer

    num_cells_x, num_cells_y = 10, 10
    x_grid = np.linspace(minx, maxx, num_cells_x + 1)
    y_grid = np.linspace(miny, maxy, num_cells_y + 1)

    # Create zones polygons
    zones = []
    for i in range(num_cells_x):
        for j in range(num_cells_y):
            coords = [
                (x_grid[i], y_grid[j]),
                (x_grid[i+1], y_grid[j]),
                (x_grid[i+1], y_grid[j+1]),
                (x_grid[i], y_grid[j+1])
            ]
            zone_poly = Polygon(coords)
            zones.append({'zone_id': f'z{i}_{j}', 'geometry': zone_poly})

    zones_gdf = gpd.GeoDataFrame(zones, geometry='geometry', crs='EPSG:4326')

    # Project to UTM zone 43N (EPSG:32643) for accurate centroid calculations
    roads_proj = roads_master.to_crs(epsg=32643)
    zones_proj = zones_gdf.to_crs(epsg=32643)

    # Compute centroids in projected CRS
    roads_proj['centroid'] = roads_proj.geometry.centroid

    # Assign roads to zones by centroid
    roads_proj['zone_id'] = roads_proj['centroid'].apply(lambda p: assign_zone(p, zones_proj))

    # Drop temporary centroid column
    roads_proj.drop(columns=['centroid'], inplace=True)

    # Project back to geographic CRS for saving and visualization
    roads_master_final = roads_proj.to_crs(epsg=4326)
    zones_final = zones_proj.to_crs(epsg=4326)

    # Save master files
    roads_master_final.to_file('master_roads.gpkg', driver='GPKG')
    zones_final.to_file('master_zones.gpkg', driver='GPKG')

    print("Master GeoPackage files created: master_roads.gpkg and master_zones.gpkg")

if __name__ == "__main__":
    main()
