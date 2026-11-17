import sys

import laspy
import numpy as np
import open3d as o3d

FILE = "790_5416.laz"
STEP = 4  # keep every 4th point so the viewer stays smooth

CLASS_COLOURS = {
    1: (0.6, 0.6, 0.6),     # unclassified - grey
    2: (0.65, 0.5, 0.35),   # ground - brown
    6: (0.9, 0.2, 0.2),     # building - red
    20: (0.2, 0.7, 0.3),    # vegetation and other objects - green
}

RAMP_POS = [0.0, 0.33, 0.66, 1.0]
RAMP_RGB = np.array([(0.1, 0.2, 0.8), (0.1, 0.8, 0.4), (1.0, 0.9, 0.1), (0.9, 0.1, 0.1)])


def load_points(path=FILE, step=STEP):
    las = laspy.read(path)
    xyz = np.column_stack([las.x, las.y, las.z])[::step]
    classes = np.asarray(las.classification)[::step]
    return xyz, classes


def colours_by_class(classes):
    colours = np.full((len(classes), 3), 0.6)
    for code, rgb in CLASS_COLOURS.items():
        colours[classes == code] = rgb
    return colours


def colours_by_height(z):
    low, high = np.percentile(z, [1, 99])
    t = np.clip((z - low) / (high - low), 0, 1)
    return np.column_stack([np.interp(t, RAMP_POS, RAMP_RGB[:, i]) for i in range(3)])


def build_cloud(xyz, colours):
    local = xyz - xyz.min(axis=0)
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(local)
    cloud.colors = o3d.utility.Vector3dVector(colours)
    return cloud


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "class"
    if mode not in ("class", "height"):
        sys.exit("Use: python visualize_3d.py class   or   python visualize_3d.py height")

    print("Loading points, this takes a moment...")
    xyz, classes = load_points()
    colours = colours_by_class(classes) if mode == "class" else colours_by_height(xyz[:, 2])
    cloud = build_cloud(xyz, colours)
    print(f"Showing {len(xyz):,} points coloured by {mode}. Press P for a screenshot, Q to close.")
    o3d.visualization.draw_geometries(
        [cloud], window_name=f"Deggendorf LiDAR - by {mode}", width=1400, height=900
    )


if __name__ == "__main__":
    main()