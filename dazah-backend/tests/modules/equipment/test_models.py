"""Tests for equipment ORM models."""

from datetime import date
from typing import Any

from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from app.modules.equipment.models import (
    Equipment,
    EquipmentCategory,
    EquipmentCategoryLink,
    Location,
)


class TestEquipmentCategoryModel:
    """Tests for EquipmentCategory model."""

    def test_instantiation(self: Any) -> None:
        """Model can be instantiated with required fields."""
        cat = EquipmentCategory(
            name="反应釜",
            code="REACTOR",
        )
        assert cat.name == "反应釜"
        assert cat.code == "REACTOR"
        assert cat.parent_id is None
        assert cat.description is None

    def test_instantiation_with_optional_fields(self: Any) -> None:
        """Model accepts optional fields."""
        cat = EquipmentCategory(
            name="反应釜",
            code="REACTOR",
            description="用于化学反应的设备",
        )
        assert cat.description == "用于化学反应的设备"

    def test_parent_child_linking(self: Any) -> None:
        """Parent and child categories can be linked via relationship attributes."""
        parent = EquipmentCategory(name="通用设备", code="GENERAL")
        child = EquipmentCategory(name="反应釜", code="REACTOR")

        child.parent = parent
        assert child.parent is parent
        assert child in parent.children

    def test_code_uses_partial_unique_index(self: Any) -> None:
        """Only active category codes are unique."""
        index = next(
            c
            for c in EquipmentCategory.__table_args__
            if isinstance(c, Index) and c.name == "uq_equipment_categories_code"
        )
        assert index.unique is True
        assert {col.name for col in index.columns} == {"code"}
        assert "is_deleted = false" in str(index.dialect_options["postgresql"]["where"])

    def test_schema_is_equipment(self: Any) -> None:
        """Table belongs to the equipment schema."""
        assert EquipmentCategory.__table_args__[-1]["schema"] == "equipment"


class TestLocationModel:
    """Tests for Location model."""

    def test_instantiation(self: Any) -> None:
        """Model can be instantiated with required fields."""
        loc = Location(name="一号车间", code="WORKSHOP-01")
        assert loc.name == "一号车间"
        assert loc.code == "WORKSHOP-01"
        assert loc.parent_id is None

    def test_parent_child_linking(self: Any) -> None:
        """Parent and child locations can be linked via relationship attributes."""
        parent = Location(name="工厂", code="FACTORY")
        child = Location(name="一号车间", code="WORKSHOP-01")

        child.parent = parent
        assert child.parent is parent
        assert child in parent.children

    def test_code_uses_partial_unique_index(self: Any) -> None:
        """Only active location codes are unique."""
        index = next(
            c
            for c in Location.__table_args__
            if isinstance(c, Index) and c.name == "uq_locations_code"
        )
        assert index.unique is True
        assert {col.name for col in index.columns} == {"code"}
        assert "is_deleted = false" in str(index.dialect_options["postgresql"]["where"])


class TestEquipmentModel:
    """Tests for Equipment model."""

    def _make_category(self: Any) -> EquipmentCategory:
        return EquipmentCategory(name="反应釜", code="REACTOR")

    def _make_location(self: Any) -> Location:
        return Location(name="一号车间", code="WORKSHOP-01")

    def test_instantiation(self: Any) -> None:
        """Model can be instantiated with required fields."""
        loc = self._make_location()
        equip = Equipment(
            equipment_no="EQ-001",
            name="500L反应釜",
            location_id=loc.id,
            status="在用",
        )
        assert equip.equipment_no == "EQ-001"
        assert equip.name == "500L反应釜"
        assert equip.status == "在用"

    def test_date_fields_accept_date_objects(self: Any) -> None:
        """production_date and commissioning_date accept datetime.date values."""
        loc = self._make_location()
        equip = Equipment(
            equipment_no="EQ-002",
            name="干燥机",
            location_id=loc.id,
            production_date=date(2024, 1, 15),
            commissioning_date=date(2024, 3, 1),
        )
        assert equip.production_date == date(2024, 1, 15)
        assert equip.commissioning_date == date(2024, 3, 1)

    def test_date_fields_accept_none(self: Any) -> None:
        """production_date and commissioning_date default to None."""
        loc = self._make_location()
        equip = Equipment(
            equipment_no="EQ-003",
            name="离心机",
            location_id=loc.id,
        )
        assert equip.production_date is None
        assert equip.commissioning_date is None

    def test_unique_constraint_includes_is_deleted(self: Any) -> None:
        """Unique constraint on equipment_no includes is_deleted column."""
        constraint = next(
            c
            for c in Equipment.__table_args__
            if isinstance(c, UniqueConstraint)
            and c.name == "uq_equipments_equipment_no"
        )
        col_names = {col.name for col in constraint.columns}
        assert "equipment_no" in col_names
        assert "is_deleted" in col_names

    def test_status_check_constraint_exists(self: Any) -> None:
        """CheckConstraint validates status values."""
        constraint = next(
            c
            for c in Equipment.__table_args__
            if isinstance(c, CheckConstraint) and c.name == "ck_equipments_status"
        )
        assert "在用" in constraint.sqltext.text
        assert "备用" in constraint.sqltext.text
        assert "维修中" in constraint.sqltext.text
        assert "停用" in constraint.sqltext.text
        assert "报废" in constraint.sqltext.text

    def test_relationships(self: Any) -> None:
        """Equipment has category-link and location relationships."""
        cat = self._make_category()
        loc = self._make_location()
        equip = Equipment(
            equipment_no="EQ-004",
            name="离心机",
            location_id=loc.id,
        )
        equip.category_links = [EquipmentCategoryLink(category=cat)]
        equip.location = loc
        assert equip.category_links[0].category is cat
        assert equip.location is loc

    def test_optional_fields_default_to_none(self: Any) -> None:
        """Optional fields default to None when not provided."""
        loc = self._make_location()
        equip = Equipment(
            equipment_no="EQ-005",
            name="测试设备",
            location_id=loc.id,
        )
        assert equip.model is None
        assert equip.specification is None
        assert equip.manufacturer is None
        assert equip.supplier is None
        assert equip.description is None
        assert equip.warranty_expire_date is None
        assert equip.asset_value is None
        assert equip.depreciation_years is None
        assert equip.technical_params is None

    def test_new_fields_default_to_none(self: Any) -> None:
        """新字段默认为 None"""
        loc = self._make_location()
        equip = Equipment(
            equipment_no="EQ-NEW-001",
            name="测试设备",
            location_id=loc.id,
        )
        assert equip.warranty_expire_date is None
        assert equip.asset_value is None
        assert equip.depreciation_years is None
        assert equip.technical_params is None

    def test_new_fields_accept_values(self: Any) -> None:
        """新字段可以赋值"""
        loc = self._make_location()
        equip = Equipment(
            equipment_no="EQ-NEW-002",
            name="测试设备",
            location_id=loc.id,
            warranty_expire_date=date(2027, 12, 31),
            asset_value=150000.00,
            depreciation_years=10,
            technical_params={"power": "380V", "capacity": "500L"},
        )
        assert equip.warranty_expire_date == date(2027, 12, 31)
        assert equip.asset_value == 150000.00
        assert equip.depreciation_years == 10
        assert equip.technical_params == {"power": "380V", "capacity": "500L"}
