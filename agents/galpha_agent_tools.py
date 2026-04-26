import os
import math
import random
import json
import requests
from typing import Dict, Any, List, Optional

# --- Helpers --------------------------------------------------------------

def _is_coord_valid(coords: List[float]) -> bool:
    try:
        lon, lat = float(coords[0]), float(coords[1])
        return -180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0
    except Exception:
        return False

def _meters_to_deg_lat(meters: float) -> float:
    # ประมาณ: 1 deg latitude ~ 111320 m
    return meters / 111320.0

def _meters_to_deg_lon(meters: float, lat_deg: float) -> float:
    # ความยาวของ 1 deg longitude ที่ละติจูด lat = 111320 * cos(lat)
    return meters / (111320.0 * math.cos(math.radians(lat_deg)) + 1e-9)

def _jitter_coord(coord: List[float], radius_m: float) -> List[float]:
    lon, lat = float(coord[0]), float(coord[1])
    # random direction and distance
    r = random.random()
    theta = random.random() * 2 * math.pi
    # uniform distribution in circle: sqrt(r) * radius
    dist = math.sqrt(r) * radius_m
    dlat = _meters_to_deg_lat(dist * math.cos(theta))
    dlon = _meters_to_deg_lon(dist * math.sin(theta), lat)
    return [lon + dlon, lat + dlat]

def _generalize_coord(coord: List[float], precision: int) -> List[float]:
    lon, lat = float(coord[0]), float(coord[1])
    return [round(lon, precision), round(lat, precision)]

# --- Enrichment -----------------------------------------------------------

def mapbox_reverse_geocode(lon: float, lat: float, token: str) -> Optional[Dict[str, Any]]:
    """Call Mapbox reverse geocoding. Returns the top place feature or None."""
    if not token:
        return None
    try:
        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{lon},{lat}.json"
        params = {
            "access_token": token,
            "limit": 1,
            "types": "place,region,country,address,locality"
        }
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("features"):
            return data["features"][0]
        return None
    except Exception as e:
        # เก็บ error ไว้ใน properties หากต้องการ debug
        return {"error": str(e)}

def gbif_occurrence_search(lon: float, lat: float, radius_km: float = 1.0, limit: int = 5) -> Dict[str, Any]:
    """
    Simple GBIF enrichment: query occurrences inside a small bounding box around point.
    Uses public GBIF API (no token required).
    Returns small summary: count and sample occurrences (limit).
    """
    try:
        delta = radius_km / 111.0  # ~ degrees
        min_lon, max_lon = lon - delta, lon + delta
        min_lat, max_lat = lat - delta, lat + delta
        # construct POLYGON bbox for geometry param
        poly = f"POLYGON(({min_lon} {min_lat},{max_lon} {min_lat},{max_lon} {max_lat},{min_lon} {max_lat},{min_lon} {min_lat}))"
        url = "https://api.gbif.org/v1/occurrence/search"
        params = {"geometry": poly, "limit": limit, "hasCoordinate": "true"}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        return {"count": data.get("count", 0), "results": data.get("results", [])}
    except Exception as e:
        return {"error": str(e)}

# --- Core validation & processing ----------------------------------------

def geojson_validate(geojson_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Basic validation only: check coordinates, properties, duplicates.
    This function remains available standalone.
    """
    features = geojson_data.get("features", [])
    anomalies = []
    seen_coords = set()
    for idx, feat in enumerate(features, start=1):
        g = feat.get("geometry", {})
        prop = feat.get("properties", {})
        coords = g.get("coordinates", [])
        if not coords or coords == [None, None]:
            anomalies.append({"index": idx, "reason": "missing coordinates"})
            continue
        if not _is_coord_valid(coords):
            anomalies.append({"index": idx, "reason": "invalid coordinates", "coords": coords})
            continue
        coord_key = (round(float(coords[0]), 6), round(float(coords[1]), 6))
        if coord_key in seen_coords:
            anomalies.append({"index": idx, "reason": "duplicate coordinates", "coords": coords})
        else:
            seen_coords.add(coord_key)
        if not prop or not isinstance(prop, dict):
            anomalies.append({"index": idx, "reason": "missing properties"})
    summary = f"ข้อมูล GeoJSON มี {len(features)} features, พบ anomaly {len(anomalies)} รายการ"
    map_actions = []
    if anomalies:
        map_actions.append({"type": "highlight", "payload": {"indexes": [a["index"] for a in anomalies]}})
    return {
        "summary": summary,
        "geojson": geojson_data,
        "anomalies": anomalies,
        "map_actions": map_actions
    }

def process_geojson(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Orchestrator entrypoint expected by manifest.
    Input (payload) shape:
    {
      "geojson": { FeatureCollection ... },
      "options": {
         "validate": true,
         "enrich": {"mapbox": true, "gbif": true, "gbif_radius_km": 1.0},
         "mask": {"method": "jitter", "radius_m": 50} OR {"method":"generalize","precision":3}
      }
    }

    Returns schema:
    {
      "summary": str,
      "geojson": FeatureCollection,
      "anomalies": [...],
      "map_actions": [...]
    }
    """
    geojson_data = payload.get("geojson") or payload  # allow passing geojson directly
    options = payload.get("options", {}) if isinstance(payload, dict) else {}
    validate_flag = options.get("validate", True)
    enrich_opts = options.get("enrich", {})
    mask_opts = options.get("mask", {})

    # prepare tokens from env (do NOT hardcode tokens)
    mapbox_token = os.getenv("MAPBOX_TOKEN", "")
    # GBIF public API does not strictly require token; we still read if present
    gbif_token = os.getenv("GBIF_TOKEN", "")

    features = geojson_data.get("features", [])
    anomalies = []
    seen_coords = set()

    for idx, feat in enumerate(features, start=1):
        g = feat.get("geometry", {})
        prop = feat.setdefault("properties", {})
        coords = g.get("coordinates", [])

        # validate
        if validate_flag:
            if not coords or coords == [None, None]:
                anomalies.append({"index": idx, "reason": "missing coordinates"})
                continue
            if not _is_coord_valid(coords):
                anomalies.append({"index": idx, "reason": "invalid coordinates", "coords": coords})
                continue

        lon, lat = float(coords[0]), float(coords[1])

        # duplicate check
        coord_key = (round(lon, 6), round(lat, 6))
        if coord_key in seen_coords:
            anomalies.append({"index": idx, "reason": "duplicate coordinates", "coords": coords})
        else:
            seen_coords.add(coord_key)

        # enrich: Mapbox
        if enrich_opts.get("mapbox") and mapbox_token:
            mb = mapbox_reverse_geocode(lon, lat, mapbox_token)
            if mb:
                prop["_mapbox_place_name"] = mb.get("place_name") or None
                prop["_mapbox_feature"] = {"id": mb.get("id"), "type": mb.get("place_type"), "raw": mb}
        elif enrich_opts.get("mapbox") and not mapbox_token:
            prop["_mapbox_note"] = "MAPBOX_TOKEN not set"

        # enrich: GBIF
        if enrich_opts.get("gbif"):
            radius_km = float(enrich_opts.get("gbif_radius_km", 1.0))
            gbif_data = gbif_occurrence_search(lon, lat, radius_km=radius_km, limit=int(enrich_opts.get("gbif_limit", 5)))
            prop["_gbif"] = {"query_radius_km": radius_km, "result_sample": gbif_data}

        # mask
        if mask_opts:
            method = mask_opts.get("method")
            if method == "jitter":
                radius_m = float(mask_opts.get("radius_m", 50))
                new_coords = _jitter_coord([lon, lat], radius_m)
                g["coordinates"] = new_coords
                prop["_masking"] = {"method": "jitter", "radius_m": radius_m}
            elif method == "generalize":
                precision = int(mask_opts.get("precision", 3))
                new_coords = _generalize_coord([lon, lat], precision)
                g["coordinates"] = new_coords
                prop["_masking"] = {"method": "generalize", "precision": precision}
            else:
                # no mask or unknown method
                pass

        # property sanity - ensure id exists
        if "id" not in prop:
            prop.setdefault("id", str(idx))

    summary = f"ดำเนินการกับ {len(features)} features; พบ anomaly {len(anomalies)} รายการ"
    map_actions = []
    if anomalies:
        map_actions.append({"type": "highlight", "payload": {"indexes": [a["index"] for a in anomalies]}})
        # zoom to first anomaly if coords exist
        first = anomalies[0]
        if "coords" in first and first["coords"]:
            lon0, lat0 = first["coords"][0], first["coords"][1]
            map_actions.append({"type": "zoomTo", "payload": {"center": [lon0, lat0], "zoom": 12}})

    return {"summary": summary, "geojson": geojson_data, "anomalies": anomalies, "map_actions": map_actions}
