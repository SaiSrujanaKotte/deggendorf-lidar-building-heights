import os

import branca.colormap as cm
import folium
import geopandas as gpd

IN_FILE = "buildings_heights.geojson"
OUT_DIR = "docs"            # GitHub Pages can publish this folder directly
OUT_FILE = os.path.join(OUT_DIR, "index.html")

buildings = gpd.read_file(IN_FILE)
buildings["name"] = buildings["name"].fillna("")
buildings["osm_height"] = buildings["osm_height"].round(1)

# Colour scale from low (yellow) to high (dark red); capped at 30 m so a few towers
# don't wash out the differences between ordinary buildings
colormap = cm.LinearColormap(
    ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"], vmin=3, vmax=30
)
colormap.caption = "Building height above ground from LiDAR (m)"

centre = buildings.geometry.union_all().centroid
m = folium.Map(location=[centre.y, centre.x], zoom_start=16, tiles=None)

# Background maps (Esri tiles work both from a local file and from a website)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    attr="Esri, HERE, Garmin, OpenStreetMap contributors",
    name="Light grey map",
    max_zoom=20,
    max_native_zoom=16,
).add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri, Maxar, Earthstar Geographics",
    name="Satellite",
    max_zoom=20,
    max_native_zoom=19,
).add_to(m)


def style(feature):
    height = feature["properties"]["height_lidar"]
    return {
        "fillColor": colormap(min(height, 30)),
        "color": "#555555",
        "weight": 0.5,
        "fillOpacity": 0.85,
    }


folium.GeoJson(
    buildings,
    name="Buildings by height",
    style_function=style,
    highlight_function=lambda f: {"weight": 2, "color": "#000000"},
    tooltip=folium.GeoJsonTooltip(fields=["height_lidar"], aliases=["Height (m):"]),
    popup=folium.GeoJsonPopup(
        fields=["name", "building", "height_lidar", "height_median",
                "osm_height", "osm_levels", "n_points", "ground_elev"],
        aliases=["Name", "Building type", "LiDAR height, roof top (m)",
                 "LiDAR height, median roof (m)", "OSM height tag (m)",
                 "OSM floors", "LiDAR points used", "Ground elevation (m)"],
    ),
).add_to(m)

colormap.add_to(m)
folium.LayerControl(collapsed=False).add_to(m)

title = """
<div style="position: fixed; bottom: 30px; left: 10px; z-index: 9999; background: white;
            padding: 8px 12px; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,.3);
            font-family: sans-serif; font-size: 14px;">
  <b>Deggendorf building heights from airborne LiDAR</b><br>
  Click a building for details.<br>
  <span style="font-size: 11px; color: #555;">
    Data: Bayerische Vermessungsverwaltung (CC BY 4.0), &copy; OpenStreetMap contributors (ODbL)
  </span>
</div>
"""
m.get_root().html.add_child(folium.Element(title))

os.makedirs(OUT_DIR, exist_ok=True)
m.save(OUT_FILE)
print(f"Saved {OUT_FILE} with {len(buildings)} buildings. Open it in your browser.")