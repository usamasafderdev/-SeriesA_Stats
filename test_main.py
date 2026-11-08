from pathlib import Path

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)
PROJECT_FOLDER = Path(__file__).resolve().parent


def test_home_page_returns_original_html():
    response = client.get("/")
    original_html = (PROJECT_FOLDER / "index.html").read_bytes()

    assert response.status_code == 200
    assert response.content == original_html


def test_health_endpoint_returns_expected_message():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "application": "Serie A Tracker",
    }


def test_frontend_static_files_are_available():
    file_paths = [
        "/css/style.css",
        "/js/app.js",
        "/js/demo-data.js",
        "/js/formation-layout.js",
        "/assets/logo.svg",
        "/assets/stadium.jpg",
    ]

    for file_path in file_paths:
        response = client.get(file_path)

        assert response.status_code == 200, file_path
        assert response.content, file_path
