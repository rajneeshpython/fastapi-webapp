import pytest
from httpx import AsyncClient

from tests.conftest import auth_header, create_test_user, login_user


@pytest.mark.anyio
async def test_get_posts_empty(client: AsyncClient):
    response = await client.get("/api/posts")

    assert response.status_code == 200
    data = response.json()
    assert data["posts"] == []
    assert data["total"] == 0
    assert data["has_more"] is False


@pytest.mark.anyio
async def test_get_post_not_found(client: AsyncClient):
    response = await client.get("/api/posts/999")

    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "Post not found"


@pytest.mark.anyio
async def test_create_post_success(client: AsyncClient):
    user = await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token)

    response = await client.post(
        "/api/posts",
        json={
            "title": "Test Post",
            "content": "This is a test post.",
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Post"
    assert data["content"] == "This is a test post."
    assert data["author"]["id"] == user["id"]
    assert "id" in data
    assert "date_posted" in data
    assert data["author"]["username"] == "testuser"


@pytest.mark.anyio
async def test_create_post_unauthorized(client: AsyncClient):
    response = await client.post(
        "/api/posts",
        json={
            "title": "Unauthorized Post",
            "content": "This post should not be created.",
        },
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"] == "Not authenticated"


@pytest.mark.anyio
async def test_update_post_success(client: AsyncClient):
    user = await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token)

    # Create a post to update
    create_response = await client.post(
        "/api/posts",
        json={
            "title": "Original Title",
            "content": "Original content.",
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    post_id = create_response.json()["id"]

    # Update the post
    update_response = await client.patch(
        f"/api/posts/{post_id}",
        json={
            "title": "Updated Title"
        },
        headers=headers,
    )
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["title"] == "Updated Title"


@pytest.mark.anyio
async def test_update_post_wrong_user(client: AsyncClient):
    # Create first user and post
    user1 = await create_test_user(client, username="user1", email="user1@example.com")
    token1 = await login_user(client, email="user1@example.com")
    headers1 = auth_header(token1)

    # Create a post to update
    create_response = await client.post(
        "/api/posts",
        json={
            "title": "Original Title",
            "content": "Original content.",
        },
        headers=headers1,
    )
    assert create_response.status_code == 201
    post_id = create_response.json()["id"]

    # Try to update the post with a different user
    user2 = await create_test_user(client, username="user2", email="user2@example.com")
    token2 = await login_user(client, email="user2@example.com")
    headers2 = auth_header(token2)

    update_response = await client.patch(
        f"/api/posts/{post_id}",
        json={
            "title": "Updated Title"
        },
        headers=headers2,
    )
    assert update_response.status_code == 403
    data = update_response.json()
    assert data["detail"] ==  "Not authorized to update this post"


@pytest.mark.anyio
async def test_get_posts_with_pagination(client: AsyncClient):
    user = await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token)

    # Create 15 posts
    for i in range(15):
        response = await client.post(
            "/api/posts",
            json={
                "title": f"Post {i+1}",
                "content": f"Content for post {i+1}.",
            },
            headers=headers,
        )
        assert response.status_code == 201

    # Get first page of posts (default limit is 10)
    response = await client.get("/api/posts")
    assert response.status_code == 200
    data = response.json()
    assert len(data["posts"]) == 10
    assert data["total"] == 15
    assert data["has_more"] is True

    # Get second page of posts
    response = await client.get("/api/posts?limit=15")
    assert response.status_code == 200
    data = response.json()
    assert len(data["posts"]) == 15
    assert data["total"] == 15
    assert data["has_more"] is False

    # Get posts with a skip and limit
    response = await client.get("/api/posts?skip=5&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data["posts"]) == 5
    assert data["total"] == 15
    assert data["has_more"] is True
    assert data["skip"] == 5
    assert data["limit"] == 5


@pytest.mark.anyio
async def test_delete_post_success(client: AsyncClient):
    user = await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token)

    # Create a post to delete
    create_response = await client.post(
        "/api/posts",
        json={
            "title": "Post to Delete",
            "content": "This post will be deleted.",
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    post_id = create_response.json()["id"]

    # Delete the post
    delete_response = await client.delete(f"/api/posts/{post_id}", headers=headers)
    assert delete_response.status_code == 204

    # Verify the post is deleted
    get_response = await client.get(f"/api/posts/{post_id}")
    assert get_response.status_code == 404