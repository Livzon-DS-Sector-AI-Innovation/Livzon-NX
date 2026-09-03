import { ENERGY_DATA_PAGES } from "./energy-data-pages"
import { registrationCertificateSheets } from "./registration-certificate"
import { registrationDeclarationProgressSheets } from "./registration-declaration-progress"
import { registrationProjectLedgerSheets } from "./registration-project-ledger"
import {
  liquidInspectionGroups,
  solidInspectionGroups,
} from "./quality-inspection-material-groups"
import { warehouseHardwarePages } from "./warehouse-hardware-pages"

export interface SubMenuItem {
  key: string
  label: string
  path: string
  children?: SubMenuItem[]   // 嵌套子菜单 → Ant Design SubMenu
  disabled?: boolean         // 灰显占位，功能未开发
  placement?: "bottom"       // 置底显示，例如模块设置入口
  adminOnly?: boolean         // 仅系统管理员可见
  permission?: string         // 细粒度权限（仍由后端负责最终鉴权）
  feishuPageKey?: string      // 可绑定飞书只读数据表的稳定页面标识
  /** localStorage key 读取激活产品集合，用于动态菜单标签 */
  labelStorageKey?: string
  /** 产品 key → 显示名 映射，配合 labelStorageKey 使用 */
  labelProducts?: { key: string; name: string }[]
}

export interface ModuleMenu {
  key: string
  moduleCode: string
  label: string
  icon: string
  path: string
  children: SubMenuItem[]
}

export const moduleMenus: ModuleMenu[] = [
  {
    key: "production",
    moduleCode: "production",
    label: "生产管理",
    icon: "factory",
    path: "/production",
    children: [
      {
        key: "batches",
        label: "批次管理",
        path: "",
        children: [
          { key: "workshop-101-1", label: "101一车间（菌种）", path: "/production/batches/workshop/101-1" },
          { key: "workshop-101-2", label: "101二车间", path: "/production/batches/workshop/101-2" },
          { key: "workshop-102-1", label: "102一车间", path: "/production/batches/workshop/102-1" },
          { key: "workshop-102-2", label: "102二车间", path: "/production/batches/workshop/102-2" },
          {
            key: "workshop-103",
            label: "103车间",
            path: "",
            children: [
              { key: "ws103-phenylalanine", label: "苯丙氨酸", path: "/production/batches/workshop/103/phenylalanine" },
              {
                key: "ws103-lovastatin",
                label: "洛伐他汀/美伐他汀",
                path: "/production/batches/workshop/103/lovastatin",
                // 产品 key → 显示名 映射，配合 labelStorageKey 使用
                labelStorageKey: "workshop_103_lovastatin_active_products",
                labelProducts: [
                  { key: "lovastatin", name: "洛伐他汀" },
                  { key: "mevastatin", name: "美伐他汀" },
                ],
              },
            ],
          },
          { key: "workshop-201-1", label: "201一车间", path: "/production/batches/workshop/201-1" },
          { key: "workshop-201-2", label: "201二车间", path: "/production/batches/workshop/201-2" },
          { key: "workshop-201-3", label: "201三车间", path: "/production/batches/workshop/201-3" },
          { key: "workshop-202", label: "202车间", path: "/production/batches/workshop/202" },
          { key: "workshop-203", label: "203车间", path: "/production/batches/workshop/203" },
          { key: "workshop-203-3", label: "203三车间", path: "/production/batches/workshop/203-3" },
        ],
      },
      {
        key: "plan",
        label: "生产计划",
        path: "",
        children: [
          { key: "sales-plan", label: "产销计划", path: "/production/plan" },
          { key: "scheduling", label: "排产计划", path: "/production/scheduling" },
        ],
      },
      { key: "process", label: "工艺规程（开发中）", path: "/production/process" },
      { key: "records", label: "生产记录（开发中）", path: "/production/records" },
      { key: "balance", label: "物料平衡（开发中）", path: "/production/balance" },
      {
        key: "shift-log",
        label: "生产日志",
        path: "",
        children: [
          { key: "shift-log-deviation", label: "非密事件与运行偏差", path: "/production/shift-log/deviation" },
          { key: "shift-log-quality", label: "中间体质控数据台账", path: "/production/shift-log/quality" },
          { key: "shift-log-summary", label: "班次运行摘要", path: "/production/shift-log/summary" },
          { key: "shift-log-handover", label: "班组交接确认", path: "/production/shift-log/handover" },
        ],
      },
      { key: "label-verification", label: "标签复核", path: "/production/label-verification" },
      { key: "pressure", label: "压差统计", path: "/production/pressure" },
    ],
  },
  {
    key: "equipment",
    moduleCode: "equipment",
    label: "设备管理",
    icon: "cog",
    path: "/equipment",
    children: [
      { key: "stats", label: "设备仪表盘", path: "/equipment/stats" },
      { key: "assets", label: "设备台账", path: "/equipment/assets" },
      { key: "maintenance", label: "维护保养", path: "/equipment/maintenance" },
      { key: "inspection", label: "设备巡检", path: "/equipment/inspection" },
      { key: "spare-parts", label: "备件管理", path: "/equipment/spare-parts" },
      { key: "personnel", label: "人员配置", path: "/equipment/personnel" },
    ],
  },
  {
    key: "energy",
    moduleCode: "energy",
    label: "能源管理",
    icon: "bolt",
    path: "/energy",
    children: [
      { key: "overview", label: "能源总览", path: "/energy" },
      ...ENERGY_DATA_PAGES.map((page) => ({
        key: page.key,
        label: page.label,
        path: `/energy/${page.slug}`,
        feishuPageKey: page.pageKey,
      })),
      { key: "feishu-config", label: "飞书配置", path: "/energy/feishu-config", placement: "bottom" },
    ],
  },

  // ═══════════════════════════════════════════════════════
  // 安全管理模块 — 按化工安全生产管理体系分级
  // ═══════════════════════════════════════════════════════
  {
    key: "safety",
    moduleCode: "safety",
    label: "安全管理",
    icon: "shield",
    path: "/safety",
    children: [
      // ── 系统配置 ──
      {
        key: "system-config",
        label: "系统配置",
        path: "",
        children: [
          { key: "ai-workflow", label: "AI工作流配置", path: "/safety/ai-workflow-config" },
          { key: "scheduled-tasks", label: "定时任务", path: "/safety/scheduled-tasks" },
        ],
      },
      // ── 作业安全 ──
      {
        key: "ops-safety",
        label: "作业安全",
        path: "",
        children: [
          { key: "special-ops-mgmt", label: "特殊作业管理", path: "/safety/special-ops" },
          { key: "daily-risk-report", label: "关键风险作业报备", path: "/safety/risk-reporting" },
        ],
      },
      // ── 风险与隐患 ──
      {
        key: "risk-hazard",
        label: "风险与隐患",
        path: "",
        children: [
          {
            key: "risk-grading",
            label: "风险分级管控",
            path: "",
            children: [
              { key: "hazard-identification", label: "危险源辨识工作流", path: "/safety/hazard-identification" },
              { key: "hazard-ledger", label: "危险源辨识台账", path: "/safety/hazard-identification/ledger" },
            ],
          },
          {
            key: "hazard-inspection",
            label: "隐患排查治理",
            path: "",
            children: [
              { key: "hazard-inspection-ledger", label: "隐患台账", path: "/safety/hazard-ledger" },
            ],
          },
          {
            key: "regulation",
            label: "安全操规管理",
            path: "",
            children: [
              { key: "regulation-list", label: "安全操规台账", path: "/safety/regulation" },
              { key: "regulation-generator", label: "标准化生成", path: "/safety/regulation/generator" },
            ],
          },
          {
            key: "ehs-change",
            label: "EHS变更管理",
            path: "",
            children: [
              { key: "ehs-change-apply", label: "EHS变更申请", path: "/safety/ehs-change" },
            ],
          },
        ],
      },
      // ── 应急与事故 ──
      {
        key: "emergency-accident",
        label: "应急与事故",
        path: "",
        children: [
          { key: "accident-ledger", label: "事故台账", path: "/safety/accident" },
          { key: "emergency-plan", label: "应急预案", path: "", disabled: true },
        ],
      },
      // ── 安全培训与检查 ──
      {
        key: "training-check",
        label: "安全培训与检查",
        path: "",
        children: [
          { key: "safety-check", label: "安全检查", path: "/safety/check" },
          { key: "safety-training", label: "安全培训", path: "/safety/training" },
          { key: "contractor", label: "相关方管理", path: "/safety/contractor" },
        ],
      },
      // ── 职业健康 ──
      {
        key: "occupational-health-group",
        label: "职业健康",
        path: "",
        children: [
          { key: "oh-monitor", label: "职业危害因素监测", path: "/safety/occupational-health" },
        ],
      },
      // ── 法规与安全信息 ──
      {
        key: "regulation-info",
        label: "法规与安全信息",
        path: "",
        children: [
          { key: "knowledge-base", label: "安全知识库", path: "/safety/knowledge-base" },
        ],
      },
    ],
  },

  {
    key: "rd",
    moduleCode: "research",
    label: "研发管理",
    icon: "beaker",
    path: "/rd",
    children: [
      { key: "project-initiation", label: "立项（开发中）", path: "/rd/project-initiation" },
      { key: "route-development", label: "打通路线", path: "/rd/route-development" },
      { key: "process-optimization", label: "工艺优化", path: "/rd/process-optimization" },
      { key: "pilot-workflow", label: "中试研究", path: "/rd/pilot-workflow" },
      { key: "process-validation", label: "工艺验证（开发中）", path: "/rd/process-validation" },
      { key: "registration-filing", label: "申报资料（开发中）", path: "/rd/registration-filing" },
      { key: "projects", label: "研发项目（开发中）", path: "/rd/projects" },
      { key: "experiments", label: "实验记录（开发中）", path: "/rd/experiments" },
      { key: "reports", label: "研发报告（开发中）", path: "/rd/reports" },
      { key: "bayesian", label: "贝叶斯优化", path: "/rd/bayesian" },
      { key: "ich-analysis", label: "ICH Q3C/Q3D 杂质识别", path: "/rd/ich-analysis" },
    ],
  },
  {
    key: "registration",
    moduleCode: "registration",
    label: "注册管理",
    icon: "document",
    path: "/registration",
    children: [
      {
        key: "project",
        label: "申报项目",
        path: "/registration/project",
        children: [
          {
            key: "project-ledger",
            label: "申报台账",
            path: "/registration/project-ledger",
            children: registrationProjectLedgerSheets.map((item) => ({
              key: item.key,
              label: item.name,
              path: item.path,
            })),
          },
          {
            key: "declaration-progress",
            label: "申报进度",
            path: "/registration/declaration-progress",
            children: registrationDeclarationProgressSheets.map((item) => ({
              key: item.key,
              label: item.name,
              path: item.path,
            })),
          },
        ],
      },
      { key: "authorization-letter", label: "授权书管理", path: "/registration/authorization-letter" },
      {
        key: "certificate-management",
        label: "证书管理",
        path: "/registration/certificate-management",
        children: registrationCertificateSheets.map((item) => ({
          key: item.key,
          label: item.name,
          path: item.path,
        })),
      },
      { key: "regulation", label: "法规跟踪", path: "/registration/regulation" },
      {
        key: "fees",
        label: "注册费用",
        path: "/registration/fees",
        children: [
          { key: "fee-ledger", label: "费用台账", path: "/registration/fees/ledger" },
          { key: "inspection-contacts", label: "外检联系", path: "/registration/fees/contacts" },
        ],
      },
      { key: "knowledge", label: "注册知识库", path: "/registration/knowledge" },
    ],
  },
  {
    key: "quality",
    moduleCode: "quality",
    label: "质量管理",
    icon: "check-circle",
    path: "/quality",
    children: [
      { key: "feishu-settings", label: "飞书设置", path: "/quality/feishu-settings" },
      { key: "documents", label: "文件管理", path: "/quality/documents" },
      {
        key: "deviations",
        label: "偏差管理",
        path: "/quality/deviations",
        children: [
          { key: "deviation-records", label: "报告记录", path: "/quality/deviations/records" },
          { key: "deviation-investigations", label: "调查推送", path: "/quality/deviations/investigations" },
          { key: "deviation-ledger", label: "偏差台账", path: "/quality/deviations/ledger" },
          { key: "deviation-history", label: "历史偏差", path: "/quality/deviations/history" },
          { key: "deviation-workbench", label: "偏差工作台", path: "/quality/deviations/workbench" },
        ],
      },
      {
        key: "capas",
        label: "CAPA管理",
        path: "/quality/capas",
        children: [
          { key: "capa-ledger", label: "CAPA台账", path: "/quality/capas/ledger" },
          { key: "capa-plans", label: "计划跟踪", path: "/quality/capas/plans" },
        ],
      },
      {
        key: "complaints",
        label: "投诉管理",
        path: "/quality/complaints",
        children: [
          { key: "complaint-ledger", label: "投诉台账", path: "/quality/complaints/ledger" },
        ],
      },
      { key: "department-contacts", label: "部门联系人", path: "/quality/department-contacts" },
      {
        key: "inspection",
        label: "质量检验",
        path: "/quality/inspection",
        children: [
          {
            key: "inspection-items",
            label: "物品管理",
            path: "/quality/inspection/items",
            children: [
              { key: "inspection-items-inventory", label: "库存台账", path: "/quality/inspection/items/inventory" },
              { key: "inspection-items-inbound", label: "入库记录", path: "/quality/inspection/items/inbound" },
              { key: "inspection-items-outbound", label: "出库记录", path: "/quality/inspection/items/outbound" },
            ],
          },
          {
            key: "inspection-instruments",
            label: "仪器管理",
            path: "/quality/inspection/instruments",
            children: [
              { key: "inspection-instruments-equipment", label: "仪器设备", path: "/quality/inspection/instruments/equipment" },
              { key: "inspection-instruments-assets", label: "资产台账", path: "/quality/inspection/instruments/assets" },
              { key: "inspection-instruments-calibration", label: "校准计划", path: "/quality/inspection/instruments/calibration" },
              { key: "inspection-instruments-maintenance", label: "维护保养", path: "/quality/inspection/instruments/maintenance" },
              { key: "inspection-instruments-repair", label: "维修记录", path: "/quality/inspection/instruments/repair" },
              { key: "inspection-instruments-change", label: "变更记录", path: "/quality/inspection/instruments/change" },
              { key: "inspection-instruments-contracts", label: "外协合同", path: "/quality/inspection/instruments/contracts" },
              { key: "inspection-instruments-plans", label: "年度计划", path: "/quality/inspection/instruments/plans" },
            ],
          },
          {
            key: "inspection-finished",
            label: "成品检验",
            path: "/quality/inspection/finished",
            children: [
              { key: "inspection-finished-mpa", label: "霉酚酸", path: "/quality/inspection/finished/mpa" },
              { key: "inspection-finished-mvt", label: "美伐他汀", path: "/quality/inspection/finished/mvt" },
              { key: "inspection-finished-lft", label: "洛伐他汀", path: "/quality/inspection/finished/lft" },
              { key: "inspection-finished-dls", label: "多拉菌素", path: "/quality/inspection/finished/dls" },
              { key: "inspection-finished-lkms", label: "林可霉素", path: "/quality/inspection/finished/lkms" },
              { key: "inspection-finished-bbas", label: "L-苯丙氨酸", path: "/quality/inspection/finished/bbas" },
              { key: "inspection-finished-formulations", label: "预混剂", path: "/quality/inspection/finished/formulations" },
              { key: "inspection-finished-tryptophan", label: "色氨酸", path: "/quality/inspection/finished/tryptophan" },
              { key: "inspection-finished-water", label: "纯化水", path: "/quality/inspection/finished/water" },
            ],
          },
          {
            key: "inspection-solid",
            label: "固体物料检验",
            path: "/quality/inspection/solid",
            children: [
              { key: "inspection-solid-raw", label: "原料检验", path: "/quality/inspection/solid/raw-inspection" },
              ...solidInspectionGroups.map((item) => ({
                key: `inspection-solid-${item.key}`,
                label: item.label,
                path: `/quality/inspection/solid/${item.key}`,
              })),
            ],
          },
          {
            key: "inspection-liquid",
            label: "液体物料检验",
            path: "/quality/inspection/liquid",
            children: [
              { key: "inspection-liquid-raw", label: "原料检验", path: "/quality/inspection/liquid/raw-inspection" },
              ...liquidInspectionGroups.map((item) => ({
                key: `inspection-liquid-${item.key}`,
                label: item.label,
                path: `/quality/inspection/liquid/${item.key}`,
              })),
            ],
          },
        ],
      },
      {
        key: "oos-oot",
        label: "OOS/OOT管理",
        path: "/quality/oos-oot",
        children: [
          { key: "oos-oot-report-records", label: "报告记录", path: "/quality/oos-oot/report-records" },
          { key: "oos-oot-investigation-push", label: "调查推送", path: "/quality/oos-oot/investigation-push" },
          { key: "oos-ledger", label: "OOS台账", path: "/quality/oos-oot/oos-ledger" },
          { key: "oot-ledger", label: "OOT台账", path: "/quality/oos-oot/oot-ledger" },
          { key: "oot-limits", label: "各产品OOT限度", path: "/quality/oos-oot/oot-limits" },
          { key: "product-departments", label: "产品涉及部门", path: "/quality/oos-oot/product-departments" },
        ],
      },
      {
        key: "product-quality",
        label: "产品质量回顾",
        path: "/quality/product-quality",
        children: [
          { key: "product-quality-mfn", label: "霉酚酸", path: "/quality/product-quality/mfn" },
          { key: "product-quality-dljs", label: "多拉菌素", path: "/quality/product-quality/dljs" },
          { key: "product-quality-lftt", label: "洛伐他汀", path: "/quality/product-quality/lftt" },
          { key: "product-quality-mftt", label: "美伐他汀", path: "/quality/product-quality/mftt" },
          { key: "product-quality-yslkms", label: "盐酸林可霉素", path: "/quality/product-quality/yslkms" },
          { key: "product-quality-bbas", label: "L-苯丙氨酸", path: "/quality/product-quality/bbas" },
          { key: "product-quality-sas", label: "L-色氨酸", path: "/quality/product-quality/sas" },
        ],
      },
      {
        key: "return-recalls",
        label: "退货召回",
        path: "/quality/return-recalls",
        children: [
          { key: "return-application", label: "退货申请", path: "/quality/return-recalls/return-application" },
          { key: "return-ledger", label: "退货台账", path: "/quality/return-recalls/return-ledger" },
        ],
      },
      {
        key: "suppliers",
        label: "供应商管理",
        path: "/quality/suppliers",
        children: [
          { key: "supplier-qualification", label: "供应商资质台账", path: "/quality/suppliers/qualification" },
        ],
      },
      {
        key: "change",
        label: "变更控制",
        path: "/quality/change",
        children: [
          { key: "change-ledger", label: "技术变更台账", path: "/quality/change/ledger" },
          { key: "file-change-ledger", label: "文件变更台账", path: "/quality/file-change/ledger" },
          { key: "change-action-plans", label: "变更计划", path: "/quality/change/action-plans" },
        ],
      },
      {
        key: "validation",
        label: "验证与确认",
        path: "/quality/validation",
        children: [
          { key: "validation-plans", label: "验证主计划", path: "/quality/validation/plans" },
          { key: "equipment-qualification", label: "设备确认", path: "/quality/validation/equipment-qualification" },
          { key: "process-validation", label: "工艺验证", path: "/quality/validation/process-validation" },
          { key: "cleaning-validation", label: "清洁验证", path: "/quality/validation/cleaning-validation" },
          { key: "other-validations", label: "其他验证", path: "/quality/validation/other-validations" },
          { key: "qc-validation", label: "QC验证", path: "/quality/validation/qc-validation" },
        ],
      },
    ],
  },
  {
    key: "admin",
    moduleCode: "administration",
    label: "行政管理",
    icon: "building",
    path: "/admin",
    children: [
      { key: "notice", label: "公告通知（开发中）", path: "/admin/notice", disabled: true },
      { key: "meeting", label: "会议管理（开发中）", path: "/admin/meeting", disabled: true },
      { key: "approval", label: "文件审批（开发中）", path: "/admin/approval", disabled: true },
    ],
  },
  {
    key: "hr",
    moduleCode: "hr",
    label: "人事管理",
    icon: "users",
    path: "/hr",
    children: [
      { key: "departments", label: "部门管理", path: "/hr/departments" },
      {
        key: "employee-management",
        label: "员工管理",
        path: "/hr/employee-management",
        children: [
          { key: "profile", label: "员工档案", path: "/hr/profile" },
          { key: "feishu-contacts", label: "飞书联系人", path: "/hr/feishu-contacts" },
        ],
      },
      { key: "recruitment", label: "招聘管理", path: "/hr/recruitment" },
      { key: "onboarding", label: "入职台账", path: "/hr/onboarding" },
      { key: "offboarding", label: "离职管理", path: "/hr/offboarding" },
      { key: "position-transfer", label: "岗位调动管理", path: "/hr/position-transfer" },
      {
        key: "contracts",
        label: "合同管理",
        path: "/hr/contracts",
        children: [
          { key: "contracts-ledger", label: "合同台账", path: "/hr/contracts" },
          { key: "contract-approval-results", label: "合同到期审批结果", path: "/hr/contracts/approval-results" },
        ],
      },
      {
        key: "training",
        label: "培训管理",
        path: "/hr/training",
        children: [
          { key: "annual-plan", label: "年度培训计划", path: "/hr/training/annual-plan" },
          { key: "sign-in-sheet", label: "培训资料", path: "/hr/training/sign-in" },
          { key: "new-employee-training", label: "新员工培训", path: "/hr/training/new-employee" },
          { key: "training-ledger", label: "培训台账", path: "/hr/training/ledger" },
          { key: "employee-training-list", label: "员工培训清单", path: "/hr/training/employee-training-list" },
          { key: "trainer", label: "培训师管理", path: "/hr/training/trainer" },
          { key: "position-training", label: "岗位培训清单", path: "/hr/training/position-training" },
          { key: "plan-tracking", label: "培训计划跟踪", path: "/hr/training/plan-tracking" },
        ],
      },
      {
        key: "hr-settings",
        label: "HR设置",
        path: "/hr/settings/feishu",
        children: [
          { key: "hr-settings-feishu", label: "飞书设置", path: "/hr/settings/feishu" },
          { key: "hr-settings-reminder", label: "提醒设置", path: "/hr/settings/reminder" },
          { key: "hr-settings-approval", label: "审批流程设置", path: "/hr/settings/approval" },
          { key: "hr-settings-dept-mapping", label: "培训部门映射", path: "/hr/settings/dept-mapping", permission: "hr:write" },
          { key: "hr-settings-dept-scopes", label: "部门权限配置", path: "/hr/settings/dept-scopes", permission: "hr:write" },
        ],
      },
    ],
  },
  {
    key: "warehouse",
    moduleCode: "warehouse",
    label: "仓储管理",
    icon: "archive",
    path: "/warehouse",
    children: [
      // feishuPageKey 与后端 FEISHU_WAREHOUSE_MATERIAL_PAGES 的裸 key 一致，
      // 供页面数据映射门（MappedMenuPageGate）定位绑定；空串 = 显式不映射
      { key: "ai-analysis", label: "AI分析", path: "/warehouse/ai-analysis", feishuPageKey: "" },
      {
        key: "materials",
        label: "原辅料及包材",
        path: "/warehouse/materials/dashboard",
        feishuPageKey: "",
        children: [
          { key: "raw-summary", label: "原辅料库存总表", path: "/warehouse/materials/raw-summary", feishuPageKey: "raw-summary" },
          { key: "raw-detail", label: "原辅料库存明细表", path: "/warehouse/materials/raw-detail", feishuPageKey: "raw-detail" },
          { key: "raw-ledger", label: "原辅料出库总账", path: "/warehouse/materials/raw-ledger", feishuPageKey: "raw-ledger" },
          { key: "packaging-summary", label: "包材库存总表", path: "/warehouse/materials/packaging-summary", feishuPageKey: "packaging-summary" },
          { key: "packaging-detail", label: "包材库存明细表", path: "/warehouse/materials/packaging-detail", feishuPageKey: "packaging-detail" },
          { key: "packaging-ledger", label: "包材出库总账", path: "/warehouse/materials/packaging-ledger", feishuPageKey: "packaging-ledger" },
          { key: "inbound-ledger", label: "入库总账", path: "/warehouse/materials/inbound-ledger", feishuPageKey: "inbound-ledger" },
          { key: "qualified-suppliers", label: "原辅材料合格供应商一览表", path: "/warehouse/materials/qualified-suppliers", feishuPageKey: "qualified-suppliers" },
          { key: "material-name-code-map", label: "物料名称及代码对应表", path: "/warehouse/materials/material-name-code-map", feishuPageKey: "material-name-code-map" },
        ],
      },
      {
        key: "hardware",
        label: "五金",
        path: "/warehouse/hardware/dashboard",
        feishuPageKey: "",
        children: warehouseHardwarePages.map((item) => ({
          key: `hardware-${item.pageKey}`,
          label: item.label,
          path: item.path,
          feishuPageKey: item.pageKey,
        })),
      },
      {
        key: "product-inventory",
        label: "成品库存",
        path: "/warehouse/product/dashboard",
        feishuPageKey: "",
        children: [
          { key: "product-summary", label: "产品汇总", path: "/warehouse/product/summary", feishuPageKey: "product-summary" },
          {
            key: "product-details",
            label: "产品明细",
            path: "",
            children: [
              { key: "product-detail-l-phenylalanine", label: "L-苯丙氨酸库存明细", path: "/warehouse/product/details/l-phenylalanine", feishuPageKey: "product-detail-l-phenylalanine" },
              { key: "product-detail-fumaric-acid", label: "霉酚酸库存明细", path: "/warehouse/product/details/fumaric-acid", feishuPageKey: "product-detail-fumaric-acid" },
              { key: "product-detail-l-tryptophan", label: "L-色氨酸库存明细", path: "/warehouse/product/details/l-tryptophan", feishuPageKey: "product-detail-l-tryptophan" },
              { key: "product-detail-mevastatin", label: "美伐他汀库存明细", path: "/warehouse/product/details/mevastatin", feishuPageKey: "product-detail-mevastatin" },
              { key: "product-detail-kitasamycin-hcl", label: "盐酸林可霉素库存明细", path: "/warehouse/product/details/kitasamycin-hcl", feishuPageKey: "product-detail-kitasamycin-hcl" },
              { key: "product-detail-doramectin", label: "多拉菌素库存明细", path: "/warehouse/product/details/doramectin", feishuPageKey: "product-detail-doramectin" },
              { key: "product-detail-lovastatin", label: "洛伐他汀库存明细", path: "/warehouse/product/details/lovastatin", feishuPageKey: "product-detail-lovastatin" },
              { key: "product-detail-florfenicol-premix", label: "氟苯尼考预混剂库存明细", path: "/warehouse/product/details/florfenicol-premix", feishuPageKey: "product-detail-florfenicol-premix" },
              { key: "product-detail-demeclocycline-hcl", label: "盐酸去甲金霉素库存明细", path: "/warehouse/product/details/demeclocycline-hcl", feishuPageKey: "product-detail-demeclocycline-hcl" },
              { key: "product-detail-fenbendazole-powder", label: "芬苯达唑粉剂库存明细", path: "/warehouse/product/details/fenbendazole-powder", feishuPageKey: "product-detail-fenbendazole-powder" },
            ],
          },
          { key: "product-inbound-detail", label: "成品入库明细", path: "/warehouse/product/inbound-detail", feishuPageKey: "product-inbound-detail" },
          { key: "product-inbound-ledger", label: "入库总账", path: "/warehouse/product/inbound-ledger", feishuPageKey: "product-inbound-ledger" },
          { key: "product-outbound-ledger", label: "出库台账", path: "/warehouse/product/outbound-ledger", feishuPageKey: "product-outbound-ledger" },
          { key: "product-shipping", label: "发货情况", path: "/warehouse/product/shipping", feishuPageKey: "product-shipping" },
        ],
      },
      { key: "warehouse-settings", label: "仓储设置", path: "/warehouse/settings", placement: "bottom", feishuPageKey: "" },
    ],
  },
  {
    key: "purchasing",
    moduleCode: "procurement",
    label: "采购管理",
    icon: "cart",
    path: "/purchasing",
    children: [
      {
        key: "request",
        label: "采购申请",
        path: "",
        children: [
          { key: "request-hardware", label: "五金材料", path: "/purchasing/request/hardware" },
          { key: "request-computer", label: "电脑材料", path: "/purchasing/request/computer" },
          { key: "request-office", label: "办公用品", path: "/purchasing/request/office" },
          { key: "request-raw-auxiliary", label: "原辅料", path: "/purchasing/request/raw-auxiliary" },
          { key: "request-chemical-glass", label: "化玻", path: "/purchasing/request/chemical-glass" },
          { key: "request-electrical", label: "电气", path: "/purchasing/request/electrical" },
          { key: "request-advertising-printing", label: "广告/印刷", path: "/purchasing/request/advertising-printing" },
          { key: "request-fire", label: "消防", path: "/purchasing/request/fire" },
          { key: "request-packaging", label: "包材", path: "/purchasing/request/packaging" },
          {
            key: "request-labor",
            label: "劳保",
            path: "",
            children: [
              { key: "request-labor-special", label: "特防", path: "/purchasing/request/labor-special" },
              { key: "request-labor-miscellaneous", label: "杂品", path: "/purchasing/request/labor-miscellaneous" },
            ],
          },
          { key: "request-urgent", label: "加急单", path: "/purchasing/request/urgent" },
        ],
      },
      { key: "material-library", label: "物料编码库", path: "/purchasing/material-library" },
      {
        key: "approval",
        label: "采购审批",
        path: "",
        children: [
          {
            key: "approval-hardware",
            label: "五金材料",
            path: "",
            children: [
              { key: "approval-hardware-hardware-warehouse", label: "五金库", path: "/purchasing/approval/hardware/hardware-warehouse" },
              { key: "approval-hardware-department-head", label: "部门负责人", path: "/purchasing/approval/hardware/department-head" },
              { key: "approval-hardware-responsible-leader", label: "分管领导", path: "/purchasing/approval/hardware/responsible-leader" },
              { key: "approval-hardware-supervising-leader", label: "主管领导", path: "/purchasing/approval/hardware/supervising-leader" },
              { key: "approval-hardware-general-manager", label: "总经理", path: "/purchasing/approval/hardware/general-manager" },
            ],
          },
          {
            key: "approval-computer",
            label: "电脑材料",
            path: "",
            children: [
              { key: "approval-computer-department-head", label: "部门负责人", path: "/purchasing/approval/computer/department-head" },
              { key: "approval-computer-responsible-leader", label: "分管领导", path: "/purchasing/approval/computer/responsible-leader" },
              { key: "approval-computer-supervising-leader", label: "主管领导", path: "/purchasing/approval/computer/supervising-leader" },
            ],
          },
          {
            key: "approval-office",
            label: "办公用品",
            path: "",
            children: [
              { key: "approval-office-department-head", label: "部门负责人", path: "/purchasing/approval/office/department-head" },
              { key: "approval-office-responsible-leader", label: "分管领导", path: "/purchasing/approval/office/responsible-leader" },
              { key: "approval-office-supervising-leader", label: "主管领导", path: "/purchasing/approval/office/supervising-leader" },
            ],
          },
          {
            key: "approval-raw-auxiliary",
            label: "原辅料",
            path: "",
            children: [
              { key: "approval-raw-auxiliary-department-head", label: "部门负责人", path: "/purchasing/approval/raw-auxiliary/department-head" },
              { key: "approval-raw-auxiliary-responsible-leader", label: "分管领导", path: "/purchasing/approval/raw-auxiliary/responsible-leader" },
              { key: "approval-raw-auxiliary-supervising-leader", label: "主管领导", path: "/purchasing/approval/raw-auxiliary/supervising-leader" },
            ],
          },
          {
            key: "approval-chemical-glass",
            label: "化玻",
            path: "",
            children: [
              { key: "approval-chemical-glass-department-head", label: "部门负责人", path: "/purchasing/approval/chemical-glass/department-head" },
              { key: "approval-chemical-glass-responsible-leader", label: "分管领导", path: "/purchasing/approval/chemical-glass/responsible-leader" },
              { key: "approval-chemical-glass-supervising-leader", label: "主管领导", path: "/purchasing/approval/chemical-glass/supervising-leader" },
            ],
          },
          {
            key: "approval-electrical",
            label: "电气",
            path: "",
            children: [
              { key: "approval-electrical-hardware-warehouse", label: "五金库", path: "/purchasing/approval/electrical/hardware-warehouse" },
              { key: "approval-electrical-equipment-power", label: "设备动力部会签", path: "/purchasing/approval/electrical/equipment-power" },
              { key: "approval-electrical-department-head", label: "部门负责人", path: "/purchasing/approval/electrical/department-head" },
              { key: "approval-electrical-responsible-leader", label: "分管领导", path: "/purchasing/approval/electrical/responsible-leader" },
              { key: "approval-electrical-supervising-leader", label: "主管领导", path: "/purchasing/approval/electrical/supervising-leader" },
            ],
          },
          {
            key: "approval-advertising-printing",
            label: "广告/印刷",
            path: "",
            children: [
              { key: "approval-advertising-printing-department-head", label: "部门负责人", path: "/purchasing/approval/advertising-printing/department-head" },
              { key: "approval-advertising-printing-responsible-leader", label: "分管领导", path: "/purchasing/approval/advertising-printing/responsible-leader" },
              { key: "approval-advertising-printing-supervising-leader", label: "主管领导", path: "/purchasing/approval/advertising-printing/supervising-leader" },
            ],
          },
          {
            key: "approval-fire",
            label: "消防",
            path: "",
            children: [
              { key: "approval-fire-department-head", label: "部门负责人", path: "/purchasing/approval/fire/department-head" },
              { key: "approval-fire-responsible-leader", label: "分管领导", path: "/purchasing/approval/fire/responsible-leader" },
              { key: "approval-fire-supervising-leader", label: "主管领导", path: "/purchasing/approval/fire/supervising-leader" },
            ],
          },
          {
            key: "approval-packaging",
            label: "包材",
            path: "",
            children: [
              { key: "approval-packaging-department-head", label: "部门负责人", path: "/purchasing/approval/packaging/department-head" },
              { key: "approval-packaging-responsible-leader", label: "分管领导", path: "/purchasing/approval/packaging/responsible-leader" },
              { key: "approval-packaging-supervising-leader", label: "主管领导", path: "/purchasing/approval/packaging/supervising-leader" },
            ],
          },
          {
            key: "approval-labor",
            label: "劳保",
            path: "",
            children: [
              {
                key: "approval-labor-special",
                label: "特防",
                path: "",
                children: [
                  { key: "approval-labor-special-safety-officer", label: "安全员", path: "/purchasing/approval/labor-special/safety-officer" },
                  { key: "approval-labor-special-department-head", label: "部门负责人", path: "/purchasing/approval/labor-special/department-head" },
                  { key: "approval-labor-special-responsible-leader", label: "分管领导", path: "/purchasing/approval/labor-special/responsible-leader" },
                ],
              },
              {
                key: "approval-labor-miscellaneous",
                label: "杂品",
                path: "",
                children: [
                  { key: "approval-labor-miscellaneous-department-head", label: "部门负责人", path: "/purchasing/approval/labor-miscellaneous/department-head" },
                  { key: "approval-labor-miscellaneous-responsible-leader", label: "分管领导", path: "/purchasing/approval/labor-miscellaneous/responsible-leader" },
                  { key: "approval-labor-miscellaneous-supervising-leader", label: "主管领导", path: "/purchasing/approval/labor-miscellaneous/supervising-leader" },
                ],
              },
            ],
          },
          {
            key: "approval-urgent",
            label: "加急单",
            path: "",
            children: [
              { key: "approval-urgent-hardware-warehouse", label: "五金库", path: "/purchasing/approval/urgent/hardware-warehouse" },
              { key: "approval-urgent-department-head", label: "部门负责人", path: "/purchasing/approval/urgent/department-head" },
              { key: "approval-urgent-responsible-leader", label: "分管领导", path: "/purchasing/approval/urgent/responsible-leader" },
              { key: "approval-urgent-supervising-leader", label: "主管领导", path: "/purchasing/approval/urgent/supervising-leader" },
              { key: "approval-urgent-finance-director", label: "财务总监", path: "/purchasing/approval/urgent/finance-director" },
              { key: "approval-urgent-general-manager", label: "总经理", path: "/purchasing/approval/urgent/general-manager" },
            ],
          },
        ],
      },
      { key: "supplier", label: "供应商管理", path: "/purchasing/supplier" },
      { key: "order", label: "采购订单", path: "/purchasing/order" },
      { key: "invoice-recognition", label: "发票识别", path: "/purchasing/invoice-recognition" },
      { key: "contract-summary", label: "合同汇总", path: "/purchasing/contract-summary" },
      {
        key: "contract-generation",
        label: "合同生成",
        path: "",
        children: [
          { key: "contract-generation-fixed-assets", label: "固定资产", path: "/purchasing/contract-generation/fixed-assets" },
          { key: "contract-generation-consumables", label: "耗材", path: "/purchasing/contract-generation/consumables" },
          { key: "contract-generation-hardware", label: "五金", path: "/purchasing/contract-generation/hardware" },
          { key: "contract-generation-raw-materials", label: "原材料", path: "/purchasing/contract-generation/raw-materials" },
        ],
      },
      { key: "settings", label: "采购设置", path: "/purchasing/settings", placement: "bottom", adminOnly: true },
    ],
  },
]

export function getModuleByKey(key: string): ModuleMenu | undefined {
  return moduleMenus.find((m) => m.key === key)
}

export function getAuthorizedModuleMenus(moduleCodes: string[] | undefined): ModuleMenu[] {
  const allowedCodes = new Set(moduleCodes || [])
  return moduleMenus.filter((module) => allowedCodes.has(module.moduleCode))
}
