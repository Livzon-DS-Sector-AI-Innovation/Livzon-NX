from __future__ import annotations

from app.modules.quality.service.inspection_helpers import _smart_normalize_value


def test_attachment_list_keeps_clickable_structure() -> None:
    result = _smart_normalize_value(
        [
            {
                "file_token": "tok_1",
                "name": "报告.pdf",
                "url": "https://x/r.pdf",
                "type": "pdf",
                "size": 1024,
            },
            {"file_token": "tok_2", "name": "图谱.jpg", "tmp_url": "https://x/t.jpg"},
        ]
    )
    assert result[0] == {
        "name": "报告.pdf",
        "url": "https://x/r.pdf",
        "file_token": "tok_1",
        "type": "pdf",
        "size": 1024,
    }
    assert result[1]["url"] == "https://x/t.jpg"
    assert result[1]["file_token"] == "tok_2"


def test_url_field_keeps_link_object() -> None:
    result = _smart_normalize_value(
        {"link": "https://example.com", "text": "查看报告", "type": "url"}
    )
    assert result == {"link": "https://example.com", "text": "查看报告"}


def test_person_list_keeps_name_and_avatar() -> None:
    result = _smart_normalize_value(
        [
            {"id": "ou_1", "name": "张三", "avatar_url": "https://x/a.png"},
            {"id": "ou_2", "en_name": "Li"},
        ]
    )
    assert result[0]["name"] == "张三"
    assert result[0]["avatar_url"] == "https://x/a.png"
    assert result[1]["name"] == "Li"


def test_plain_values_still_normalize_to_text() -> None:
    assert _smart_normalize_value("葡萄糖") == "葡萄糖"
    assert _smart_normalize_value(3.5) == "3.5"
    assert _smart_normalize_value(None) is None
    assert _smart_normalize_value(["甲", "乙"]) == "甲 / 乙"
