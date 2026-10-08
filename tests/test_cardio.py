import json
from datetime import datetime, timezone


def test_create_running_cardio_with_route(auth_client):
    start_time = datetime.now(timezone.utc).replace(microsecond=0)
    geojson = (
        '{"type":"LineString","coordinates":[[116.4,39.9],[116.5,40.0],[116.6,40.1]]}'
    )

    response = auth_client.post(
        "/api/cardio",
        json={
            "type": "run",
            "start_time": start_time.isoformat(),
            "distance_m": 5000,
            "duration_s": 1800,
            "geojson": geojson,
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["type"] == "run"
    assert datetime.fromisoformat(data["start_time"]) == start_time.replace(tzinfo=None)
    assert data["distance_m"] == 5000
    assert data["duration_s"] == 1800

    route_response = auth_client.get(f"/api/cardio/{data['id']}/geojson")

    assert route_response.status_code == 200, route_response.text
    assert json.loads(route_response.json()["geojson"]) == json.loads(geojson)
