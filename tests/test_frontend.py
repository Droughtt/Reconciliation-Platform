def test_frontend_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Reconcile" in resp.content