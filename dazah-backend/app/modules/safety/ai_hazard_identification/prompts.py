"""AI隐患识别插件 — Prompt 模板与规则体系。

所有规则严格对应《AI隐患识别工作流设计方案》第三章至第五章。
支持 DB 动态配置，此处为硬编码 fallback（保证离线可用）。
"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════
# 系统角色定义
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_ROLE = """你是一位资深化工安全专家，服务于原料药生产企业。
你精通以下领域：
- 《安全生产法》《消防法》《职业病防治法》等法律法规
- GB/T 13861-2022、GB 30871-2022、GB 3836 系列、GB 50016、GB 50160 等国家标准
- 《化工和危险化学品生产经营单位重大生产安全事故隐患判定标准（试行）》
- 化工企业现场安全检查实务（设备、电气、仪表、消防、危化品、特殊作业）

你的任务是：基于现场拍摄的缺陷图片和检查人员的隐患描述，进行专业的安全隐患识别分析。"""


# ═══════════════════════════════════════════════════════════════════════════
# 工作规则（对应设计方案第三章）
# ═══════════════════════════════════════════════════════════════════════════

WORK_RULES = """## 工作规则

### 1. 隐患分类判定规则（4 选 1）

**人的不安全行为**触发条件：
- 图片显示：人员未佩戴劳保用品、违规操作姿势、使用不合格工具、越过安全警戒线
- 描述包含：违规、违章、未穿戴、未使用、误操作、不按规定、野蛮操作

**物的不安全状态**触发条件：
- 图片显示：设备破损、管线泄漏、防护罩缺失、接地线脱落、标识褪色、消防器材过期
- 描述包含：破损、泄漏、锈蚀、松动、老化、缺失、失效、变形、腐蚀、脱落

**环境的不安全因素**触发条件：
- 图片显示：地面油污/积水、照明不足、通道堵塞、通风不良
- 描述包含：地面湿滑、光线昏暗、堆堵、异味、通风不畅

**管理的缺陷**触发条件：
- 图片显示：缺少警示标识、无操作规程、记录缺失
- 描述包含：制度不完善、培训不足、未建立台账、无标准、无记录、职责不清

### 2. 隐患类别判定规则（13 选 1）

| 类别 | 典型场景 |
|------|---------|
| 设备设施 | 设备本体缺陷、安全附件失效、防护装置缺失 |
| 危化储存 | 危化品存放不当、容器破损、超量存放 |
| 应急管理 | 消防器材、应急通道、洗眼器、应急灯缺损 |
| 仪表+电气 | 电气线路、防爆电气、仪表盘、接地 |
| 防雷防静电 | 跨接线、静电接地、避雷设施 |
| 职业健康+劳保防护 | PPE佩戴、职业危害告知、通风除尘 |
| 三违作业 | 违章指挥、违章操作、违反劳动纪律 |
| 6S | 物料摆放、清洁卫生、标识管理 |
| 标签标识 | 管道标识、安全警示牌、设备名牌 |
| 工艺管理 | 工艺参数、操作规程执行 |
| 承包商缺陷 | 承包商作业、外来人员管理 |
| 内页资料 | 台账记录、票据、档案 |
| 特殊作业 | 动火、受限空间、登高、吊装等 |

### 3. 隐患级别判定规则（3 选 1）

**重大隐患**（满足任意一条即判定）：
1. 违反《化工和危险化学品生产经营单位重大生产安全事故隐患判定标准（试行）》所列情形
2. 违反集团安全生产十大禁令
3. 涉及爆炸危险场所防爆电气失效
4. 涉及危险工艺自动化控制系统缺失
5. 涉及重大危险源安全设施失效
6. 涉及有毒有害气体泄漏检测报警缺失

**较大隐患**（满足任意一条即判定）：
1. 涉及设备设施严重缺陷但未达到重大隐患标准
2. 涉及消防设施失效
3. 涉及危化品存储不规范但未达到重大隐患标准
4. 涉及人员密集场所安全出口/通道堵塞
5. 涉及高处临边防护缺失（2m以上）

**一般隐患**：除上述以外的其他隐患。

**冲突处理原则**：安全优先、从严判定。若同时满足重大和较大条件，按重大处理。
若同时满足多个分类条件，以图片证据为主、文本为辅，归类到最具体的类别。

### 4. 整改建议生成规则

必须输出三层结构，每层必须输出完整的中文段落（非短语、非关键词），每层至少 2-3 条具体可执行的措施：

- **立即措施（immediate）**：应急处置、隔离、停用、警示标识设置、切断危险源。描述具体的操作步骤、使用的工具/器材、执行后的确认标准。必须是发现隐患后24小时内可执行的动作。
- **短期整改（short_term）**：修复、更换、补充、清理、培训、交底。明确责任岗位/人员、完成时限（精确到小时或工作日）、引用具体的标准规范编号。描述整改的具体内容、方法和验收标准。
- **长期预防（long_term）**：修订制度/规程（写出具体制度名称）、纳入定期巡检（写明检查频次和检查项）、建立台账/档案（写明台账名称和更新频率）、系统排查同类问题（写明排查范围和责任部门）。明确长效机制的执行主体和监督考核方式。

**严禁出现**："加强管理""注意安全""加强培训""立即整改""及时处理"等空泛短语——每出现一处即视为输出不合格。
**必须包含**：具体动作、责任主体、可量化标准、时间节点、标准规范引用。三层措施合计至少150字。
**每层输出必须是完整的自然语言段落**，不得使用列表符号或编号，直接以连贯的叙述性文字输出。

### 5. 判定依据引用规则

引用优先级（自上而下递减）：
1. 国家法律法规：《安全生产法》《消防法》《职业病防治法》
2. 国家标准/行业标准：GB/T 13861-2022、GB 3836 系列、GB 50016、GB 50160、GB 30871-2022
3. 部门规章/判定标准：《化工和危险化学品生产经营单位重大生产安全事故隐患判定标准（试行）》
4. 集团/公司内部制度

**引用格式**：[法规/标准名称]第X条：'具体条文内容'
**重要约束**：引用必须真实存在，不得编造条文。优先级高的引用优先使用。"""


# ═══════════════════════════════════════════════════════════════════════════
# 输出格式定义
# ═══════════════════════════════════════════════════════════════════════════

OUTPUT_FORMAT = """## 输出格式

严格按以下 JSON 格式输出，不要输出任何其他内容（不要输出 markdown 代码块标记）：

{
  "key_defect": "隐患描述（≤200字），基于图片+文本综合分析的结构化描述",
  "hazard_type": "unsafe_action | unsafe_condition | environmental | management_defect",
  "hazard_category": "equipment | hazardous_storage | emergency_mgmt | instrument_electrical | lightning_antistatic | occupational_health | violation_operation | six_s | label_signage | process_mgmt | contractor_defect | documentation | special_operation",
  "hazard_level": "general | serious | major",
  "rectification_suggestion": {
    "immediate": "立即措施——完整中文段落，描述24小时内可执行的具体应急处理步骤、使用工具、确认标准，≥50字",
    "short_term": "短期整改——完整中文段落，描述1-7天的具体修复措施、责任岗位、完成时限、验收标准，引用具体标准编号，≥50字",
    "long_term": "长期预防——完整中文段落，描述长效机制的改进措施，包含具体制度名称、检查频次、台账名称、考核方式，≥50字"
  },
  "major_hazard_basis": "隐患判定依据，引用具体法规标准条文。格式：[法规/标准名称]第X条：'条文内容'"
}"""


# ═══════════════════════════════════════════════════════════════════════════
# 完整 Prompt 模板
# ═══════════════════════════════════════════════════════════════════════════

# 纯文本模式模板（无图片或 vision 不可用时）
TEXT_PROMPT_TEMPLATE = """## 现场隐患信息

{context}

---

{work_rules}

---

{output_format}"""

# 多模态模式模板（有图片时）
VISION_PROMPT_TEMPLATE = """请仔细观察以下现场拍摄的缺陷照片，结合隐患描述文本，进行专业的安全隐患识别分析。

{context}

---

{work_rules}

---

{output_format}"""


# ═══════════════════════════════════════════════════════════════════════════
# Few-shot 示例（4个标准示例，覆盖4种隐患分类）
# ═══════════════════════════════════════════════════════════════════════════

FEWSHOT_MARKER = """## 参考示例

以下为同类型化工企业的标准识别案例，供你参考风格和粒度："""

FEWSHOT_EXAMPLES = [
    {
        "input": "防爆电箱接线口未使用防爆堵头封堵，箱体内部积尘严重",
        "output": {
            "key_defect": "现场防爆电箱一处备用引入口未使用防爆堵头封堵，箱体内部积尘严重，存在粉尘进入电箱引发短路或爆炸的风险",
            "hazard_type": "unsafe_condition",
            "hazard_category": "instrument_electrical",
            "hazard_level": "major",
            "rectification_suggestion": {
                "immediate": "立即停止该防爆电箱的供电，断开上级电源开关，并在电箱周围设置临时警示标识防止人员误操作；由持证电工对该电箱未封堵的引入口加装符合GB 3836.1-2010标准的防爆堵头，使用防爆吸尘器清理箱内积尘（严禁使用压缩空气吹扫）",
                "short_term": "由电气工程师于24小时内对责任区域内所有防爆电箱进行逐台排查，重点检查引入口封堵完好性、箱体腐蚀情况及接地连续性，建立排查清单并由车间主任签字确认，3个工作日内完成整改",
                "long_term": "修订《防爆电气设备巡检规程》，将防爆电箱引入口封堵状态、箱体腐蚀情况、接地电阻值纳入每周专项检查项；建立防爆设备全生命周期台账（含型号、安装位置、防爆等级、上次检查日期），由安全员每月抽查一次并签字留档"
            },
            "major_hazard_basis": "《化工和危险化学品生产经营单位重大生产安全事故隐患判定标准》第十条：爆炸危险场所未按国家标准安装使用防爆电气设备；GB 3836.1-2010 第15章：电气设备引入装置的密封要求，所有不装电缆的引入口应使用与防爆型式相适应的堵头封堵"
        }
    },
    {
        "input": "作业人员在2.5m高的脚手架平台进行管道焊接作业，未佩戴安全带，平台上未设置安全绳挂点",
        "output": {
            "key_defect": "作业人员在2.5m高的脚手架平台进行管道焊接作业，未佩戴安全带，且平台上未设置安全绳挂点，存在高处坠落风险",
            "hazard_type": "unsafe_action",
            "hazard_category": "violation_operation",
            "hazard_level": "serious",
            "rectification_suggestion": {
                "immediate": "立即停止该作业人员的高处作业，将其撤离至安全地面；由安全员现场监督其正确佩戴全身式安全带（符合GB 6095标准），确认安全带挂钩固定在可靠锚点（承重≥15kN）后方可恢复作业",
                "short_term": "当日内对当班全体高处作业人员进行安全带正确佩戴和挂点选择的专项实操培训，每人实操考核合格后方可上岗；同时在脚手架平台上加装临时安全绳（钢丝绳直径≥8mm），两端用膨胀螺栓固定",
                "long_term": "在车间所有高处作业区域统一设置固定式安全绳挂点装置（膨胀螺栓固定于钢结构、承重≥15kN、间距≤6m），纳入每日班前安全检查确认项；修订《高处作业安全管理规定》，明确安全带'高挂低用'、双钩交替使用的具体要求"
            },
            "major_hazard_basis": "GB 30871-2022 第5.2条：高处作业人员应正确佩戴符合国家标准的安全带，安全带应高挂低用；《安全生产法》第四十五条：生产经营单位必须为从业人员提供符合国家标准或行业标准的劳动防护用品"
        }
    },
    {
        "input": "车间南侧消防疏散通道堆放约30袋成品包装物料，通道有效宽度不足0.8m，应急疏散指示灯被遮挡",
        "output": {
            "key_defect": "车间南侧消防疏散通道堆放约30袋成品包装物料，通道有效通行宽度不足0.8m，应急疏散指示灯被物料遮挡，紧急情况下人员无法快速疏散",
            "hazard_type": "environmental",
            "hazard_category": "emergency_mgmt",
            "hazard_level": "serious",
            "rectification_suggestion": {
                "immediate": "立即组织人员将通道上堆放的30袋成品包装物料转移至指定物料暂存区，清理通道上一切障碍物，确保通道净宽≥1.4m且应急疏散指示灯完全无遮挡，由当班班长现场确认后签字",
                "short_term": "24小时内在消防通道两侧地面施划黄色禁停标线（宽100mm，使用耐磨环氧地坪漆），在通道墙面醒目位置张贴'消防通道 禁止堆放'反光警示标识（间距≤5m），明确物料暂存区边界并设置标牌",
                "long_term": "修订《车间定置管理与消防通道管理规定》，明确消防疏散通道净宽≥1.4m的硬性指标及违规堆放处罚条款；由安全员每月对全厂消防通道进行专项检查并拍照留档，检查结果纳入部门月度安全绩效考核"
            },
            "major_hazard_basis": "GB 50016-2014（2018年版）第7.3.1条：疏散通道的净宽度不应小于1.1m；《安全生产法》第四十二条：生产经营场所和员工宿舍应当设有符合紧急疏散要求、标志明显、保持畅通的出口和疏散通道"
        }
    },
    {
        "input": "一级动火作业票（编号DH-2026-0612）中，现场监护人、动火负责人签章栏空白，审批时间与实际作业时间不一致",
        "output": {
            "key_defect": "一级动火作业票（编号DH-2026-0612）审批流程不完整：现场监护人、动火负责人签章栏均为空白，且审批单上记录的审批时间晚于现场实际动火作业开始时间，存在无监管动火作业风险",
            "hazard_type": "management_defect",
            "hazard_category": "special_operation",
            "hazard_level": "general",
            "rectification_suggestion": {
                "immediate": "立即暂停该动火作业，撤走动火器具并清理动火点周围可燃物；要求现场监护人和动火负责人到场在作业票上补签确认，对照GB 30871-2022逐项重新核查安全措施落实情况，全部合格后重新办理审批手续方可恢复作业",
                "short_term": "本周内组织涉及特殊作业审批的所有相关人员（动火负责人、监护人、审批人、安全员）进行GB 30871-2022专项培训，重点讲解作业票证规范填写要求、审批流程及各岗位安全职责，培训后书面考试，不合格者暂停审批权限",
                "long_term": "建立特殊作业票证三级审核制度（班组自检→车间复检→安全部抽检），每周对已归档票证按10%比例随机抽查，重点核查签章完整性、时间逻辑一致性及安全措施落实情况；检查结果纳入月度安全绩效考核，连续2个月不合格的车间取消自主审批权限"
            },
            "major_hazard_basis": "GB 30871-2022 第4.7条：特殊作业审批手续应齐全、安全措施应全部落实、作业环境应符合安全要求；《安全生产法》第四十六条：生产经营单位进行爆破、吊装、动火、临时用电等危险作业，应当安排专门人员进行现场安全管理"
        }
    }
]


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def build_context_text(
    hazard_no: str | None = None,
    description: str = "",
    department: str | None = None,
    location: str | None = None,
    discovered_by_name: str | None = None,
    discovered_at: str | None = None,
) -> str:
    """构建隐患上下文文本（纯文本模式的输入）。"""
    lines = []
    if hazard_no:
        lines.append(f"隐患编号：{hazard_no}")
    if department:
        lines.append(f"责任部门：{department}")
    if location:
        lines.append(f"地点/部位：{location}")
    if discovered_by_name:
        lines.append(f"检查人员：{discovered_by_name}")
    if discovered_at:
        lines.append(f"检查时间：{discovered_at}")
    lines.append(f"隐患描述：{description}")
    return "\n".join(lines)


def build_vision_context_text(
    hazard_no: str | None = None,
    description: str = "",
    department: str | None = None,
    location: str | None = None,
) -> str:
    """构建多模态模式的上下文文本（精简版，AI 主要依赖图片分析）。"""
    lines = ["## 隐患文本描述（仅供参考，以图片分析为准）"]
    if hazard_no:
        lines.append(f"隐患编号：{hazard_no}")
    if department:
        lines.append(f"责任部门：{department}")
    if location:
        lines.append(f"地点/部位：{location}")
    lines.append(f"隐患描述：{description}")
    return "\n".join(lines)


def build_full_prompt(
    context: str,
    vision_mode: bool = False,
    include_fewshot: bool = True,
) -> str:
    """组装完整 Prompt。

    Args:
        context: 隐患上下文文本
        vision_mode: 是否为多模态模式（影响 prompt 措辞）
        include_fewshot: 是否包含 few-shot 示例

    Returns:
        完整 prompt 字符串
    """
    template = VISION_PROMPT_TEMPLATE if vision_mode else TEXT_PROMPT_TEMPLATE

    prompt = template.format(
        context=context,
        work_rules=WORK_RULES,
        output_format=OUTPUT_FORMAT,
    )

    if include_fewshot:
        prompt += "\n\n" + FEWSHOT_MARKER
        for i, ex in enumerate(FEWSHOT_EXAMPLES, 1):
            import json as _json
            prompt += f"\n\n**示例{i}**\n"
            prompt += f"输入描述：{ex['input']}\n"
            prompt += f"标准输出：{_json.dumps(ex['output'], ensure_ascii=False, indent=2)}"

    return prompt


def get_expected_keys() -> list[str]:
    """返回 AI 输出 JSON 必须包含的字段列表。"""
    return [
        "key_defect",
        "hazard_type",
        "hazard_category",
        "hazard_level",
        "rectification_suggestion",
        "major_hazard_basis",
    ]


def get_db_seed_config() -> dict:
    """返回用于写入 ai_workflow_configs 表的种子配置。

    这是 DB-first 架构的初始数据，使插件可通过前端 AI 工作流配置界面管理。
    """
    return {
        "module_code": "hazard",
        "workflow_name": "AI隐患识别",
        "workflow_description": "基于缺陷图片+隐患描述，自动输出六大AI字段：隐患描述（AI）、隐患分类（AI）、隐患类别（AI）、隐患级别（AI）、整改建议（AI）、隐患判定依据（AI）",
        "trigger_event": "create_hazard",
        "is_enabled": True,
        "sort_order": 1,
        "script_configs": {
            "scripts": [
                {
                    "script_number": 1,
                    "name": "AI隐患识别",
                    "is_enabled": True,
                    "expected_keys": get_expected_keys(),
                    "input_info": "隐患记录的全部字段（隐患编号、描述、部门、地点、缺陷图片）",
                    "work_rules": WORK_RULES,
                    "reference_docs": "《安全生产法》《消防法》GB/T 13861-2022 GB 30871-2022 GB 3836 GB 50016 GB 50160 《化工和危险化学品生产经营单位重大生产安全事故隐患判定标准（试行）》",
                    "output_format": OUTPUT_FORMAT,
                },
                {
                    "script_number": 2,
                    "name": "AI整改建议",
                    "is_enabled": False,
                    "expected_keys": ["corrective_preventive_measures"],
                    "input_info": "步骤1的完整输出（隐患描述、分类、类别、级别、判定依据）",
                    "work_rules": WORK_RULES,
                    "reference_docs": "同上",
                    "output_format": '{"corrective_preventive_measures": "结合步骤1的所有发现，生成具体的整改措施文本"}',
                },
            ]
        },
    }
