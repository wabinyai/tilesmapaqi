# tilesmapaqi

.
├── app.py              # Flask API for serving MVT tiles
├── aqi_utils.py        # PM10 to AQI conversion logic
├── tile_server.html    # Mapbox frontend
├── requirements.txt    # Dependencies

### Install Dependencies

Ensure you have the necessary dependencies installed:

```sh
python -m pip install --upgrade pip
pip install -r requirements.txt
```

start docker
```sh
docker-compose up -d
```
stop docker
```sh
docker-compose down
```

access airflow
```sh
http://localhost:8080
```
