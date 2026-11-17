import laspy, numpy as np

las = laspy.read("790_5416.laz")
print("Points:", len(las.points))
print("CRS:", las.header.parse_crs())
print("X range:", las.x.min(), las.x.max())
print("Y range:", las.y.min(), las.y.max())
print("Z range:", las.z.min(), las.z.max())
classes, counts = np.unique(las.classification, return_counts=True)
for c, n in zip(classes, counts):
    print(f"class {c}: {n} points")