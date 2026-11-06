import re

from fastapi.testclient import TestClient

from main import ASSET_VERSION, app, asset_version

ASSET_URL = re.compile(r"/assets/[\w./-]+\.\w+(\?v=\w+)?")


def test_index_versions_every_asset_url_and_is_revalidated():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-cache"
    urls = [match.group() for match in ASSET_URL.finditer(response.text)]
    assert f"/assets/style.css?v={ASSET_VERSION}" in urls
    assert f"/assets/app.js?v={ASSET_VERSION}" in urls
    assert all(url.endswith(f"?v={ASSET_VERSION}") for url in urls)


def test_stylesheet_versions_scene_urls():
    with TestClient(app) as client:
        response = client.get(f"/assets/style.css?v={ASSET_VERSION}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    assert f"/assets/scenes/snow_leopard.webp?v={ASSET_VERSION}" in response.text
    assert all(url.endswith(f"?v={ASSET_VERSION}") for url in
               (match.group() for match in ASSET_URL.finditer(response.text)))


def test_versioned_static_files_are_still_served():
    with TestClient(app) as client:
        assert client.get(f"/assets/app.js?v={ASSET_VERSION}").status_code == 200
        assert client.get(f"/assets/scenes/fox.webp?v={ASSET_VERSION}").status_code == 200


def test_version_changes_with_asset_content(tmp_path):
    (tmp_path / "pets").mkdir()
    sprite = tmp_path / "pets" / "cat-calm.webp"
    sprite.write_bytes(b"old")
    before = asset_version(tmp_path)
    assert before == asset_version(tmp_path)
    sprite.write_bytes(b"new")
    assert asset_version(tmp_path) != before
