"""MC 飞书同步列位对齐回归（production 模块门禁同名测试）。

2026-10 起源表在粗提块前新增"钠化滤液对发酵液总收率"列，粗品块整体右移一列；
提取表在折干产量后新增"产品量"列，收率/母液块整体右移一列。
本文件锁定新列位，防止后续源表加列再次静默错位。
"""

from types import SimpleNamespace

from app.modules.production import mc_feishu_sheets_sync as sync


def _row(*values: object, length: int = 36) -> list[str]:
    cells = [""] * length
    for idx, value in enumerate(values[:length]):
        if value is not None:
            cells[idx] = str(value)
    return cells


def test_apply_st_fields_reads_crude_block_from_ab() -> None:
    """粗提块自 AB(27) 列起：重量/袋种/含量/水分/产品量/收率/累积/累计收率/备注。"""
    st = SimpleNamespace()
    row = _row(
        "2026-11-01",  # A 日期
        "FL-1",  # B 发酵液批号
        "RB-1",  # C 提炼生产批号
        "40.2",  # D 体积 KL
        "13752",  # E 效价
        "552.8304",  # F 核对产品量
        "2389.33",  # G 总产量
        "67021.3",  # H 累计放罐产品量
        *([""] * 18),  # I..Z 钠化/酸化块（本测试不覆盖）
        "99.5",  # AA 钠化滤液对发酵液总收率（新增列，不读入粗品重量）
        "1874",  # AB 粗品重量
        "30",  # AC 袋种KG
        "89.07",  # AD 含量
        "17.4",  # AE 水分
        "1378.7359068",  # AF 产品量(kg)
        "1.00163894904712",  # AG 收率≥92%（比例，>1 也要×100）
        "1001.6",  # AH 累积粗品产品量
        "0.971016430579944",  # AI 粗品累计收率
        "备注X",  # AJ 备注
    )
    sync._apply_st_fields(st, row, tank_no=1, pending_st2_data={})

    assert st.fl_volume == 40.2
    assert st.fl_potency == 13752.0
    assert st.fl_product_qty == 552.8304
    assert st.total_input == 2389.33
    assert st.cumulative_qty == 67021.3
    assert st.crude_weight == 1874.0
    assert st.bag_weight == 30.0
    assert st.crude_content == 89.07
    assert st.crude_moisture == 17.4
    assert st.crude_product_qty == 1378.7359068
    assert st.yield_rate == 100.16  # 1.0016 比例×100
    assert st.cumulative_crude_qty == 1001.6
    assert st.cumulative_crude_yield == 97.1  # 0.971 比例×100
    assert st.remarks == "备注X"


def test_apply_st_fields_resync_refreshes_existing_values() -> None:
    """重同步刷新：已有行以源表为准覆盖——非空覆盖旧值，源表空值清空字段。"""
    st = SimpleNamespace(
        crude_weight=999.0,
        bag_weight=999.0,
        crude_content=999.0,
        crude_moisture=999.0,
        crude_product_qty=999.0,
        yield_rate=999.0,
        cumulative_crude_qty=999.0,
        cumulative_crude_yield=999.0,
        remarks="旧备注",
    )
    row = _row(
        "2026-11-02",
        "FL-2",
        "RB-2",
        *([""] * 24),  # D..Z 置空（3+24=27，下一值落 AB）
        "1500",  # AB 粗品重量
        "30",  # AC 袋种
        "89.07",  # AD 含量
        "",  # AE 水分留空 → 按源表清空
        "",  # AF 产品量留空 → 按源表清空
        "97.1",  # AG 收率（已填百分数 ≥3，不放大）
        "",  # AH 留空 → 清空
        "",  # AI 留空 → 清空
        "新备注",  # AJ 备注
    )
    sync._apply_st_fields(st, row, tank_no=1, pending_st2_data={})

    assert st.crude_weight == 1500.0
    assert st.bag_weight == 30.0
    assert st.crude_content == 89.07
    assert st.crude_moisture is None  # 源表空值清空旧值（含历史错位残留）
    assert st.crude_product_qty is None
    assert st.yield_rate == 97.1  # ≥3 视为已填百分数
    assert st.cumulative_crude_qty is None
    assert st.cumulative_crude_yield is None
    assert st.remarks == "新备注"


def test_apply_st_fields_fl_pending_overrides_tank2() -> None:
    """子罐2 使用暂存的发酵液 D/E/F 数据覆盖本行。"""
    st = SimpleNamespace()
    row = _row("2026-11-03", "FL-3", "RB-3", "10", "20", "30")
    pending = {"volume": 47.0, "potency": 175.0, "pq": 135.0}
    sync._apply_st_fields(st, row, tank_no=2, pending_st2_data=pending)

    assert st.fl_volume == 47.0
    assert st.fl_potency == 175.0
    assert st.fl_product_qty == 135.0
