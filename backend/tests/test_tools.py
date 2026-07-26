async def test_list_tools(client):
    resp = await client.get("/api/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    assert any(t["name"] for t in data)
