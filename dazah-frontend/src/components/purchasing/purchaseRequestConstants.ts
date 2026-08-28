import type {
  PurchaseApprovalRole,
  PurchaseApprovalView,
  PurchaseRequestCategory,
  PurchaseRequestItemInput,
  PurchaseRequestStatus,
} from '@/types/purchasing'

export const purchaseCategoryLabels: Record<PurchaseRequestCategory, string> = {
  hardware: '五金材料',
  computer: '电脑材料',
  office: '办公用品',
  'raw-auxiliary': '原辅料',
  'chemical-glass': '化玻',
  electrical: '电气',
  'advertising-printing': '广告/印刷',
  fire: '消防',
  packaging: '包材',
  'labor-special': '特防',
  'labor-miscellaneous': '杂品',
  urgent: '加急单',
}

export const materialFieldPurchaseCategories: ReadonlySet<PurchaseRequestCategory> =
  new Set([
    'hardware',
    'electrical',
    'chemical-glass',
    'raw-auxiliary',
    'packaging',
    'labor-special',
    'labor-miscellaneous',
    'fire',
  ])

export function usesMaterialFields(category: PurchaseRequestCategory) {
  return materialFieldPurchaseCategories.has(category)
}

export const approvalRoleLabels: Record<PurchaseApprovalRole, string> = {
  hardware_warehouse: '五金库',
  equipment_power: '设备动力部（何学斌、安伟）',
  safety_officer: '安全员',
  department_head: '部门负责人',
  responsible_leader: '分管领导',
  supervising_leader: '主管领导',
  finance_director: '财务总监',
  general_manager: '总经理',
}

export const approvalStepToRole = {
  'hardware-warehouse': 'hardware_warehouse',
  'equipment-power': 'equipment_power',
  'safety-officer': 'safety_officer',
  'department-head': 'department_head',
  'responsible-leader': 'responsible_leader',
  'supervising-leader': 'supervising_leader',
  'finance-director': 'finance_director',
  'general-manager': 'general_manager',
} satisfies Record<string, PurchaseApprovalRole>

export const approvalRoleToStep: Record<PurchaseApprovalRole, string> = {
  hardware_warehouse: 'hardware-warehouse',
  equipment_power: 'equipment-power',
  safety_officer: 'safety-officer',
  department_head: 'department-head',
  responsible_leader: 'responsible-leader',
  supervising_leader: 'supervising-leader',
  finance_director: 'finance-director',
  general_manager: 'general-manager',
}

export const purchaseApprovalWorkflows: Record<
  PurchaseRequestCategory,
  readonly PurchaseApprovalRole[]
> = {
  hardware: [
    'hardware_warehouse',
    'department_head',
    'responsible_leader',
    'supervising_leader',
    'general_manager',
  ],
  electrical: [
    'hardware_warehouse',
    'equipment_power',
    'department_head',
    'responsible_leader',
    'supervising_leader',
  ],
  'labor-special': [
    'safety_officer',
    'department_head',
    'responsible_leader',
  ],
  urgent: [
    'hardware_warehouse',
    'department_head',
    'responsible_leader',
    'supervising_leader',
    'finance_director',
    'general_manager',
  ],
  computer: ['department_head', 'responsible_leader', 'supervising_leader'],
  office: ['department_head', 'responsible_leader', 'supervising_leader'],
  'raw-auxiliary': ['department_head', 'responsible_leader', 'supervising_leader'],
  'chemical-glass': ['department_head', 'responsible_leader', 'supervising_leader'],
  'advertising-printing': [
    'department_head',
    'responsible_leader',
    'supervising_leader',
  ],
  fire: ['department_head', 'responsible_leader', 'supervising_leader'],
  packaging: ['department_head', 'responsible_leader', 'supervising_leader'],
  'labor-miscellaneous': [
    'department_head',
    'responsible_leader',
    'supervising_leader',
  ],
}

export const approvalRoleRequiredApprovals: Partial<
  Record<PurchaseApprovalRole, number>
> = {
  equipment_power: 2,
}

export const approvalRoleHints: Partial<Record<PurchaseApprovalRole, string>> = {
  equipment_power:
    '设备动力部会签需何学斌、安伟分别完成同意；当前不校验登录身份，请按实际审批人填写姓名。',
}

export const approvalViewLabels: Record<PurchaseApprovalView, string> = {
  pending: '待审批',
  completed: '审批完成',
  rejected: '审批驳回',
}

export const approvalViews = Object.keys(
  approvalViewLabels
) as PurchaseApprovalView[]

export const purchaseStatusLabels: Record<PurchaseRequestStatus, string> = {
  draft: '草稿',
  pending_hardware_warehouse: '待五金库审批',
  pending_equipment_power: '待设备动力部审批',
  pending_safety_officer: '待安全员审批',
  pending_department_head: '待部门负责人审批',
  pending_responsible_leader: '待分管领导审批',
  pending_supervising_leader: '待主管领导审批',
  pending_finance_director: '待财务总监审批',
  pending_general_manager: '待总经理审批',
  approved: '已通过',
  rejected: '已驳回',
}

export const purchaseStatusColors: Record<PurchaseRequestStatus, string> = {
  draft: 'default',
  pending_hardware_warehouse: 'processing',
  pending_equipment_power: 'processing',
  pending_safety_officer: 'processing',
  pending_department_head: 'processing',
  pending_responsible_leader: 'warning',
  pending_supervising_leader: 'warning',
  pending_finance_director: 'warning',
  pending_general_manager: 'warning',
  approved: 'success',
  rejected: 'error',
}

export const defaultPurchaseRequestItem: PurchaseRequestItemInput = {
  product_name: '',
  specification: '',
  material_code: '',
  material_description: '',
  rule_model: '',
  purpose: '',
  material: '',
  brand: '',
  quantity: 1,
  unit: '',
  unit_price: 0,
  remarks: '',
}

export const purchaseCategories = Object.keys(
  purchaseCategoryLabels
) as PurchaseRequestCategory[]

export const normalPurchaseCategories = purchaseCategories.filter(
  (category) => category !== 'urgent'
)

export function formatMoney(value: string | number | null | undefined) {
  const numberValue = Number(value ?? 0)
  if (!Number.isFinite(numberValue)) return '¥0.00'
  return `¥${numberValue.toFixed(2)}`
}

export function calculateLineAmount(
  quantity: string | number | null | undefined,
  unitPrice: string | number | null | undefined
) {
  const quantityValue = Number(quantity ?? 0)
  const unitPriceValue = Number(unitPrice ?? 0)
  if (!Number.isFinite(quantityValue) || !Number.isFinite(unitPriceValue)) {
    return 0
  }
  return Number((quantityValue * unitPriceValue).toFixed(2))
}

type PurchaseAmountItem = Pick<PurchaseRequestItemInput, 'quantity' | 'unit_price'>
type PurchaseAmountGroup = {
  items?: ReadonlyArray<PurchaseAmountItem | null | undefined> | null
}

export function calculateItemsTotal(
  items: ReadonlyArray<PurchaseAmountItem | null | undefined> | null | undefined,
) {
  return (items ?? []).reduce(
    (sum, item) => sum + calculateLineAmount(item?.quantity, item?.unit_price),
    0,
  )
}

export function calculateGroupsTotal(
  groups: ReadonlyArray<PurchaseAmountGroup | null | undefined> | null | undefined,
) {
  return (groups ?? []).reduce(
    (sum, group) => sum + calculateItemsTotal(group?.items),
    0,
  )
}
