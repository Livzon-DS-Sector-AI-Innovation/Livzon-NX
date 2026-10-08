"""变更控制 change_object 放宽为 TEXT 后的模型契约与导入行为。"""

from app.modules.quality.models.change_control import ChangeControl


def test_change_object_column_is_text_after_widen() -> None:
    """change_object 与 change_content 同为 TEXT，长变更对象不再被 VARCHAR(255) 截断。"""
    col = ChangeControl.__table__.columns["change_object"]
    assert col.type.__class__.__name__ == "Text"
    assert col.nullable is True
