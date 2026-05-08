"""Offline tests for the authenticated GenPod GraphQL client."""

from __future__ import annotations

import json
from urllib.parse import parse_qs

import httpx
import pytest

from polish_genealogy_mcp.sources.genpod.client import (
    GenpodAuthenticationError,
    GenpodClient,
    GenpodConfig,
)

AUTHENTICATED_HTML = """
<html><body><script>
window.reactContext = {"user":{"username":"tester"},"graphQLEndpoint":"/graphql"};
</script></body></html>
"""


def test_missing_credentials_raise_before_network():
    client = GenpodClient(GenpodConfig(username=None, password=None, min_interval_seconds=0))

    with pytest.raises(GenpodAuthenticationError):
        client.list_parishes()


def test_search_logs_in_and_posts_graphql_variables():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path == "/login":
            return httpx.Response(200, text="<html>login</html>")
        if request.method == "POST" and request.url.path == "/login":
            form = parse_qs(request.content.decode())
            assert form["username"] == ["user"]
            assert form["password"] == ["pass"]
            return httpx.Response(200, text=AUTHENTICATED_HTML)
        if request.method == "POST" and request.url.path == "/graphql":
            body = json.loads(request.content)
            assert body["operationName"] == "SearchVitalRecords"
            variables = body["variables"]
            assert variables["commonFilters"] == {
                "lastNameFragment": "Kowalski",
                "lastNameExact": False,
                "yearFromInclusive": 1880,
                "yearToInclusive": 1890,
                "secondPersonLastNameExact": False,
            }
            assert variables["sliceUrodzenia"]["page"] == 2
            assert variables["sliceUrodzenia"]["pageSize"] == 10
            assert variables["sliceMalzenstwa"]["pageSize"] == 1
            assert variables["sliceZgony"]["pageSize"] == 1
            return httpx.Response(
                200,
                json={
                    "data": {
                        "urodzenia": {
                            "totalResultCount": 1,
                            "pageSize": 10,
                            "didNotProvideLastNameFragment": False,
                            "results": [{"rok": 1888, "nazwisko_wsp": "Kowalski"}],
                        },
                        "malzenstwa": {
                            "totalResultCount": 0,
                            "pageSize": 1,
                            "didNotProvideLastNameFragment": False,
                            "results": [],
                        },
                        "zgony": {
                            "totalResultCount": 0,
                            "pageSize": 1,
                            "didNotProvideLastNameFragment": False,
                            "results": [],
                        },
                    }
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = GenpodClient(
        GenpodConfig(username="user", password="pass", min_interval_seconds=0),
        transport=httpx.MockTransport(handler),
    )

    data = client.search_vital_records(
        last_name="Kowalski",
        year_from=1880,
        year_to=1890,
        record_types=["birth"],
        limit=10,
        page=2,
    )

    assert data["urodzenia"]["totalResultCount"] == 1
    assert data["malzenstwa"]["totalResultCount"] is None
    assert data["malzenstwa"]["results"] == []
    assert data["zgony"]["totalResultCount"] is None
    assert data["zgony"]["results"] == []
    assert [request.url.path for request in requests] == ["/login", "/login", "/graphql"]


def test_list_parishes_uses_authenticated_session_once():
    graphql_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal graphql_calls
        if request.url.path == "/login":
            return httpx.Response(200, text=AUTHENTICATED_HTML)
        if request.url.path == "/graphql":
            graphql_calls += 1
            return httpx.Response(
                200,
                json={
                    "data": {
                        "parafieIndexingSummary": [],
                        "parafieUpdateHistogram": {"buckets": []},
                    }
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = GenpodClient(
        GenpodConfig(username="user", password="pass", min_interval_seconds=0),
        transport=httpx.MockTransport(handler),
    )

    assert client.list_parishes()["parafieIndexingSummary"] == []
    assert client.list_parishes()["parafieIndexingSummary"] == []
    assert graphql_calls == 2
