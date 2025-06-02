from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from dotenv import load_dotenv
import os
import numpy as np
from scipy.interpolate import griddata
from matplotlib.colors import to_rgba
from io import BytesIO
from PIL import Image
import base64
from datetime import datetime
import redis
import json

# Load environment variables
load_dotenv()

# FastAPI app
app = FastAPI()

# CORS
origins = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis setup
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True  # Automatically decode strings
)

# --- AQI Utility Functions ---

def aqi_to_color(aqi):
    if aqi <= 50:
        return to_rgba("green")
    elif aqi <= 100:
        return to_rgba("yellow")
    elif aqi <= 150:
        return to_rgba("orange")
    elif aqi <= 200:
        return to_rgba("red")
    elif aqi <= 300:
        return to_rgba("purple")
    else:
        return to_rgba("maroon")

def pm25_to_aqi(pm):
    if pm <= 12:
        return int((50 / 12) * pm)
    elif pm <= 35.4:
        return int(((100 - 51) / (35.4 - 12.1)) * (pm - 12.1) + 51)
    elif pm <= 55.4:
        return int(((150 - 101) / (55.4 - 35.5)) * (pm - 35.5) + 101)
    elif pm <= 150.4:
        return int(((200 - 151) / (150.4 - 55.5)) * (pm - 55.5) + 151)
    elif pm <= 250.4:
        return int(((300 - 201) / (250.4 - 150.5)) * (pm - 150.5) + 201)
    else:
        return int(((500 - 301) / (500.4 - 250.5)) * (pm - 250.5) + 301)

def normalize_longitude(lon):
    return ((lon + 180) % 360) - 180

# --- Data Fetch and Processing ---

def fetch_aqi_data():
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME", "airqo"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASS", "postgres"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432")
    )
    cur = conn.cursor()
    cur.execute("SELECT latitude, longitude, pm10 FROM cams_pm10 WHERE pm10 IS NOT NULL;")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    valid_data = []
    for lat, lon, pm in rows:
        if -90 <= lat <= 90:
            norm_lon = normalize_longitude(lon)
            valid_data.append((lat, norm_lon, pm))
    return valid_data

def create_interpolated_overlay(data, resolution=500):
    if not data:
        return None

    lats = np.array([d[0] for d in data])
    lons = np.array([d[1] for d in data])
    pms = np.array([d[2] for d in data])
    aqis = np.array([pm25_to_aqi(pm) for pm in pms])

    lat_min, lat_max = lats.min(), lats.max()
    lon_min, lon_max = lons.min(), lons.max()

    if lon_max - lon_min > 180:
        lon_min, lon_max = -180, 180

    grid_lon, grid_lat = np.meshgrid(
        np.linspace(lon_min, lon_max, resolution),
        np.linspace(lat_max, lat_min, resolution)
    )

    grid_aqi = griddata((lats, lons), aqis, (grid_lat, grid_lon), method='cubic')

    rgba_image = np.zeros((resolution, resolution, 4))
    for i in range(resolution):
        for j in range(resolution):
            if np.isnan(grid_aqi[i, j]):
                rgba_image[i, j] = (0, 0, 0, 0)
            else:
                rgba_image[i, j] = aqi_to_color(grid_aqi[i, j])

    img = Image.fromarray((rgba_image * 255).astype(np.uint8), mode="RGBA")

    buf = BytesIO()
    img.save(buf, format='PNG')
    img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    data_url = f"data:image/png;base64,{img_b64}"

    return {
        "mapimage": {
            "image": data_url,
            "bounds": [[lat_min, lon_min], [lat_max, lon_max]],
            "lat_min": float(lat_min),
            "lat_max": float(lat_max),
            "lon_min": float(lon_min),
            "lon_max": float(lon_max)
        },
        "time": {
            "generated_at": datetime.utcnow().isoformat() + "Z"
        }
    }

# --- Main API Route with Redis Caching ---

@app.get("/aqi-data")
async def get_aqi_data():
    try:
        timestamp_key = datetime.utcnow().strftime("%Y-%m-%dT%H")
        cache_key = f"airqo:aqi_overlay:{timestamp_key}"

        # Try Redis
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return JSONResponse(content=json.loads(cached))
        except Exception as redis_err:
            print(f"[Redis Error - get] {redis_err}")

        # No cache, generate result
        data = fetch_aqi_data()
        if not data:
            return JSONResponse(status_code=404, content={"message": "No valid data available"})

        result = create_interpolated_overlay(data)
        if not result:
            return JSONResponse(status_code=404, content={"message": "Could not generate overlay"})

        # Cache for 10 minutes
        try:
            redis_client.setex(cache_key, 600, json.dumps(result))
        except Exception as redis_err:
            print(f"[Redis Error - set] {redis_err}")

        return result

    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})
