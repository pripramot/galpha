import csv
import json
from typing import Dict

def csv_to_geojson(csv_path: str, lon_field: str = "lon", lat_field: str = "lat") -> Dict:
    features = []
    issues = []
    with open(csv_path, encoding='utf-8') as fp:
        reader = csv.DictReader(fp)
        for idx, row in enumerate(reader, start=1):
            try:
                lon = float(row[lon_field])
                lat = float(row[lat_field])
                feat = {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {k: v for k, v in row.items() if k not in (lon_field, lat_field)}
                }
                features.append(feat)
            except Exception as e:
                issues.append({"row": idx, "error": str(e)})
    return {"type": "FeatureCollection", "features": features, "issues": issues}

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python scripts/csv_to_geojson.py observations.csv [out.geojson]")
        sys.exit(1)
    csvp = sys.argv[1]
    outp = sys.argv[2] if len(sys.argv) > 2 else "out.geojson"
    result = csv_to_geojson(csvp)
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(result["features"] and {"type":"FeatureCollection","features":result["features"]} or {}, f, ensure_ascii=False, indent=2)
    if result.get("issues"):
        print("Issues:", result["issues"])
