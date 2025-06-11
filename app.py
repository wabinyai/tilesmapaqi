from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import os
import psycopg2
import math
from datetime import datetime
import pytz
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(override=True)

# Initialize Flask app
app = Flask(__name__)
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Log response headers for debugging
@app.after_request
def log_response_headers(response):
    logger.info(f"Response headers: {response.headers}")
    return response

# Validate environment variables
REQUIRED_ENV_VARS = ["DB_NAME", "DB_USER", "DB_PASS", "DB_HOST", "DB_PORT"]
missing_env_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
if missing_env_vars:
    logger.critical(f"Missing environment variables: {missing_env_vars}")
    raise EnvironmentError(f"Missing required environment variables: {missing_env_vars}")

def fetch_wind_data():
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
        cur = conn.cursor()
        cur.execute("""
            SELECT latitude, longitude, wind_speed, wind_direction, time
            FROM nomads_wind
            WHERE wind_speed IS NOT NULL AND wind_direction IS NOT NULL;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        logger.info(f"Fetched {len(rows)} wind data records.")
        return rows
    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        return []

def create_grid(rows):
    grid = {}
    lats, lons = set(), set()
    ref_time = None

    for lat, lon, speed, direction, timestamp in rows:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or speed < 0:
            continue

        lat, lon = round(lat, 1), round(lon, 1)
        #rad = math.radians(direction)
        rad = math.radians((direction + 180) % 360)
        u = round(speed * math.sin(rad), 2)
        v = round(speed * math.cos(rad), 2)

        grid[(lat, lon)] = {"u": u, "v": v}
        lats.add(lat)
        lons.add(lon)

        if not ref_time or (timestamp and timestamp > ref_time):
            ref_time = timestamp

    lats, lons = sorted(lats, reverse=True), sorted(lons)
    nx, ny = len(lons), len(lats)

    if not nx or not ny:
        logger.warning("Empty grid: insufficient valid data.")
        return None, None, None, None, None, None

    return grid, lats, lons, nx, ny, ref_time

def create_velocity_components(grid, lats, lons, nx, ny, ref_time):
    u_data, v_data = [], []

    for lat in lats:
        for lon in lons:
            point = grid.get((lat, lon), {"u": 0.0, "v": 0.0})
            u_data.append(point["u"])
            v_data.append(point["v"])

    if len(u_data) != nx * ny or len(v_data) != nx * ny:
        logger.error("Mismatch in grid data length.")
        return None, None

    dx = round((lons[-1] - lons[0]) / (nx - 1), 2) if nx > 1 else 0.1
    dy = round((lats[0] - lats[-1]) / (ny - 1), 2) if ny > 1 else 0.1

    base_header = {
        "parameterUnit": "m.s-1",
        "parameterCategory": 2,
        "nx": nx,
        "ny": ny,
        "lo1": lons[0],
        "la1": lats[0],
        "lo2": lons[-1],
        "la2": lats[-1],
        "dx": dx,
        "dy": dy,
        "refTime": ref_time.strftime("%Y-%m-%dT%H:%M:%SZ") if ref_time else datetime.now(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    }

    u_component = {
        "header": {**base_header, "parameterNumber": 2},
        "data": u_data
    }

    v_component = {
        "header": {**base_header, "parameterNumber": 3},
        "data": v_data
    }

    return u_component, v_component

@app.route("/api/wind", methods=["GET", "OPTIONS"])
def wind_data():
    logger.info(f"Received {request.method} request for /api/wind")
    if request.method == "OPTIONS":
        response = jsonify({})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Methods", "GET, OPTIONS")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        return response, 200

    rows = fetch_wind_data()
    if not rows:
        response = jsonify({"error": "No wind data found"})
        response.status_code = 500
    else:
        grid, lats, lons, nx, ny, ref_time = create_grid(rows)
        if grid is None:
            response = jsonify({"error": "Failed to generate grid"})
            response.status_code = 500
        else:
            u_component, v_component = create_velocity_components(grid, lats, lons, nx, ny, ref_time)
            if u_component is None or v_component is None:
                response = jsonify({"error": "Failed to generate wind components"})
                response.status_code = 500
            else:
                response = jsonify([u_component, v_component])

    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Methods", "GET, OPTIONS")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type")
    return response

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)