"""步骤2：工程计算与放大评估（规则计算）"""

import logging
import math

from app.modules.research.models import PilotWorkflow

logger = logging.getLogger(__name__)

# 常见设备类型的几何参数
EQUIPMENT_PROFILES = {
    "反应釜": {"h_d_ratio": 1.2, "agitator_type": "锚式", "heat_transfer_coeff": 300},
    "结晶釜": {"h_d_ratio": 1.5, "agitator_type": "桨式", "heat_transfer_coeff": 250},
    "高压釜": {"h_d_ratio": 1.0, "agitator_type": "涡轮式", "heat_transfer_coeff": 350},
    "默认": {"h_d_ratio": 1.2, "agitator_type": "锚式", "heat_transfer_coeff": 280},
}


def _calc_geometry(volume_l: float, h_d_ratio: float) -> dict:
    """计算设备几何参数"""
    volume_m3 = volume_l / 1000.0
    # V = π/4 * D^2 * (H_D_ratio * D) = π/4 * H_D_ratio * D^3
    diameter_m = (4.0 * volume_m3 / (math.pi * h_d_ratio)) ** (1.0 / 3.0)
    height_m = diameter_m * h_d_ratio
    # 换热面积（筒体侧面积，忽略底部）
    heat_area_m2 = math.pi * diameter_m * height_m
    # 体积/面积比
    volume_area_ratio = volume_m3 / heat_area_m2 if heat_area_m2 > 0 else float("inf")
    return {
        "volume_m3": round(volume_m3, 3),
        "diameter_m": round(diameter_m, 3),
        "height_m": round(height_m, 3),
        "heat_area_m2": round(heat_area_m2, 3),
        "volume_area_ratio_m": round(volume_area_ratio, 3),
    }


def _assess_heat_transfer(
    scale_up_ratio: float,
    lab_volume_l: float,
    pilot_volume_l: float,
    heat_transfer_coeff: float,
) -> dict:
    """评估传热能力变化"""
    # 小试设备（假设 H/D = 1.0）
    lab_geo = _calc_geometry(lab_volume_l, 1.0)
    pilot_geo = _calc_geometry(pilot_volume_l, 1.2)

    # 面积/体积比变化
    lab_ratio = lab_geo["volume_area_ratio_m"]
    pilot_ratio = pilot_geo["volume_area_ratio_m"]
    ratio_change = pilot_ratio / lab_ratio if lab_ratio > 0 else 1.0

    # 评估结论
    if ratio_change > 2.0:
        level = "高风险"
        detail = "体积/面积比显著增大，散热能力严重不足，需考虑外部冷却或分段加料"
    elif ratio_change > 1.5:
        level = "中风险"
        detail = "散热能力有所下降，建议控制加料速度并监控温度"
    else:
        level = "低风险"
        detail = "散热能力变化不大，正常操作即可"

    return {
        "lab_geometry": lab_geo,
        "pilot_geometry": pilot_geo,
        "volume_area_ratio_change": round(ratio_change, 2),
        "heat_transfer_coeff_w_m2k": heat_transfer_coeff,
        "risk_level": level,
        "detail": detail,
    }


def _assess_mixing(
    scale_up_ratio: float,
    pilot_volume_l: float,
    agitator_type: str,
) -> dict:
    """评估混合效果"""
    # 简化搅拌功率估算（按体积放大）
    # 经验法则：P/V ∝ N^3 * D^2，恒 P/V 时 N ∝ D^(-2/3)

    # 估算搅拌转速（基于经验值）
    agitator_speeds = {
        "锚式": {"lab_rpm": 60, "scale_exp": -0.67},
        "桨式": {"lab_rpm": 80, "scale_exp": -0.67},
        "涡轮式": {"lab_rpm": 120, "scale_exp": -0.67},
    }
    params = agitator_speeds.get(agitator_type, agitator_speeds["锚式"])

    # 放大后转速
    pilot_rpm = params["lab_rpm"] * (scale_up_ratio ** params["scale_exp"])

    # 混合时间估算（经验公式）
    mixing_time_s = 60.0 / max(pilot_rpm, 1.0) * 10  # 简化估算

    if mixing_time_s > 120:
        level = "中风险"
        detail = f"预计混合时间较长({mixing_time_s:.0f}s)，可能影响反应均匀性"
    elif mixing_time_s > 60:
        level = "低风险"
        detail = f"预计混合时间{mixing_time_s:.0f}s，在可接受范围"
    else:
        level = "低风险"
        detail = f"预计混合时间{mixing_time_s:.0f}s，混合效果良好"

    return {
        "agitator_type": agitator_type,
        "estimated_pilot_rpm": round(pilot_rpm, 1),
        "estimated_mixing_time_s": round(mixing_time_s, 1),
        "risk_level": level,
        "detail": detail,
    }


def _assess_equipment_fit(
    pilot_volume_l: float,
    equipment_type: str,
) -> dict:
    """评估设备适配性"""
    profile = EQUIPMENT_PROFILES.get(equipment_type, EQUIPMENT_PROFILES["默认"])
    geo = _calc_geometry(pilot_volume_l, profile["h_d_ratio"])

    # 容积填充率（假设70%为最佳）
    fill_rate = 0.7
    working_volume_l = pilot_volume_l * fill_rate

    # 高径比评估
    h_d_ratio = profile["h_d_ratio"]
    if h_d_ratio > 2.0:
        fit_level = "需注意"
        fit_detail = f"高径比{h_d_ratio}较大，液柱静压可能影响底部反应"
    elif h_d_ratio < 0.8:
        fit_level = "需注意"
        fit_detail = f"高径比{h_d_ratio}较小，设备偏矮胖，混合可能不均匀"
    else:
        fit_level = "合适"
        fit_detail = f"高径比{h_d_ratio}在常规范围"

    return {
        "equipment_type": equipment_type,
        "total_volume_l": pilot_volume_l,
        "working_volume_l": round(working_volume_l, 1),
        "fill_rate": fill_rate,
        "geometry": geo,
        "h_d_ratio": h_d_ratio,
        "fit_level": fit_level,
        "detail": fit_detail,
    }


async def execute_scale_up_calc(
    step_input: dict,
    workflow: PilotWorkflow,
) -> dict:
    """执行工程计算与放大评估"""
    scale_up_ratio = workflow.scale_up_ratio
    equipment_type = workflow.equipment_type
    pilot_volume = workflow.equipment_volume

    # 推算小试批量
    lab_volume = pilot_volume / scale_up_ratio if scale_up_ratio > 0 else pilot_volume

    profile = EQUIPMENT_PROFILES.get(equipment_type, EQUIPMENT_PROFILES["默认"])

    # 传热评估
    heat_assessment = _assess_heat_transfer(
        scale_up_ratio=scale_up_ratio,
        lab_volume_l=lab_volume,
        pilot_volume_l=pilot_volume,
        heat_transfer_coeff=profile["heat_transfer_coeff"],
    )

    # 混合评估
    mixing_assessment = _assess_mixing(
        scale_up_ratio=scale_up_ratio,
        pilot_volume_l=pilot_volume,
        agitator_type=profile["agitator_type"],
    )

    # 设备适配性评估
    equipment_fit = _assess_equipment_fit(
        pilot_volume_l=pilot_volume,
        equipment_type=equipment_type,
    )

    # 综合风险判断
    risk_levels = [
        heat_assessment["risk_level"],
        mixing_assessment["risk_level"],
        equipment_fit["fit_level"],
    ]
    if "高风险" in risk_levels or "需注意" in risk_levels:
        overall_risk = "中"
    elif "中风险" in risk_levels:
        overall_risk = "中"
    else:
        overall_risk = "低"

    return {
        "step": "scale_up_calc",
        "scale_up_ratio": scale_up_ratio,
        "lab_volume_l": round(lab_volume, 2),
        "pilot_volume_l": pilot_volume,
        "heat_transfer": heat_assessment,
        "mixing": mixing_assessment,
        "equipment_fit": equipment_fit,
        "overall_risk": overall_risk,
    }
