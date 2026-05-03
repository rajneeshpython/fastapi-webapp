from io import BytesIO
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header, create_test_user, login_user


@pytest.mark.anyio
async def test_create_user_validation_error(client: AsyncClient):
    response = await client.post(
        "/api/users",
        json={
            "username": "testuser",
        },
    )
    assert response.status_code == 422
    assert "email" in response.text
    assert "password" in response.text


@pytest.mark.anyio
async def test_create_user_duplicate_email(client: AsyncClient):
    # First create a user with the email
    # This line is already in the test, so we can just call it without parameters since it uses the default email
    # await create_test_user(client)
    await create_test_user(client, email="test@example.com")

    # Then try to create another user with the same email
    response = await client.post(
        "/api/users",
        json={
            "username": "testuser2",
            "email": "test@example.com",  # Duplicate email
            "password": "testpassword123",
        },
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "Email already registered"


@pytest.mark.anyio
async def test_create_user_success(client: AsyncClient):
    # Create a user with valid data and check the response don't use default email to avoid duplicate email error
    response = await client.post(
        "/api/users",
        json={
            "username": "newtestuser",
            "email": "newtest@example.com",
            "password": "testpassword123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "newtestuser"
    assert data["email"] == "newtest@example.com"
    assert "id" in data
    assert "image_path" in data
    assert "image_file" in data
    assert "password" not in data
    assert "hashed_password" not in data


@pytest.mark.anyio
async def test_upload_profile_picture(client: AsyncClient, mocked_aws):
    user = await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token)

    test_image_path = Path(__file__).parent / "test_image.jpg"
    image_bytes = test_image_path.read_bytes()

    response = await client.patch(
        f"/api/users/{user['id']}/picture",
        files={"file": ("profile.jpg", BytesIO(image_bytes), "image/jpeg")},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["image_file"] is not None
    assert data["image_file"].endswith(".jpg")
    assert "s3" in data["image_path"]


    s3_objects = mocked_aws.list_objects_v2(Bucket="test-bucket")
    assert "Contents" in s3_objects
    assert len(s3_objects["Contents"]) == 1
    assert s3_objects["Contents"][0]["Key"].endswith(".jpg")


@pytest.mark.anyio
async def test_forgot_password_send_email(client: AsyncClient, mocked_aws):
    user = await create_test_user(client)
    
    with patch("routers.users.send_password_reset_email", new_callable=AsyncMock) as mock_send_email:
        response = await client.post(
            "/api/users/forgot-password",
            json={"email": user["email"]}, # test@example.com
        )
        assert response.status_code == 202
        data = response.json()
        assert data["message"] == "If an account exists with this email, you will receive password reset instructions."

        mock_send_email.assert_awaited_once()
        args, kwargs = mock_send_email.call_args
        assert "to_email" in kwargs
        assert kwargs["to_email"] == user["email"]
        assert kwargs["username"] == user["username"]
        assert "token" in kwargs


@pytest.mark.anyio
async def test_update_username(client: AsyncClient):
    user = await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token)

    response = await client.patch(
        f"/api/users/{user['id']}",
        json={"username": "updatedusername"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "updatedusername"


@pytest.mark.anyio
async def test_update_email(client: AsyncClient):
    user = await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token)

    response = await client.patch(
        f"/api/users/{user['id']}",
        json={"email": "newtest@example.com"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "newtest@example.com"