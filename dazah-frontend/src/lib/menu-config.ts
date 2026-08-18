import {
  BATCH_PRODUCTION_LINE_GROUPS,
  BATCH_PRODUCT_NAMES,
  getBatchProductPath,
  getBatchProductionLinePath,
} from "./production-batch-lines"
import { ENERGY_DATA_PAGES } from "./energy-data-pages"

export interface SubMenuItem {
  key: string
  label: string
  path: string
  children?: SubMenuItem[]   // 嵌套子菜单 → Ant Design SubMenu
  disabled?: boolean         // 灰显占位，功能未开发
  placement?: "bottom"       // 置底显示，例如模块设置入口
  adminOnly?: boolean         // 仅系统管理员可见
  feishuPageKey?: string      // 可绑定飞书只读数据表的稳定页面标识
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
          {
            key: "batches-products",
            label: "按产品",
            path: "",
            children: BATCH_PRODUCT_NAMES.map((productName) => ({
              key: `batches-product-${productName}`,
              label: productName,
              path: getBatchProductPath(productName),
            })),
          },
          ...BATCH_PRODUCTION_LINE_GROUPS.map((group) => ({
            key: `batches-${group.key}`,
            label: group.label,
            path: "",
            children: group.codes.map((code) => ({
              key: `batches-line-${code}`,
              label: code,
              path: getBatchProductionLinePath(code),
            })),
          })),
        ],
      },
      { key: "workshop-203", label: "203 工序工作台", path: "/production/workshop-203" },
      { key: "fermentation", label: "发酵与种子培养", path: "/production/fermentation", feishuPageKey: "production.fermentation" },
      { key: "shift-log", label: "生产日志与交接", path: "/production/shift-log", feishuPageKey: "production.shift-log" },
      { key: "plan", label: "生产计划", path: "/production/plan" },
      { key: "process", label: "工艺规程（开发中）", path: "/production/process" },
      { key: "records", label: "生产记录（开发中）", path: "/production/records", feishuPageKey: "production.records" },
      { key: "balance", label: "物料平衡（开发中）", path: "/production/balance" },
      { key: "label-verification", label: "标签复核", path: "/production/label-verification" },
      { key: "pressure", label: "压差统计", path: "/production/pressure" },
      { key: "feishu-data", label: "飞书数据", path: "/production/data", feishuPageKey: "production.data" },
      { key: "feishu-config", label: "飞书配置", path: "/production/feishu-config", placement: "bottom" },
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
      { key: "dossier-writer", label: "卷宗编写", path: "/registration/dossier-writer" },
      { key: "validation-audit", label: "验证文件审核", path: "/registration/validation-audit" },
      { key: "review", label: "申报进度查询", path: "/registration/review" },
      { key: "authorization-letter", label: "授权书管理", path: "/registration/authorization-letter" },
      { key: "supplementary-reply", label: "发补回复", path: "/registration/supplementary-reply" },
      { key: "reference-standard", label: "对照物质说明表", path: "/registration/reference-standard" },
      { key: "regulation", label: "法规跟踪", path: "/registration/regulation" },
    ],
  },
  {
    key: "quality",
    moduleCode: "quality",
    label: "质量管理",
    icon: "check-circle",
    path: "/quality",
    children: [
      { key: "deviations", label: "偏差管理", path: "/quality/deviations" },
      { key: "capas", label: "CAPA管理", path: "/quality/capas" },
      { key: "department-contacts", label: "部门联系人", path: "/quality/department-contacts" },
      { key: "change", label: "变更控制", path: "/quality/change" },
      { key: "validation", label: "验证与确认", path: "/quality/validation" },
      { key: "inspection", label: "检验管理", path: "/quality/inspection" },
      { key: "oos-oot", label: "OOS/OOT管理", path: "/quality/oos-oot" },
      { key: "suppliers", label: "供应商管理", path: "/quality/suppliers" },
      { key: "complaints", label: "投诉管理", path: "/quality/complaints" },
      { key: "return-recalls", label: "退货召回", path: "/quality/return-recalls" },
      { key: "product-quality", label: "产品质量标准", path: "/quality/product-quality" },
      { key: "feishu-data", label: "飞书数据", path: "/quality/data" },
      { key: "feishu-settings", label: "飞书设置", path: "/quality/feishu-settings", placement: "bottom" },
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
      {
        key: "old-factory",
        label: "老厂",
        path: "/hr/departments",
        children: [
          { key: "departments", label: "部门管理", path: "/hr/departments" },
          { key: "profile", label: "员工档案", path: "/hr/profile" },
          { key: "roster", label: "员工花名册", path: "/hr/roster" },
          { key: "onboarding", label: "入职台账", path: "/hr/onboarding" },
          { key: "departure", label: "离职台账", path: "/hr/departure" },
          { key: "offboarding", label: "离职管理", path: "/hr/offboarding" },
          { key: "attendance", label: "考勤管理（开发中）", path: "/hr/attendance" },
          {
            key: "training",
            label: "培训管理",
            path: "/hr/training",
            children: [
              { key: "onboarding-training", label: "新员工入职培训", path: "/hr/training/onboarding" },
              { key: "training-notification", label: "培训通知", path: "/hr/training/notification" },
              { key: "sign-in-sheet", label: "培训签到表", path: "/hr/training/sign-in" },
              { key: "ai-exam", label: "AI 出题", path: "/hr/training/ai-exam" },
              { key: "annual-plan", label: "年度培训计划", path: "/hr/training/annual-plan" },
              { key: "training-ledger", label: "培训台账", path: "/hr/training/ledger" },
            ],
          },
        ],
      },
      {
        key: "new-factory",
        label: "新厂",
        path: "#",
        children: [
          { key: "new-departments", label: "部门管理", path: "/hr/new/departments" },
          { key: "new-profile", label: "员工档案", path: "/hr/new/profile" },
          { key: "new-onboarding", label: "入职台账", path: "/hr/new/onboarding" },
          { key: "new-departure", label: "离职台账", path: "/hr/new/departure" },
          { key: "new-offboarding", label: "离职管理", path: "/hr/new/offboarding" },
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
      { key: "raw-material", label: "成品", path: "/warehouse/raw-material", feishuPageKey: "warehouse.raw_material" },
      { key: "packaging", label: "原辅料及包材", path: "/warehouse/packaging", feishuPageKey: "warehouse.packaging" },
      { key: "product", label: "五金", path: "/warehouse/product", feishuPageKey: "warehouse.product" },
      { key: "feishu-config", label: "飞书配置", path: "/warehouse/feishu-config", placement: "bottom" },
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
