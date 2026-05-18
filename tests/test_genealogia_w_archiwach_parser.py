"""Offline parser tests for Genealogia w Archiwach UIDL payloads."""

from __future__ import annotations

import json

from genealogy_mcp.sources.genealogia_w_archiwach.parser import (
    extract_urls,
    image_urls,
    parse_records,
    parse_uidl_text,
)


def test_parse_uidl_text_strips_vaadin_prefix():
    messages = parse_uidl_text('for(;;);[{"syncId":1,"changes":[]}]')

    assert messages == [{"syncId": 1, "changes": []}]


def test_extract_urls_normalizes_relative_and_detects_images():
    payload = {
        "href": "/archiwum-front/skan?unit=123",
        "iiif": "https://www.genealogiawarchiwach.pl/iiif/abc/info.json",
        "thumb": "/images/thumb.jpg",
        "icon": "fonticon://FontAwesome/f15b",
        "html": "<span>Stanisław</span><div>Mańkowski</div>",
    }

    urls = extract_urls(payload)

    assert "https://www.genealogiawarchiwach.pl/archiwum-front/skan?unit=123" in urls
    assert "https://www.genealogiawarchiwach.pl/images/thumb.jpg" in urls
    assert "https://www.genealogiawarchiwach.pl/iiif/abc/info.json" in image_urls(urls)
    assert "https://www.genealogiawarchiwach.pl/images/thumb.jpg" in image_urls(urls)
    assert "https://www.genealogiawarchiwach.pl//FontAwesome/f15b" not in urls
    assert "https://www.genealogiawarchiwach.pl/span" not in urls
    assert "https://www.genealogiawarchiwach.pl/div" not in urls


def test_parse_records_extracts_result_text_urls_and_images():
    message = {
        "typeMappings": {
            "pl.bos.archiwum.front.view.search.result.PersonSearchResult": 14,
            "com.vaadin.ui.MenuBar": 12,
        },
        "hierarchy": {"100": ["101"]},
        "changes": [
            ["change", {"pid": "100"}, ["14", {"id": "100"}]],
            [
                "change",
                {"pid": "101"},
                [
                    "12",
                    {"id": "101"},
                    [
                        "items",
                        {},
                        [
                            "item",
                            {
                                "description": "Stanisław Mańkowski 1893 Toruń",
                                "url": "/record/123",
                                "thumb": "/iiif/scan-123/info.json",
                            },
                        ],
                    ],
                ],
            ],
        ],
    }

    records = parse_records([message])

    assert len(records) == 1
    assert records[0].description == "Stanisław Mańkowski 1893 Toruń"
    assert records[0].year == 1893
    assert records[0].source_url == "https://www.genealogiawarchiwach.pl/record/123"
    assert records[0].image_urls == ["https://www.genealogiawarchiwach.pl/iiif/scan-123/info.json"]


def test_parse_records_reads_vaadin_state_without_duplicate_details():
    message = {
        "typeMappings": {
            "pl.bos.archiwum.front.view.search.result.ScanSearchResult": 21,
            "pl.bos.archiwum.front.view.search.result.ScanSearchResultDetails": 22,
            "com.vaadin.ui.Label": 12,
        },
        "hierarchy": {
            "100": ["101", "102"],
            "101": ["103"],
            "102": ["104", "105", "106", "107"],
        },
        "changes": [
            ["change", {"pid": "100"}, ["21", {"id": "100"}]],
            ["change", {"pid": "102"}, ["22", {"id": "102"}]],
            ["change", {"pid": "103"}, ["12", {"id": "103"}]],
            ["change", {"pid": "104"}, ["12", {"id": "104"}]],
            ["change", {"pid": "105"}, ["12", {"id": "105"}]],
            ["change", {"pid": "106"}, ["12", {"id": "106"}]],
            ["change", {"pid": "107"}, ["12", {"id": "107"}]],
        ],
        "state": {
            "100": {"childLocations": {"101": "document_name", "102": "document_more"}},
            "103": {"description": "71/229/0/77 (19)"},
            "104": {
                "text": '<div class="fat-container"><div class="fat">miejscowość</div><div class="fat-value"> Połajewo</div></div>'
            },
            "105": {
                "text": '<div class="fat-container"><div class="fat">data</div><div class="fat-value"> 1903</div></div>'
            },
            "106": {
                "text": '<div class="fat-container"><div class="fat">jednostka archiwalna</div><div class="fat-value"> 71/229/0/77</div></div>'
            },
            "107": {
                "text": '<div class="fat-container"><div class="fat">sygnatura</div><div class="fat-value"> 77</div></div>'
            },
        },
    }

    records = parse_records([message])

    assert len(records) == 1
    assert records[0].description == "71/229/0/77 (19)"
    assert records[0].place == "Połajewo"
    assert records[0].year == 1903
    assert records[0].identifiers["jednostka archiwalna"] == "71/229/0/77"
    assert records[0].identifiers["sygnatura"] == "77"
