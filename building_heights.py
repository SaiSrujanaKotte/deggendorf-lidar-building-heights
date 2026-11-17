import time

import geopandas as gpd
import laspy
import numpy as np
import pandas as pd
import shapely
from scipy import ndimage
from shapely.geometry import box

FILE = "790_5416.laz"
CRS_LIDAR = "EPSG:25832"   # ETRS89 / UTM zone 32N, as stated on the download page
CELL = 1.0                 # ground model resolution in metres
BUILDING_STEP = 2          # use every 2nd building point (plenty for a height)
MIN_POINTS = 20            # ignore footprints with fewer LiDAR points than this
MIN_HEIGHT = 2.0           # ignore results lower than this (sheds, noise)
OSM_SERVERS = [
    "https://overpass-api.de/api",
    "https://overpass.private.coffee/api",
    "https://overpass.kumi.systems/api",
]


def load_lidar(path=FILE):
    las = laspy.read(path)
    cls = np.asarray(las.classification)
    x, y, z = np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)
    ground = np.column_stack([x[cls == 2], y[cls == 2], z[cls == 2]])
    building = np.column_stack([x[cls == 6], y[cls == 6], z[cls == 6]])[::BUILDING_STEP]
    bounds = (x.min(), y.min(), x.max(), y.max())
    return ground, building, bounds


def build_ground_model(ground, bounds, cell=CELL):
    """Mean ground elevation per cell; empty cells take the nearest filled cell."""
    x0, y0, x1, y1 = bounds
    ncols = int(np.ceil((x1 - x0) / cell)) + 1
    nrows = int(np.ceil((y1 - y0) / cell)) + 1
    col = ((ground[:, 0] - x0) / cell).astype(int)
    row = ((ground[:, 1] - y0) / cell).astype(int)
    flat = row * ncols + col
    total = np.bincount(flat, weights=ground[:, 2], minlength=nrows * ncols)
    count = np.bincount(flat, minlength=nrows * ncols)
    with np.errstate(invalid="ignore"):
        dtm = (total / count).reshape(nrows, ncols)
    empty = np.isnan(dtm)
    nearest = ndimage.distance_transform_edt(empty, return_distances=False, return_indices=True)
    return dtm[tuple(nearest)]


def height_above_ground(points, dtm, bounds, cell=CELL):
    x0, y0, _, _ = bounds
    col = ((points[:, 0] - x0) / cell).astype(int)
    row = ((points[:, 1] - y0) / cell).astype(int)
    ground_z = dtm[row, col]
    return points[:, 2] - ground_z, ground_z


def get_osm_footprints(bounds):
    """Building polygons from OpenStreetMap that lie fully inside the tile."""
    import osmnx as ox

    tile = gpd.GeoSeries([box(*bounds)], crs=CRS_LIDAR)
    area_wgs84 = tile.to_crs("EPSG:4326").iloc[0]
    osm = None
    ox.settings.overpass_rate_limit = False
    ox.settings.requests_timeout = 60
    for attempt in range(9):                     # public servers are often busy: retry
        ox.settings.overpass_url = OSM_SERVERS[attempt % len(OSM_SERVERS)]
        try:
            osm = ox.features_from_polygon(area_wgs84, tags={"building": True})
            break
        except Exception:
            print(f"   {ox.settings.overpass_url} is busy, trying another server in 15 s...")
            time.sleep(15)
    if osm is None:
        raise SystemExit("All OpenStreetMap servers are busy. Try again in 10 minutes.")
    osm = osm[osm.geom_type.isin(["Polygon", "MultiPolygon"])].to_crs(CRS_LIDAR)
    osm = osm[osm.within(tile.iloc[0])]          # drop buildings cut by the tile edge
    osm = osm.reset_index()
    id_column = "osmid" if "osmid" in osm.columns else "id"
    out = gpd.GeoDataFrame(
        {
            "osm_id": osm[id_column].values,
            "name": osm["name"].values if "name" in osm.columns else None,
            "building": osm["building"].values,
            "osm_height": _to_number(osm, "height"),
            "osm_levels": _to_number(osm, "building:levels"),
        },
        geometry=osm.geometry.values,
        crs=CRS_LIDAR,
    )
    return out


def _to_number(frame, column):
    if column not in frame.columns:
        return np.full(len(frame), np.nan)
    text = frame[column].astype(str).str.replace(",", ".").str.extract(r"(\d+\.?\d*)")[0]
    return pd.to_numeric(text, errors="coerce").values


def heights_per_building(footprints, building, heights, ground_z):
    """Match LiDAR building points to footprints and summarise each building."""
    tree = shapely.STRtree(footprints.geometry.values)
    points = shapely.points(building[:, 0], building[:, 1])
    point_idx, poly_idx = tree.query(points, predicate="within")
    matched = pd.DataFrame(
        {"poly": poly_idx, "h": heights[point_idx], "g": ground_z[point_idx]}
    )
    grouped = matched.groupby("poly")
    stats = pd.DataFrame(
        {
            "n_points": grouped["h"].size(),
            "height_lidar": grouped["h"].quantile(0.95),   # robust roof-top height
            "height_median": grouped["h"].median(),        # typical roof height
            "ground_elev": grouped["g"].median(),
        }
    )
    result = footprints.join(stats, how="inner")
    result = result[(result["n_points"] >= MIN_POINTS) & (result["height_lidar"] >= MIN_HEIGHT)]
    for column in ("height_lidar", "height_median", "ground_elev"):
        result[column] = result[column].round(1)
    return result


def report(result, n_footprints):
    print(f"\nOSM footprints inside the tile:        {n_footprints}")
    print(f"Buildings with a LiDAR height:         {len(result)}")
    print(f"Median building height:                {result['height_lidar'].median():.1f} m")
    top = result.sort_values("height_lidar", ascending=False).head(5)
    print("\nFive tallest buildings:")
    for _, r in top.iterrows():
        label = r["name"] if isinstance(r["name"], str) else f"OSM id {r['osm_id']}"
        print(f"  {r['height_lidar']:5.1f} m  {label}")

    with_height = result.dropna(subset=["osm_height"])
    print(f"\nBuildings with an OSM 'height' tag:    {len(with_height)}")
    if len(with_height) >= 3:
        diff = with_height["height_lidar"] - with_height["osm_height"]
        print(f"  Mean absolute difference:            {diff.abs().mean():.1f} m")
        print(f"  Median difference (LiDAR - OSM):     {diff.median():+.1f} m")

    with_levels = result.dropna(subset=["osm_levels"])
    with_levels = with_levels[with_levels["osm_levels"] > 0]
    print(f"Buildings with an OSM floor count:     {len(with_levels)}")
    if len(with_levels) >= 3:
        corr = with_levels["height_lidar"].corr(with_levels["osm_levels"])
        per_level = (with_levels["height_lidar"] / with_levels["osm_levels"]).median()
        print(f"  Correlation height vs floors:        {corr:.2f}")
        print(f"  Median LiDAR height per floor:       {per_level:.1f} m")


def main():
    print("1/5 Loading LiDAR points...")
    ground, building, bounds = load_lidar()
    print("2/5 Building the ground model...")
    dtm = build_ground_model(ground, bounds)
    heights, ground_z = height_above_ground(building, dtm, bounds)
    print("3/5 Downloading building footprints from OpenStreetMap...")
    footprints = get_osm_footprints(bounds)
    print("4/5 Matching LiDAR points to footprints...")
    result = heights_per_building(footprints, building, heights, ground_z)
    print("5/5 Saving results...")
    result.to_crs("EPSG:4326").to_file("buildings_heights.geojson", driver="GeoJSON")
    result.drop(columns="geometry").to_csv("buildings_heights.csv", index=False)
    report(result, len(footprints))
    print("\nSaved buildings_heights.geojson and buildings_heights.csv")


if __name__ == "__main__":
    main()