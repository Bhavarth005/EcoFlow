import geopandas as gpd
import lightgbm as lgb
import pandas as pd
import numpy as np
import sys
import datetime
import pytz

def prepare_features(gdf, predict_time):
    """
    Prepare features for model prediction.
    Adjust this function to your trained model's feature requirements.
    """
    df = gdf.copy()
    hour = int(predict_time.split(':')[0])
    minute = int(predict_time.split(':')[1])
    df['hour'] = hour
    df['minute'] = minute
    df['road_length'] = df.geometry.length  # Note: project to metric CRS if possible for accuracy
    # Add other feature engineering as needed

    # List your model features here
    feature_cols = ['hour', 'minute', 'road_length']
    return df[feature_cols]

def main():
    ist = pytz.timezone('Asia/Kolkata')

    if len(sys.argv) < 2:
        predict_time = datetime.datetime.now(ist).strftime("%H:%M:%S")
        print(f"No time argument passed, using current IST time: {predict_time}")
    else:
        predict_time = sys.argv[1]

    print(f"Running congestion prediction for time: {predict_time}")

    # Load master GeoPackages
    roads_gdf = gpd.read_file("master_roads.gpkg")
    zones_gdf = gpd.read_file("master_zones.gpkg")

    # Load trained LightGBM model
    model = lgb.Booster(model_file='ahmedabad_lightgbm_40pct_model.txt')

    # Prepare features for roads
    X_roads = prepare_features(roads_gdf, predict_time)

    # Predict congestion values
    pred_roads = model.predict(X_roads)
    roads_gdf['congestion'] = np.clip(pred_roads, 0, 1)

    # Assign roads to zones if not assigned
    if 'zone_id' not in roads_gdf.columns:
        roads_gdf = gpd.sjoin(roads_gdf, zones_gdf[['zone_id', 'geometry']], how='left', predicate='within')

    # Aggregate road congestion to zones (mean)
    zones_congestion = roads_gdf.groupby('zone_id')['congestion'].mean().reset_index()

    zones_gdf = zones_gdf.merge(zones_congestion, on='zone_id', how='left')
    zones_gdf['congestion'] = zones_gdf['congestion'].fillna(0)

    # Save updated congestion GeoPackages
    roads_gdf.to_file("roads_with_congestion.gpkg", driver="GPKG")
    zones_gdf.to_file("zones_with_congestion.gpkg", driver="GPKG")

    print("Congestion prediction complete. Updated files saved.")

if __name__ == "__main__":
    main()
