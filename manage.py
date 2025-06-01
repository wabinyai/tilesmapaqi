import folium
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgba
from io import BytesIO
from PIL import Image
import base64
import os
import psycopg2
from dotenv import load_dotenv
from scipy.interpolate import griddata

load_dotenv()

# 1. Connect to PostgreSQL and fetch data
def fetch_aqi_data():
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME", "airqo"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASS", "postgres"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432")
    )
    cur = conn.cursor()
    cur.execute("SELECT latitude, longitude, pm2p5 AS pm FROM cams_pm25 WHERE pm2p5 IS NOT NULL ;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [(lat, lon, pm) for lat, lon, pm in rows]

# AQI utilities
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

# 2. Interpolation and mapping
def create_interpolated_overlay(data, resolution=1000):
    lats = np.array([d[0] for d in data])
    lons = np.array([d[1] for d in data])
    pms = np.array([d[2] for d in data])
    aqis = np.array([pm25_to_aqi(pm) for pm in pms])

    lat_min, lat_max = lats.min(), lats.max()
    lon_min, lon_max = lons.min(), lons.max()

    grid_lat, grid_lon = np.mgrid[lat_min:lat_max:complex(resolution), lon_min:lon_max:complex(resolution)]
    grid_aqi = griddata((lats, lons), aqis, (grid_lat, grid_lon), method='cubic')

    # Convert AQI values to RGBA colors
    rgba_image = np.zeros((resolution, resolution, 4))
    for i in range(resolution):
        for j in range(resolution):
            if np.isnan(grid_aqi[i, j]):
                rgba_image[i, j] = (0, 0, 0, 0)  # Transparent for NaN
            else:
                rgba_image[i, j] = aqi_to_color(grid_aqi[i, j])

    return rgba_image, (lat_min, lat_max, lon_min, lon_max)

# 3. Save image and add to map with horizontal repetition
def add_image_overlay(image_array, bounds, map_obj):
    fig, ax = plt.subplots(figsize=(8, 8), dpi=1000)
    ax.imshow(image_array, extent=[0, 1, 0, 1], origin='lower')
    ax.axis('off')

    buf = BytesIO()
    plt.savefig(buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0)
    plt.close(fig)
    buf.seek(0)

    original_image = Image.open(buf)

    # Repeat image horizontally (3x)
    total_width = original_image.width * 3
    repeated_image = Image.new('RGBA', (total_width, original_image.height))
    for i in range(3):
        repeated_image.paste(original_image, (i * original_image.width, 0))

    repeated_buf = BytesIO()
    repeated_image.save(repeated_buf, format='PNG')
    repeated_buf.seek(0)

    img_b64 = base64.b64encode(repeated_buf.getvalue()).decode('utf-8')
    data_url = f"data:image/png;base64,{img_b64}"

    lat_min, lat_max, lon_min, lon_max = bounds
    width_deg = lon_max - lon_min

    # Extend the overlay bounds to match repeated image
    extended_bounds = [[lat_min, lon_min - width_deg], [lat_max, lon_max + width_deg]]

    folium.raster_layers.ImageOverlay(
        image=data_url,
        bounds=extended_bounds,
        opacity=0.5,
        interactive=False,
        cross_origin=False,
    ).add_to(map_obj)

# MAIN EXECUTION
data = fetch_aqi_data()

if not data:
    print("No data fetched.")
    exit()

# Center the map over central Africa by default
m = folium.Map(location=[0, 20], zoom_start=3)

image_array, bounds = create_interpolated_overlay(data, resolution=500)
add_image_overlay(image_array, bounds, m)

# Save the map
m.save("aqi_map.html")
print("Map saved to aqi_map.html")

 
print(f"✓ AQI map saved ")