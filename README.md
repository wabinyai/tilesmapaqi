# tilesmapaqi

.
├── app.py              # Flask API for serving MVT tiles
├── aqi_utils.py        # PM10 to AQI conversion logic
├── tile_server.html    # Mapbox frontend
├── requirements.txt    # Dependencies


### Create a Virtual Environment

Run the following command to create a virtual environment:

```sh
python -m venv venv
```

### Activate the Virtual Environment

#### Linux and macOS
```sh
source venv/bin/activate
```

#### Windows
```sh
venv\Scripts\activate
```

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
