from app.db import get_conn


async def test_request_code_user_not_found(client, seed):
    resp = await client.post("/api/auth/request-code", json={"email": "unknown@test.com"})
    assert resp.status_code == 404


async def test_full_login_flow(client, seed):
    seed(users=["alice@school.edu"])

    resp = await client.post("/api/auth/request-code", json={"email": "alice@school.edu"})
    assert resp.status_code == 200

    with get_conn() as conn:
        row = conn.execute("SELECT code FROM verification_codes WHERE email = ?", ("alice@school.edu",)).fetchone()
        code = row["code"]

    resp = await client.post("/api/auth/verify", json={"email": "alice@school.edu", "code": code})
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["email"] == "alice@school.edu"
    assert "access_token" in data
    assert resp.cookies.get("jwt_token") is not None
    assert resp.cookies.get("refresh_token") is not None

    with get_conn() as conn:
        db_expiry = conn.execute("SELECT refresh_token_expires_at FROM users WHERE email = ?", ("alice@school.edu",)).fetchone()
        assert db_expiry["refresh_token_expires_at"] is not None
        remaining = conn.execute("SELECT COUNT(*) AS c FROM verification_codes WHERE email = ?", ("alice@school.edu",)).fetchone()
        assert remaining["c"] == 0


async def test_me_after_login(client, seed):
    seed(users=["alice@school.edu"])

    with get_conn() as conn:
        row = conn.execute("SELECT code FROM verification_codes WHERE email = ?", ("alice@school.edu",)).fetchone()
        existing = row["code"] if row else None

    if not existing:
        await client.post("/api/auth/request-code", json={"email": "alice@school.edu"})
        with get_conn() as conn:
            row = conn.execute("SELECT code FROM verification_codes WHERE email = ?", ("alice@school.edu",)).fetchone()
            code = row["code"]
    else:
        code = existing

    await client.post("/api/auth/verify", json={"email": "alice@school.edu", "code": code})

    resp = await client.get("/api/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "alice@school.edu"
    assert "id" in data


async def test_refresh_token(client, seed):
    seed(users=["alice@school.edu"])
    await client.post("/api/auth/request-code", json={"email": "alice@school.edu"})
    with get_conn() as conn:
        row = conn.execute("SELECT code FROM verification_codes WHERE email = ?", ("alice@school.edu",)).fetchone()
        code = row["code"]
    await client.post("/api/auth/verify", json={"email": "alice@school.edu", "code": code})

    with get_conn() as conn:
        before = conn.execute("SELECT refresh_token_expires_at FROM users WHERE email = ?", ("alice@school.edu",)).fetchone()["refresh_token_expires_at"]

    resp = await client.post("/api/auth/refresh")
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data

    with get_conn() as conn:
        after = conn.execute("SELECT refresh_token_expires_at FROM users WHERE email = ?", ("alice@school.edu",)).fetchone()["refresh_token_expires_at"]
        assert after == before


async def test_logout(client, seed):
    seed(users=["alice@school.edu"])
    await client.post("/api/auth/request-code", json={"email": "alice@school.edu"})
    with get_conn() as conn:
        row = conn.execute("SELECT code FROM verification_codes WHERE email = ?", ("alice@school.edu",)).fetchone()
        code = row["code"]
    await client.post("/api/auth/verify", json={"email": "alice@school.edu", "code": code})

    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Logged out"

    with get_conn() as conn:
        db_expiry = conn.execute("SELECT refresh_token_expires_at FROM users WHERE email = ?", ("alice@school.edu",)).fetchone()
        assert db_expiry["refresh_token_expires_at"] is None
