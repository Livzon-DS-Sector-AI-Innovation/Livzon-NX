"""8 大特殊作业票票面模板（依据《新版作业票（2026.7.7更新）》docx）。

内容分为三层，全部为代码常量（可执行、可完善的默认口径，后续可加配置覆盖）：
- 票种与级别（编号前缀、级别枚举、气体复检配置）；
- 节点目录（与纸面签字行一一对应，kind 区分 审批/确认/验票/验收，
  ``levels`` 为激活该节点的作业级别集合，None = 全级别激活）；
- 安全措施清单原文（含填空项 fill_keys）与风险辨识选项。

审批逐级串行：按 seq 顺序流转；任一 approve 节点驳回 → 整票进入 rejected，
重新提交后按新 round 重走全链。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── 作业级别 ──

LEVEL_SPECIAL = "special"
LEVEL_GRADE1 = "grade1"
LEVEL_GRADE2 = "grade2"
LEVEL_GRADE3 = "grade3"
LEVEL_NONE = "none"

PERMIT_LEVEL_LABELS: dict[str, str] = {
    LEVEL_SPECIAL: "特级",
    LEVEL_GRADE1: "一级",
    LEVEL_GRADE2: "二级",
    LEVEL_GRADE3: "三级",
    LEVEL_NONE: "不分级别",
}


@dataclass(frozen=True)
class PermitTypeTemplate:
    """单个作业票种的静态模板。"""

    code: str
    name: str
    no_prefix: str
    levels: tuple[str, ...]
    nodes: tuple[dict[str, object], ...]
    person_roles: tuple[dict[str, object], ...]
    measures: tuple[dict[str, object], ...]
    type_fields: tuple[dict[str, object], ...] = field(default=())
    gas_enabled: bool = False
    gas_cycle_minutes: int | None = None
    gas_fields: tuple[str, ...] = field(default=())


# ── 风险辨识结果（8 票通用勾选，票面原文） ──

RISK_IDENTIFICATION_OPTIONS: tuple[str, ...] = (
    "物体打击",
    "厂(场)内车辆致害",
    "机械致害",
    "起重致害",
    "触电",
    "淹溺",
    "灼烫",
    "火灾",
    "高处坠落",
    "跌落",
    "坍塌",
    "水害",
    "容器爆炸",
    "管道爆炸",
    "可燃气体爆炸",
    "可燃液体蒸气爆炸",
    "粉尘爆炸",
    "其他可燃固体爆炸",
    "中毒",
    "窒息",
    "滑坡",
    "泄漏",
    "其他",
)

# ── 人员角色（persons JSONB 的 role 取值） ──

PERSON_ROLE_LABELS: dict[str, str] = {
    "work_leader": "作业负责人",
    "worker": "作业人",
    "guardian": "监护人",
    "briefer": "安全交底人",
    "briefer_receiver": "接受交底人",
    "process_tech": "工艺技术人员",
    "process_guardian": "工艺监护人",
    "rigger": "吊装作业人",
    "rigging_slacker": "司索人",
    "crane_commander": "指挥人员",
    "electricity_user": "用电人",
    "wiring_person": "接线人",
    "wiring_guardian": "接线监护人",
}

# 角色 → 建议证件类别（软校验：缺证/过期仅提示，强校验开关见 work_permit_settings）
PERSON_ROLE_CERT_CATEGORIES: dict[str, tuple[str, ...]] = {
    "worker": ("welding_cutting", "high_altitude_erecting"),
    "crane_commander": ("crane_commander",),
    "rigger": ("crane_operator",),
    "rigging_slacker": ("lifting_rigging",),
    "wiring_person": ("electrician",),
    "wiring_guardian": ("electrician",),
    "guardian": ("confined_space_guardian",),
}

# 天然多人员的角色（②步可多选；批准后交底签字推送对象）
MULTI_PERSON_ROLES: tuple[str, ...] = ("worker", "rigger", "rigging_slacker")

# 发起签字行（聊天流表单态签字，node_id 为空落库）
INITIATOR_SIGN_KEYS: tuple[str, ...] = ("initiator", "briefer", "briefer_receiver")


def is_multi_person_role(role_key: str) -> bool:
    return role_key in MULTI_PERSON_ROLES


def brief_worker_entries(
    persons: list[dict[str, object]] | None,
) -> list[tuple[int, dict[str, object]]]:
    """需交底签字的作业人条目 → [(序号, person)]，序号即签字行 brief_worker_{i}。

    按 persons 列表顺序对 multi 角色条目连续编号，作为签字行 key 的稳定标识。
    """
    entries: list[tuple[int, dict[str, object]]] = []
    index = 0
    for person in persons or []:
        if str(person.get("role")) in MULTI_PERSON_ROLES:
            entries.append((index, person))
            index += 1
    return entries


def brief_sign_key(index: int) -> str:
    return f"brief_worker_{index}"

# ── 证件类别字典（人员特殊作业证件管理） ──

CERTIFICATE_CATEGORIES: tuple[dict[str, str], ...] = (
    {"value": "electrician", "label": "电工作业"},
    {"value": "welding_cutting", "label": "焊接与热切割作业"},
    {"value": "high_altitude_erecting", "label": "登高架设作业"},
    {
        "value": "high_altitude_maintenance",
        "label": "高处安装、维护、拆除作业",
    },
    {"value": "refrigeration", "label": "制冷与空调作业"},
    {"value": "crane_commander", "label": "起重机械指挥"},
    {"value": "crane_operator", "label": "起重机司机"},
    {"value": "lifting_rigging", "label": "起重司索工"},
    {"value": "forklift", "label": "叉车作业"},
    {"value": "hazmat_safety_manager", "label": "危化品安全管理人员"},
    {"value": "confined_space_guardian", "label": "受限空间作业监护人"},
    {"value": "confined_space", "label": "受限空间作业"},
    {"value": "instrument", "label": "化工自动化控制仪表作业"},
    {"value": "boiler_operator", "label": "锅炉作业（司炉工）"},
    {"value": "pressure_vessel", "label": "压力容器作业"},
    {"value": "special_equipment_management", "label": "特种设备安全管理（A证）"},
    {"value": "water_quality_analyst", "label": "水质化验员"},
    {"value": "other", "label": "其他"},
)

CERTIFICATE_CATEGORY_LABELS: dict[str, str] = {
    item["value"]: item["label"] for item in CERTIFICATE_CATEGORIES
}

# 节点 kind
NODE_KIND_APPROVE = "approve"  # 逐级审批
NODE_KIND_CONFIRM = "confirm"  # 确认签字（前置确认，不构成审批链）
NODE_KIND_VERIFY = "verify"  # 作业前验票
NODE_KIND_ACCEPT = "accept"  # 完工验收

NODE_STATUS_WAITING = "waiting"
NODE_STATUS_PENDING = "pending"
NODE_STATUS_APPROVED = "approved"
NODE_STATUS_REJECTED = "rejected"
NODE_STATUS_SKIPPED = "skipped"

PERMIT_STATUS_DRAFT = "draft"
PERMIT_STATUS_PENDING = "pending_approval"
PERMIT_STATUS_APPROVED = "approved"
PERMIT_STATUS_ACTIVE = "active"
PERMIT_STATUS_COMPLETED = "completed"
PERMIT_STATUS_REJECTED = "rejected"
PERMIT_STATUS_CANCELLED = "cancelled"

PERMIT_STATUS_LABELS: dict[str, str] = {
    PERMIT_STATUS_DRAFT: "草稿",
    PERMIT_STATUS_PENDING: "审批中",
    PERMIT_STATUS_APPROVED: "已批准",
    PERMIT_STATUS_ACTIVE: "作业中",
    PERMIT_STATUS_COMPLETED: "已完工",
    PERMIT_STATUS_REJECTED: "已驳回",
    PERMIT_STATUS_CANCELLED: "已作废",
}


def _n(
    key: str,
    name: str,
    kind: str,
    levels: tuple[str, ...] | None = None,
) -> dict[str, object]:
    return {"key": key, "name": name, "kind": kind, "levels": levels}


def _m(
    key: str,
    text: str,
    *fill_keys: str,
    group: str | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {"key": key, "text": text}
    if group:
        item["group"] = group
    if fill_keys:
        item["fill_keys"] = list(fill_keys)
    return item


def _as_level_tuple(levels: object) -> tuple[str, ...]:
    if isinstance(levels, tuple):
        return levels
    return ()


# ── 安全措施填空项 key ──
# hot_work: removed_pipe_count / blind_count / extinguisher_count /
# blanket_count / hose_count

_HOT_WORK_MEASURES: tuple[dict[str, object], ...] = (
    _m(
        "hw_disconnect_pipes",
        "断开与动火设备相连接的所有管线：设备隔断（拆除管道）____处",
        "removed_pipe_count",
        group="工艺风险防范",
    ),
    _m(
        "hw_add_blind_plates",
        "与动火设备相连接的所有管线加盲板：加盲板___处",
        "blind_count",
        group="工艺风险防范",
    ),
    _m(
        "hw_clean_purge",
        (
            "动火设备和管道内部构件清理干净，蒸汽吹扫或水洗合格，"
            "环境清理置换，气体分析合格达到动火条件"
        ),
        group="工艺风险防范",
    ),
    _m(
        "hw_clear_flammables",
        (
            "动火点周围的场所、下水井、地漏、地沟、电缆沟等已清除易燃物，"
            "并已采取覆盖、铺沙、水封等手段进行隔离"
        ),
        group="工艺风险防范",
    ),
    _m(
        "hw_no_vertical_discharge",
        (
            "动火点30m内垂直空间未排放可燃气体；15m内垂直空间未排放可燃液体；"
            "10m范围内及动火点下方未同时进行可燃溶剂清洗或喷漆等作业，"
            "10m范围内未见有可燃性粉尘清扫作业"
        ),
        group="工艺风险防范",
    ),
    _m(
        "hw_no_hazard_ops_nearby",
        (
            "动火点周围规定15m距离内没有易燃易爆化学品的装卸、分水、投料、"
            "喷漆、取样等可能引起火灾爆炸的危险作业"
        ),
        group="工艺风险防范",
    ),
    _m(
        "hw_spark_protection_height",
        "高处作业已采用防火花飞溅措施，作业人员佩戴必要的个体防护装备",
        group="施工作业风险防范",
    ),
    _m(
        "hw_spark_block",
        "不涉及高处作业的，火花、焊渣接挡防止火花飞溅措施已落实",
        group="施工作业风险防范",
    ),
    _m(
        "hw_clear_upper_objects",
        "清除上方物体或采取中间隔离",
        group="施工作业风险防范",
    ),
    _m(
        "hw_welder_grounding",
        "电焊机所处位置已考虑防火防爆要求，且已可靠接地",
        group="施工作业风险防范",
    ),
    _m(
        "hw_gas_cylinders",
        (
            # 按《新版作业票》文档原文（含原文"乙换气瓶"写法）
            "乙炔气瓶直立放置，已采取防倾倒措施并安装防回火装置；"
            "乙换气瓶、氧气瓶与火源间的距离不应小于10m，"
            "两气瓶相互间距不应小于5m"
        ),
        group="施工作业风险防范",
    ),
    _m(
        "hw_jha_done",
        ("已开展作业危害分析，制定相应的安全风险管控措施，交叉作业已明确协调人"),
        group="施工作业风险防范",
    ),
    _m(
        "hw_fire_equipment",
        (
            "清理现场应急通道阻挡物，现场配备灭火器（ ）台，"
            "灭火毯（ ）块，消防蒸汽带或消防水带（ ）条"
        ),
        "extinguisher_count",
        "blanket_count",
        "hose_count",
        group="施工作业风险防范",
    ),
    _m(
        "hw_ppe_warning_zone",
        "作业人员穿戴规范，使用防护用具完好，作业现场四周已设立警戒区",
        group="施工作业风险防范",
    ),
    _m(
        "hw_recording_device",
        (
            "特级动火作业配备的摄录设备已到位，且防爆级别满足安全要求，"
            "用于连续检测的移动式可燃气体检测仪已配备到位"
        ),
        group="施工作业风险防范",
    ),
    _m(
        "hw_related_permits",
        "其他相关特殊作业已办理相应安全作业票",
        group="施工作业风险防范",
    ),
)

_CONFINED_SPACE_MEASURES: tuple[dict[str, object], ...] = (
    _m(
        "cs_valve_closed",
        (
            "受限空间连接的有毒有害、蒸汽、氮气、腐蚀性管道阀门已进行关闭，"
            "并悬挂“阀门关闭”标志牌"
        ),
    ),
    _m(
        "cs_add_blind_plates",
        (
            "受限空间连接的有毒有害、蒸汽、氮气、腐蚀性管道阀门已加装盲板，"
            "并落实盲板责任人，不得采用水封或关闭阀门代替盲板；加盲板___处"
        ),
        "blind_count",
    ),
    _m(
        "cs_disconnect_pipes",
        (
            "受限空间连接的有毒有害、蒸汽、氮气、腐蚀性管道阀门已与管道断开；"
            "设备隔断（拆除管道）____处"
        ),
        "removed_pipe_count",
    ),
    _m(
        "cs_purged",
        "盛装过有毒、可燃物料的受限空间，设备已经过置换、吹扫或蒸煮",
    ),
    _m(
        "cs_natural_ventilation",
        "设备通风孔已打开进行自然通风，温度适宜人员作业",
    ),
    _m(
        "cs_forced_ventilation",
        (
            "必要时采用强制通风或佩戴隔绝式呼吸防护装备，"
            "不应采用直接通入氧气或富氧空气的方法补充氧"
        ),
    ),
    _m(
        "cs_power_locked",
        "转动设备已切断电源，电源开关处已加锁并悬挂“禁止合闸”标志牌",
    ),
    _m(
        "cs_explosionproof_tools",
        (
            "受限空间内部已具备进入作业条件，易燃易爆物料容器内作业，"
            "作业人员应采用防爆工具，手持电动工具符合作业安全要求"
        ),
    ),
    _m(
        "cs_passage_clear",
        "受限空间进出口通道畅通，无阻碍人员进出的障碍物",
    ),
    _m(
        "cs_gas_analyzed",
        (
            "盛装过可燃有毒液体、气体的受限空间，已分析其中的可燃、"
            "有毒有害气体和氧气含量，且在安全范围内"
        ),
    ),
    _m(
        "cs_dust_stopped",
        "存在大量扬尘的设备已停止扬尘",
    ),
    _m(
        "cs_detector_ready",
        "用于连续检测的移动式可燃、有毒气体、氧气检测仪已配备到位",
    ),
    _m(
        "cs_ppe_ready",
        "作业人员已佩戴必要的个体防护装备，清除受限空间内存在的危险因素",
    ),
    _m(
        "cs_emergency_equipment",
        (
            "已配备作业应急设施：消防器材（ ）、救生绳（ ）、气防装备（ ）；"
            "盛有腐蚀性介质的容器作业现场已配备应急用冲洗水"
        ),
        "fire_equipment",
        "life_rope",
        "gas_protection_equipment",
    ),
    _m(
        "cs_communication",
        "受限空间内作业已配备通信设备",
    ),
    _m(
        "cs_warning_zone",
        "受限空间出入口四周已设立警戒区",
    ),
    _m(
        "cs_related_permits",
        "其他相关特殊作业已办理相应安全作业票",
    ),
)

_BLIND_PLATE_MEASURES: tuple[dict[str, object], ...] = (
    _m(
        "bp_normal_pressure",
        "在管道、设备上作业时，降低系统压力，作业点应为常压或微正压",
    ),
    _m(
        "bp_toxic_ppe",
        "在有毒介质的管道、设备上作业时，作业人员应穿戴适合的个体防护装备",
    ),
    _m(
        "bp_antistatic",
        (
            "火灾爆炸危险场所，作业人员穿防静电工作服、工作鞋；"
            "作业时使用防爆灯具和防爆工具"
        ),
    ),
    _m(
        "bp_no_hotwork_nearby",
        "火灾爆炸危险场所的气体管道，距作业地点30m内无其他动火作业",
    ),
    _m(
        "bp_corrosion_ppe",
        ("在强腐蚀性介质的管道、设备上作业时，作业人员已采取防止酸碱化学灼伤的措施"),
    ),
    _m(
        "bp_scald_protection",
        "介质温度较高、可能造成烫伤的情况下，作业人员已采取防烫措施",
    ),
    _m(
        "bp_frostbite_protection",
        "介质温度较低、可能造成人员冻伤情况下，作业人员已采取防冻伤措施",
    ),
    _m(
        "bp_single_point",
        "同一管道上未同时进行两处及两处以上的盲板抽堵作业",
    ),
    _m(
        "bp_related_permits",
        "其他相关特殊作业已办理相应安全作业票",
    ),
    _m(
        "bp_warning_zone",
        "作业现场四周已设警戒区",
    ),
)

_HEIGHT_MEASURES: tuple[dict[str, object], ...] = (
    _m("gc_physical_condition", "作业人员身体条件符合要求"),
    _m("gc_dress_code", "作业人员着装符合作业要求"),
    _m("gc_helmet_belt", "作业人员佩戴符合标准要求的安全帽、安全带"),
    _m(
        "gc_breathing_apparatus",
        "有可能散发有毒气体的场所携带正压式空气呼吸器或面罩备用",
    ),
    _m("gc_tool_bag", "作业人员携带有工具袋及安全绳"),
    _m("gc_scaffold", "现场搭设的脚手架、防护网、围栏符合安全规定"),
    _m("gc_layer_isolation", "垂直分层作业中间有隔离设施"),
    _m("gc_ladder_rope", "梯子、绳子符合安全规定"),
    _m(
        "gc_shed_load",
        "轻型棚的承重梁、柱能承重作业过程最大负荷的要求",
    ),
    _m(
        "gc_platform_stable",
        "作业人员在不承重物处作业所搭设的承重板稳定牢固",
    ),
    _m("gc_lighting", "采光、夜间作业照明符合作业要求"),
    _m(
        "gc_comm_tools",
        "30m以上高处作业时，作业人员已配备通信、联络工具",
    ),
    _m("gc_warning_zone", "作业现场四周已设警戒区"),
    _m("gc_wind_ok", "露天作业，风力满足作业安全要求"),
    _m("gc_related_permits", "其他相关特殊作业已办理相应安全作业票"),
)

_LIFTING_MEASURES: tuple[dict[str, object], ...] = (
    _m(
        "dz_plan_approved_12",
        "一、二级吊装作业已编制吊装作业方案，已经审查批准",
    ),
    _m(
        "dz_plan_approved_3",
        (
            "吊装物体形状复杂、刚度小、长径比大、精密贵重，"
            "作业条件特殊的三级吊装作业，已编制吊装作业方案，已经审查批准"
        ),
    ),
    _m(
        "dz_hazard_equipment_plan",
        (
            "吊装场所如有含危险物料的设备、管道时，应制定详细吊装方案，"
            "并对设备、管道采取有效防护措施，必要时停车，"
            "放空物料，置换后再进行吊装作业"
        ),
    ),
    _m("dz_ppe", "作业人员已按规定佩戴个体防护装备"),
    _m(
        "dz_tools_checked",
        ("已对起重吊装设备、钢丝绳、揽风绳、链条、吊钩等各种机具进行检查，安全可靠"),
    ),
    _m(
        "dz_signals_agreed",
        "已明确各自分工、坚守岗位，并统一规定联络信号",
    ),
    _m(
        "dz_anchor_approved",
        "将建筑物、构筑物作为锚点，应经所属单位工程管理部门审查核算并批准",
    ),
    _m(
        "dz_no_powerline_contact",
        "吊装绳索、揽风绳、拖拉绳等不应与带电线路接触，并保持安全距离",
    ),
    _m(
        "dz_no_pipe_anchor",
        "不应利用管道、管架、电杆、机电设备等作吊装锚点",
    ),
    _m(
        "dz_load_tied",
        "吊物捆扎坚固，未见绳打结、绳不齐现象，棱角吊物已采取衬垫措施",
    ),
    _m(
        "dz_crane_safety_devices",
        "起重机安全装置灵活好用",
    ),
    _m(
        "dz_valid_certificates",
        "吊装作业人员持有有效的法定资格证书",
    ),
    _m(
        "dz_underground_confirmed",
        (
            "地下通信电（光）缆、局域网络电（光）缆、排水沟的盖板，"
            "承重吊装机械的负重量已确认，保护措施已落实"
        ),
    ),
    _m(
        "dz_load_confirmed",
        "起吊物的质量（t）经确认，在吊装机械的承重范围内",
    ),
    _m(
        "dz_pipe_protection",
        "在吊装高度的管线、电缆桥架已做好防护措施",
    ),
    _m(
        "dz_warning_set",
        "作业现场围栏、警戒线、警告牌、夜间警示灯已按要求设置",
    ),
    _m(
        "dz_no_overhead_lines",
        "作业高度和转臂范围内无架空线路",
    ),
    _m(
        "dz_arrester",
        "在爆炸危险场所内的作业，机动车排气管已装阻火器",
    ),
    _m(
        "dz_wind_ok",
        "露天作业，环境风力满足作业安全要求",
    ),
    _m(
        "dz_related_permits",
        "其他相关特殊作业已办理相应安全作业票",
    ),
)

_TEMP_ELECTRICITY_MEASURES: tuple[dict[str, object], ...] = (
    _m("ld_certified_wirer", "接线人员持有电工作业操作证"),
    _m(
        "ld_explosion_grade",
        "在防爆场所使用的临时电源、元器件和线路达到相应的防爆等级要求",
    ),
    _m(
        "ld_upstream_locked",
        "上级开关已断电、加锁，并挂安全警示标牌",
    ),
    _m(
        "ld_tn_s",
        "临时用电的单相和混用线路要求按照TN-S三相五线制方式接线",
    ),
    _m(
        "ld_overhead_height",
        (
            "临时用电线路如架高敷设，在作业现场敷设高度应不低于2.5m，"
            "跨越道路高度应不低于5m"
        ),
    ),
    _m(
        "ld_wall_route",
        (
            "临时用电线路如沿墙面或地面敷设，已沿建筑物墙根部敷设，"
            "穿越道路或其他易受机械损伤的区域，已采取防机械损伤的措施；"
            "在电缆敷设路径附近，已采取防止火花损伤电缆的措施"
        ),
    ),
    _m(
        "ld_no_bare_wire",
        "临时用电线路架空进线不应采用裸线",
    ),
    _m(
        "ld_buried_marks",
        (
            "暗管埋设及地下电缆线路敷设时，已备好“走向标志”和"
            "“安全标志”等标志桩，电缆埋深要求大于0.7m"
        ),
    ),
    _m(
        "ld_rainproof",
        "现场临时用配电盘、箱配备有防雨措施，并可靠接地",
    ),
    _m(
        "ld_leakage_protection",
        (
            "临时用电设施已装配漏电保护器，移动工具、手持工具已采取"
            "防漏电的安全措施（一机一闸一保护）"
        ),
    ),
    _m(
        "ld_capacity_ok",
        "用电设备、线路容量、负荷符合要求",
    ),
    _m(
        "ld_related_permits",
        "其他相关特殊作业已办理相应安全作业票",
    ),
    _m(
        "ld_gas_checked",
        "作业场所已进行气体检测且符合作业安全要求",
    ),
)

_EXCAVATION_MEASURES: tuple[dict[str, object], ...] = (
    _m(
        "dt_cables_confirmed",
        ("地下电力电缆、通信电（光）缆、局域网络电（光）缆已确认，保护措施已落实"),
    ),
    _m(
        "dt_pipes_confirmed",
        "地下供排水、消防管线、工艺管线已确认，保护措施已落实",
    ),
    _m(
        "dt_layout_marked",
        "已按作业方案图划线和立桩",
    ),
    _m(
        "dt_warning_set",
        "作业现场围栏、警戒线、警告牌、夜间警示灯已按要求设置",
    ),
    _m(
        "dt_slope_support",
        "已进行放坡处理和固壁支撑",
    ),
    _m(
        "dt_road_reported",
        "道路施工作业已报：交通、消防、安全监督部门、应急中心",
    ),
    _m(
        "dt_night_lighting",
        ("现场夜间有充足照明：A.36V、24V、12V防水型灯；B.36V、24V、12V防爆型灯"),
    ),
    _m(
        "dt_ppe",
        "作业人员配备有必要的个人防护装备",
    ),
    _m(
        "dt_confined_space_rules",
        (
            "易燃易爆、有毒气体存在的场所动土深度超过1.2m，"
            "已按照受限空间作业要求采取了措施"
        ),
    ),
    _m(
        "dt_engineering_review",
        "有工程部进行对总图与现场进行审核",
    ),
    _m(
        "dt_related_permits",
        "其他相关特殊作业已办理相应安全作业票",
    ),
)

_ROAD_BREAKING_MEASURES: tuple[dict[str, object], ...] = (
    _m(
        "dl_traffic_plan",
        "作业前，制定交通组织方案，并已通知相关部门或单位",
    ),
    _m(
        "dl_warning_facilities",
        (
            "作业前，在断路的路口和相关道路上设置交通警示标志，"
            "在作业区域附近设置路栏、道路作业警示灯、导向标等交通警示设施"
        ),
    ),
    _m(
        "dl_night_lights",
        "夜间作业设置警示灯",
    ),
)

_HOT_WORK_TYPE_FIELDS: tuple[dict[str, object], ...] = (
    {
        "key": "hot_work_location",
        "label": "动火地点及动火部位",
        "type": "text",
        "required": True,
    },
    {
        "key": "hot_work_methods",
        "label": "动火方式",
        "type": "multi_select",
        "required": True,
        "options": (
            "焊接",
            "气割",
            "切削",
            "明火",
            "打磨",
            "电锤",
            "手枪钻",
            "其他",
            "使用非防爆的电气设备",
        ),
    },
)

_CONFINED_SPACE_TYPE_FIELDS: tuple[dict[str, object], ...] = (
    {
        "key": "space_name",
        "label": "受限空间名称",
        "type": "text",
        "required": True,
    },
    {
        "key": "original_medium",
        "label": "受限空间内原有介质名称",
        "type": "text",
    },
)

_BLIND_PLATE_TYPE_FIELDS: tuple[dict[str, object], ...] = (
    {
        "key": "blind_action",
        "label": "作业类别",
        "type": "select",
        "required": True,
        "options": ("堵盲板", "抽盲板"),
    },
    {
        "key": "equipment_pipe_name",
        "label": "设备、管道名称",
        "type": "text",
        "required": True,
    },
    {"key": "medium", "label": "介质", "type": "text"},
    {"key": "temperature", "label": "温度", "type": "text"},
    {"key": "pressure", "label": "压力", "type": "text"},
    {"key": "blind_material", "label": "盲板材质", "type": "text"},
    {"key": "blind_spec", "label": "盲板规格", "type": "text"},
    {"key": "blind_no", "label": "盲板编号", "type": "text"},
    {"key": "actual_start_time", "label": "实际作业开始时间", "type": "datetime"},
)

_HEIGHT_TYPE_FIELDS: tuple[dict[str, object], ...] = (
    {
        "key": "height_m",
        "label": "作业高度（m）",
        "type": "text",
        "required": True,
    },
)

_LIFTING_TYPE_FIELDS: tuple[dict[str, object], ...] = (
    {
        "key": "lifting_location",
        "label": "吊装地点",
        "type": "text",
        "required": True,
    },
    {"key": "lifting_tool", "label": "吊具名称", "type": "text"},
    {
        "key": "load_content",
        "label": "吊物内容",
        "type": "text",
        "required": True,
    },
    {
        "key": "load_weight_t",
        "label": "吊物质量（t）",
        "type": "number",
        "required": True,
    },
)

_TEMP_ELECTRICITY_TYPE_FIELDS: tuple[dict[str, object], ...] = (
    {
        "key": "power_access_point",
        "label": "电源接入点及许可用电功率",
        "type": "text",
        "required": True,
    },
    {"key": "voltage", "label": "工作电压", "type": "text"},
    {
        "key": "equipment_and_power",
        "label": "用电设备名称及额定功率",
        "type": "text",
    },
)

_EXCAVATION_TYPE_FIELDS: tuple[dict[str, object], ...] = (
    {
        "key": "work_scope",
        "label": "作业范围、内容、方式（包括深度、面积）",
        "type": "textarea",
        "required": True,
    },
)

_ROAD_BREAKING_TYPE_FIELDS: tuple[dict[str, object], ...] = (
    {
        "key": "road_breaking_reason",
        "label": "断路原因",
        "type": "textarea",
        "required": True,
    },
    {
        "key": "road_sketch_note",
        "label": "断路地段示意图及相关说明",
        "type": "textarea",
    },
    {
        "key": "related_units",
        "label": "涉及相关单位（部门）",
        "type": "text",
    },
)

_PERMIT_TYPES: tuple[PermitTypeTemplate, ...] = (
    PermitTypeTemplate(
        code="hot_work",
        name="动火作业",
        no_prefix="DH",
        levels=(LEVEL_SPECIAL, LEVEL_GRADE1, LEVEL_GRADE2),
        nodes=(
            _n(
                "process_tech_confirm",
                "工艺技术人员确认条件",
                NODE_KIND_CONFIRM,
            ),
            _n("safety_officer", "安全员/主管", NODE_KIND_APPROVE),
            _n("workshop_leader", "车间负责人", NODE_KIND_APPROVE),
            _n("safety_dept", "安全部", NODE_KIND_APPROVE),
            _n(
                "leader_explosion_zone",
                "分管领导（防爆区域）审核",
                NODE_KIND_APPROVE,
                (LEVEL_SPECIAL, LEVEL_GRADE1),
            ),
            _n(
                "approval_grade1",
                "一级审批（审核）",
                NODE_KIND_APPROVE,
                (LEVEL_SPECIAL, LEVEL_GRADE1),
            ),
            _n(
                "approval_special",
                "特级审批",
                NODE_KIND_APPROVE,
                (LEVEL_SPECIAL,),
            ),
            _n("pre_work_verify", "动火前岗位班长验票", NODE_KIND_VERIFY),
            _n("completion_accept", "完工验收", NODE_KIND_ACCEPT),
        ),
        person_roles=(
            {"role": "work_leader", "label": "作业负责人"},
            {"role": "worker", "label": "作业人", "cert": True, "multi": True},
            {"role": "guardian", "label": "作业监护人"},
            {"role": "process_guardian", "label": "工艺监护人"},
            {"role": "briefer", "label": "安全交底人"},
            {"role": "briefer_receiver", "label": "接受交底人"},
        ),
        measures=_HOT_WORK_MEASURES,
        type_fields=_HOT_WORK_TYPE_FIELDS,
        gas_enabled=True,
        gas_cycle_minutes=60,
        gas_fields=("representative_gas", "result_percent", "analyst_name"),
    ),
    PermitTypeTemplate(
        code="confined_space",
        name="受限空间作业",
        no_prefix="SX",
        levels=(LEVEL_NONE,),
        nodes=(
            _n("safety_officer", "安全员/主管签字", NODE_KIND_APPROVE),
            _n("workshop_leader", "车间负责人", NODE_KIND_APPROVE),
            _n("safety_dept_review", "安全部审核", NODE_KIND_APPROVE),
            _n(
                "direct_leader_zone",
                "直管领导（防爆区域）审核",
                NODE_KIND_APPROVE,
            ),
            _n("pre_work_verify", "作业前验票", NODE_KIND_VERIFY),
            _n("completion_accept", "完工验收", NODE_KIND_ACCEPT),
        ),
        person_roles=(
            {"role": "work_leader", "label": "作业负责人"},
            {"role": "worker", "label": "作业人", "cert": True, "multi": True},
            {"role": "guardian", "label": "监护人", "cert": True},
            {"role": "process_guardian", "label": "工艺监护人"},
            {"role": "briefer", "label": "安全交底人"},
            {"role": "briefer_receiver", "label": "接受交底人"},
        ),
        measures=_CONFINED_SPACE_MEASURES,
        type_fields=_CONFINED_SPACE_TYPE_FIELDS,
        gas_enabled=True,
        gas_cycle_minutes=120,
        gas_fields=(
            "toxic_gas_name",
            "toxic_gas_value",
            "combustible_gas_name",
            "combustible_gas_value",
            "oxygen_value",
            "analysis_point",
            "analyst_name",
        ),
    ),
    PermitTypeTemplate(
        code="blind_plate",
        name="盲板抽堵作业",
        no_prefix="MB",
        levels=(LEVEL_NONE,),
        nodes=(
            _n("safety_officer_opinion", "安全员意见", NODE_KIND_APPROVE),
            _n("workshop_leader_opinion", "车间负责人意见", NODE_KIND_APPROVE),
            _n("completion_accept", "完工验收", NODE_KIND_ACCEPT),
        ),
        person_roles=(
            {"role": "work_leader", "label": "作业负责人"},
            {"role": "worker", "label": "作业人", "multi": True},
            {"role": "guardian", "label": "监护人"},
            {"role": "briefer", "label": "安全交底人"},
            {"role": "briefer_receiver", "label": "接受交底人"},
        ),
        measures=_BLIND_PLATE_MEASURES,
        type_fields=_BLIND_PLATE_TYPE_FIELDS,
    ),
    PermitTypeTemplate(
        code="height_work",
        name="高处作业",
        no_prefix="GC",
        levels=(LEVEL_GRADE1, LEVEL_GRADE2, LEVEL_GRADE3, LEVEL_SPECIAL),
        nodes=(
            _n("safety_officer", "安全员/主管签字", NODE_KIND_APPROVE),
            _n("process_guardian", "工艺监护人", NODE_KIND_CONFIRM),
            _n("dept_leader", "部门负责人签字", NODE_KIND_APPROVE),
            _n("safety_dept_review", "安全部审核", NODE_KIND_APPROVE),
            _n(
                "direct_leader_review",
                "直管领导审核",
                NODE_KIND_APPROVE,
                (LEVEL_GRADE3, LEVEL_SPECIAL),
            ),
            _n(
                "special_height_review",
                "特殊级高处作业审核",
                NODE_KIND_APPROVE,
                (LEVEL_SPECIAL,),
            ),
            _n("pre_work_verify", "作业前验票", NODE_KIND_VERIFY),
            _n("completion_accept", "完工验收", NODE_KIND_ACCEPT),
        ),
        person_roles=(
            {"role": "work_leader", "label": "作业负责人"},
            {"role": "worker", "label": "作业人", "cert": True, "multi": True},
            {"role": "guardian", "label": "监护人"},
            {"role": "briefer", "label": "安全交底人"},
            {"role": "briefer_receiver", "label": "接受交底人"},
        ),
        measures=_HEIGHT_MEASURES,
        type_fields=_HEIGHT_TYPE_FIELDS,
    ),
    PermitTypeTemplate(
        code="lifting",
        name="吊装作业",
        no_prefix="DZ",
        levels=(LEVEL_GRADE1, LEVEL_GRADE2, LEVEL_GRADE3),
        nodes=(
            _n("construction_leader", "施工单位负责人签字", NODE_KIND_APPROVE),
            _n("safety_officer_opinion", "安全员意见", NODE_KIND_APPROVE),
            _n("local_unit_leader", "属地单位负责人签字", NODE_KIND_APPROVE),
            _n("engineering_dept", "工程部审核", NODE_KIND_APPROVE),
            _n(
                "safety_dept_grade1",
                "安全部审核（一级吊装作业）",
                NODE_KIND_APPROVE,
                (LEVEL_GRADE1,),
            ),
            _n("completion_accept", "完工验收", NODE_KIND_ACCEPT),
        ),
        person_roles=(
            {"role": "rigger", "label": "吊装作业人", "cert": True, "multi": True},
            {"role": "rigging_slacker", "label": "司索人", "cert": True, "multi": True},
            {"role": "crane_commander", "label": "指挥人员", "cert": True},
            {"role": "guardian", "label": "监护人"},
            {"role": "briefer", "label": "安全交底人"},
            {"role": "briefer_receiver", "label": "接受交底人"},
        ),
        measures=_LIFTING_MEASURES,
        type_fields=_LIFTING_TYPE_FIELDS,
    ),
    PermitTypeTemplate(
        code="temporary_electricity",
        name="临时用电作业",
        no_prefix="LD",
        levels=(LEVEL_NONE,),
        nodes=(
            _n("work_leader_opinion", "作业负责人意见", NODE_KIND_APPROVE),
            _n("power_user_unit", "用电单位意见", NODE_KIND_APPROVE),
            _n("power_supply_unit", "配送电单位意见", NODE_KIND_APPROVE),
            _n(
                "completion_accept",
                "用电负责人确认（拆线完成）",
                NODE_KIND_ACCEPT,
            ),
        ),
        person_roles=(
            {"role": "electricity_user", "label": "用电人"},
            {"role": "wiring_person", "label": "接线人", "cert": True},
            {"role": "wiring_guardian", "label": "接线监护人", "cert": True},
            {"role": "guardian", "label": "监护人"},
            {"role": "briefer", "label": "安全交底人"},
            {"role": "briefer_receiver", "label": "接受交底人"},
        ),
        measures=_TEMP_ELECTRICITY_MEASURES,
        type_fields=_TEMP_ELECTRICITY_TYPE_FIELDS,
        gas_enabled=True,
        gas_cycle_minutes=None,
        gas_fields=("result_value", "analysis_point", "analyst_name"),
    ),
    PermitTypeTemplate(
        code="excavation",
        name="动土作业",
        no_prefix="DT",
        levels=(LEVEL_NONE,),
        nodes=(
            _n("worker_sign", "作业人签字", NODE_KIND_CONFIRM),
            _n("construction_leader", "施工单位负责人", NODE_KIND_APPROVE),
            _n("electrical_dept", "电气部门审核", NODE_KIND_APPROVE),
            _n("local_unit_leader", "属地单位负责人", NODE_KIND_APPROVE),
            _n("power_dept", "动力部门审核", NODE_KIND_APPROVE),
            _n("instrument_dept", "仪表部门审核", NODE_KIND_APPROVE),
            _n("engineering_dept", "工程部审核", NODE_KIND_APPROVE),
            _n("fire_dept", "消防部门审核", NODE_KIND_APPROVE),
            _n("pre_work_verify", "作业前验票", NODE_KIND_VERIFY),
            _n("completion_accept", "作业完工验收", NODE_KIND_ACCEPT),
        ),
        person_roles=(
            {"role": "work_leader", "label": "作业负责人"},
            {"role": "worker", "label": "作业人", "multi": True},
            {"role": "guardian", "label": "监护人"},
            {"role": "briefer", "label": "安全交底人"},
            {"role": "briefer_receiver", "label": "接受交底人"},
        ),
        measures=_EXCAVATION_MEASURES,
        type_fields=_EXCAVATION_TYPE_FIELDS,
    ),
    PermitTypeTemplate(
        code="road_breaking",
        name="断路作业",
        no_prefix="DL",
        levels=(LEVEL_NONE,),
        nodes=(
            _n("work_leader_opinion", "作业负责人意见", NODE_KIND_APPROVE),
            _n("unit_opinion", "所在单位意见", NODE_KIND_APPROVE),
            _n(
                "fire_safety_dept",
                "消防、安全管理部门意见",
                NODE_KIND_APPROVE,
            ),
            _n("approval_dept", "审批部门意见", NODE_KIND_APPROVE),
            _n("completion_accept", "完工验收", NODE_KIND_ACCEPT),
        ),
        person_roles=(
            {"role": "work_leader", "label": "作业负责人"},
            {"role": "guardian", "label": "监护人"},
            {"role": "briefer", "label": "安全交底人"},
            {"role": "briefer_receiver", "label": "接受交底人"},
        ),
        measures=_ROAD_BREAKING_MEASURES,
        type_fields=_ROAD_BREAKING_TYPE_FIELDS,
    ),
)

PERMIT_TEMPLATES: dict[str, PermitTypeTemplate] = {t.code: t for t in _PERMIT_TYPES}

PERMIT_TYPE_OPTIONS: list[dict[str, str]] = [
    {"value": t.code, "label": t.name, "no_prefix": t.no_prefix} for t in _PERMIT_TYPES
]


def get_template(permit_type: str) -> PermitTypeTemplate:
    """按票种取模板；未知票种抛 KeyError（调用方先校验）。"""
    return PERMIT_TEMPLATES[permit_type]


def active_nodes_for_level(
    permit_type: str, permit_level: str
) -> list[dict[str, object]]:
    """按票种+级别返回激活的节点链（保持票面顺序）。"""
    template = get_template(permit_type)
    active: list[dict[str, object]] = []
    for node in template.nodes:
        levels = node["levels"]
        if levels is None or permit_level in _as_level_tuple(levels):
            active.append(node)
    return active


def level_options_for(permit_type: str) -> list[dict[str, str]]:
    template = get_template(permit_type)
    return [
        {"value": level, "label": PERMIT_LEVEL_LABELS[level]}
        for level in template.levels
    ]


def person_role_options_for(permit_type: str) -> list[dict[str, object]]:
    return list(get_template(permit_type).person_roles)


def measure_template_for(permit_type: str) -> list[dict[str, object]]:
    return [dict(item) for item in get_template(permit_type).measures]


def type_fields_for(permit_type: str) -> list[dict[str, object]]:
    return [dict(item) for item in get_template(permit_type).type_fields]


def attachments_allowed(permit_type: str) -> bool:
    """盲板位置图 / 动土简图 / 断路示意图等票面要求附图的票种。"""
    return permit_type in {
        "blind_plate",
        "excavation",
        "road_breaking",
        "hot_work",
    }


def gas_cycle_minutes_for(
    permit_type: str, settings: dict[str, int] | None = None
) -> int | None:
    """作业期间气体复检间隔（分钟）；None 表示无周期复检要求。"""
    template = get_template(permit_type)
    if not template.gas_enabled or template.gas_cycle_minutes is None:
        return None
    if settings and permit_type in settings:
        return int(settings[permit_type])
    return template.gas_cycle_minutes


# 作业票有效期默认（小时）：特/一级动火 8h、二级动火 72h（GB 30871-2022 口径，
# 可经 work_permit_settings 键 validity_hours 覆盖）；其余票种按实施时间窗。
VALIDITY_HOURS_DEFAULTS: dict[str, dict[str, float]] = {
    "hot_work": {LEVEL_SPECIAL: 8, LEVEL_GRADE1: 8, LEVEL_GRADE2: 72},
}

__all__ = [
    "CERTIFICATE_CATEGORIES",
    "CERTIFICATE_CATEGORY_LABELS",
    "NODE_KIND_ACCEPT",
    "NODE_KIND_APPROVE",
    "NODE_KIND_CONFIRM",
    "NODE_KIND_VERIFY",
    "NODE_STATUS_APPROVED",
    "NODE_STATUS_PENDING",
    "NODE_STATUS_REJECTED",
    "NODE_STATUS_SKIPPED",
    "NODE_STATUS_WAITING",
    "PERSON_ROLE_CERT_CATEGORIES",
    "MULTI_PERSON_ROLES",
    "is_multi_person_role",
    "INITIATOR_SIGN_KEYS",
    "brief_worker_entries",
    "brief_sign_key",
    "PERSON_ROLE_LABELS",
    "PERMIT_LEVEL_LABELS",
    "PERMIT_STATUS_ACTIVE",
    "PERMIT_STATUS_APPROVED",
    "PERMIT_STATUS_CANCELLED",
    "PERMIT_STATUS_COMPLETED",
    "PERMIT_STATUS_DRAFT",
    "PERMIT_STATUS_LABELS",
    "PERMIT_STATUS_PENDING",
    "PERMIT_STATUS_REJECTED",
    "PERMIT_TEMPLATES",
    "PERMIT_TYPE_OPTIONS",
    "RISK_IDENTIFICATION_OPTIONS",
    "VALIDITY_HOURS_DEFAULTS",
    "active_nodes_for_level",
    "attachments_allowed",
    "gas_cycle_minutes_for",
    "get_template",
    "level_options_for",
    "measure_template_for",
    "person_role_options_for",
    "type_fields_for",
]
