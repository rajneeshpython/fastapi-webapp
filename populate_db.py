import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import delete, select, update

import models
from config import settings
from database import AsyncSessionLocal, engine
from image_utils import _get_s3_client
from main import app

POPULATE_IMAGES_DIR = Path("populate_images")

USERS = [
    {"username": "RajneeshKumar", "email": "rajneesh.kumar@gmail.com", "password": "Test@123", "image": "user_1.png"},
    {"username": "NitishVerma", "email": "nitish.verma@gmail.com", "password": "Test@123", "image": "user_2.png"},
    {"username": "PriyaSharma", "email": "priya.sharma@gmail.com", "password": "Test@123", "image": "user_3.jpg"},
    {"username": "AmitSingh", "email": "amit.singh@gmail.com", "password": "Test@123", "image": "user_4.jpg"},
    {"username": "SnehaPatel", "email": "sneha.patel@gmail.com", "password": "Test@123", "image": "user_5.png"},
    {"username": "VikashGupta", "email": "vikash.gupta@gmail.com", "password": "Test@123", "image": "user_6.jpg"},
    {"username": "RohitVerma", "email": "rohit.verma@gmail.com", "password": "Test@123", "image": "user_7.jpg"},
]

POST_TITLES = [
    "Getting Started with FastAPI",
    "Why Async Python Matters",
    "PostgreSQL Tips for Developers",
    "Building APIs with Clean Architecture",
    "JWT Authentication Best Practices",
    "Docker for Python Developers",
    "Redis Caching Strategies",
    "Understanding SQLAlchemy 2.0",
    "How to Scale FastAPI",
    "Background Jobs with Celery",
    "API Pagination Done Right",
    "Monitoring APIs with Prometheus",
    "Deploying FastAPI on AWS",
    "Rate Limiting in APIs",
    "WebSockets in FastAPI",
    "Testing APIs Properly",
    "Dependency Injection Explained",
    "Pydantic is Powerful",
    "Writing Better SQL Queries",
    "Handling Errors Gracefully",
]

POST_CONTENTS = [
    "FastAPI makes backend development simple, fast, and maintainable. Type hints, validation, and automatic docs improve developer productivity significantly.",
    "Async programming allows APIs to handle thousands of concurrent requests efficiently. It is especially useful for IO-heavy applications.",
    "PostgreSQL remains one of the best databases for modern backend systems due to reliability, indexing, and rich SQL support.",
    "Docker removes environment inconsistency and makes deployments predictable across local, staging, and production.",
    "Caching frequently accessed resources with Redis dramatically improves latency and reduces database load.",
    "Clean architecture keeps business logic independent from frameworks and databases, making systems easier to maintain.",
    "Monitoring is not optional in production. Logs, metrics, tracing, and alerts are essential for stable systems.",
    "Authentication should be secure but also simple for developers. JWT works great when implemented properly.",
    "Good API design means predictable endpoints, consistent responses, and strong validation.",
    "Writing tests early saves debugging time later and improves confidence during deployments.",
]

POSTS = [
    {
        "title": POST_TITLES[i % len(POST_TITLES)],
        "content": POST_CONTENTS[i % len(POST_CONTENTS)],
    }
    for i in range(100)
]

POST_44 = {
    "title": "Fun Fact: My First Production Bug Was on a Friday Night",
    "content": (
        "Every developer remembers that one production bug. "
        "Mine happened late Friday evening and taught me the importance "
        "of logs, alerts, and rollback plans."
    ),
}


async def clear_existing_data() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(models.User.image_file).where(models.User.image_file.is_not(None)),
        )
        filenames = result.scalars().all()

    if filenames:
        s3 = _get_s3_client()
        s3.delete_objects(
            Bucket=settings.s3_bucket_name,
            Delete={"Objects": [{"Key": f"profile_pics/{f}"} for f in filenames]},
        )
        print(f"Deleted {len(filenames)} images from S3")

    async with AsyncSessionLocal() as db:
        await db.execute(delete(models.PasswordResetToken))
        await db.execute(delete(models.Post))
        await db.execute(delete(models.User))
        await db.commit()
    print("Cleared existing data")


async def update_post_dates() -> None:
    now = datetime.now(UTC)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(models.Post).order_by(models.Post.id))
        posts = result.scalars().all()

        if not posts:
            return

        await db.execute(
            update(models.Post)
            .where(models.Post.id == posts[0].id)
            .values(date_posted=now - timedelta(days=90)),
        )

        for i, post in enumerate(posts[1:], start=1):
            days_ago = (len(posts) - i) * 1.5
            hours_offset = (i * 7) % 24
            post_date = now - timedelta(days=days_ago, hours=hours_offset)
            await db.execute(
                update(models.Post)
                .where(models.Post.id == post.id)
                .values(date_posted=post_date),
            )

        await db.commit()
    print("Updated post dates")


async def populate() -> None:
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        await clear_existing_data()

        users: list[dict] = []

        print(f"\nCreating {len(USERS)} users...")
        for user_data in USERS:
            response = await client.post(
                "/api/users",
                json={
                    "username": user_data["username"],
                    "email": user_data["email"],
                    "password": user_data["password"],
                },
            )
            response.raise_for_status()
            user = response.json()
            print(f"  Created: {user['username']}")

            response = await client.post(
                "/api/users/token",
                data={
                    "username": user_data["email"],
                    "password": user_data["password"],
                },
            )
            response.raise_for_status()
            token = response.json()["access_token"]

            if image_name := user_data.get("image"):
                image_path = POPULATE_IMAGES_DIR / image_name
                if image_path.exists():
                    content_type = (
                        "image/jpeg"
                        if image_name.lower().endswith((".jpg", ".jpeg"))
                        else "image/png"
                    )
                    response = await client.patch(
                        f"/api/users/{user['id']}/picture",
                        files={
                            "file": (
                                image_name,
                                image_path.read_bytes(),
                                content_type,
                            ),
                        },
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    response.raise_for_status()
                    print(f"    Uploaded: {image_name}")

            users.append({"id": user["id"], "username": user["username"], "token": token})

        print(f"\nCreating {len(POSTS) + 1} posts...")

        response = await client.post(
            "/api/posts",
            json={"title": POST_44["title"], "content": POST_44["content"]},
            headers={"Authorization": f"Bearer {users[0]['token']}"},
        )
        response.raise_for_status()
        print(f"  Created: '{POST_44['title']}'")

        for i, post_data in enumerate(reversed(POSTS)):
            user = users[i % len(users)]
            response = await client.post(
                "/api/posts",
                json={"title": post_data["title"], "content": post_data["content"]},
                headers={"Authorization": f"Bearer {user['token']}"},
            )
            response.raise_for_status()

        print("\nUpdating post dates...")
        await update_post_dates()

    await engine.dispose()

    print("\nDone!")
    print(f"  {len(USERS)} users")
    print(f"  {len(POSTS) + 1} posts")
    print("  Profile pictures uploaded to S3")


if __name__ == "__main__":
    asyncio.run(populate())