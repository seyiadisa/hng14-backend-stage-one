import asyncio
from datetime import datetime
from uuid import UUID

from fastapi import Response
from starlette.requests import Request

from app.api.routes import profile as profile_routes
from app.schemas.profile import ProfileCreate


class FakeExistingProfileResult:
    def scalar_one_or_none(self):
        return None


class FakeCreateProfileDB:
    def __init__(self):
        self.added_profile = None
        self.committed = False

    async def execute(self, statement):
        return FakeExistingProfileResult()

    def add(self, profile):
        self.added_profile = profile

    async def commit(self):
        self.committed = True

    async def refresh(self, profile):
        profile.id = UUID("018f978a-6ee5-7d52-b2cb-0123456789ab")
        profile.created_at = datetime(2026, 4, 29, 10, 30, 0)


def test_create_profile_sets_country_name(monkeypatch):
    async def fake_fetch_json(client, url, name, api_name):
        payloads = {
            "Genderize": {"gender": "female", "count": 10, "probability": 0.98},
            "Agify": {"age": 31},
            "Nationalize": {
                "country": [{"country_id": "NG", "probability": 0.76}]
            },
        }
        return payloads[api_name]

    async def scenario():
        db = FakeCreateProfileDB()
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/profiles",
                "headers": [],
                "client": ("testclient", 50000),
            }
        )

        response = await profile_routes.create_profile(
            request=request,
            response=Response(),
            payload=ProfileCreate(name="Ada"),
            db=db,
        )

        assert db.committed is True
        assert db.added_profile.country_name == "Nigeria"
        assert response["data"]["country_name"] == "Nigeria"

    monkeypatch.setattr(profile_routes, "fetch_json", fake_fetch_json)
    asyncio.run(scenario())
