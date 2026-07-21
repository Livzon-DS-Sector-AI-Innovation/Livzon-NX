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
  electrical: '电器',
  'labor-protection': '劳保',
}

export const approvalRoleLabels: Record<PurchaseApprovalRole, string> = {
  department_head: '部门负责人',
  responsible_leader: '分管领导',
}

export const approvalStepToRole = {
  'department-head': 'department_head',
  'responsible-leader': 'responsible_leader',
} as const

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
  pending_department_head: '待部门负责人审批',
  pending_responsible_leader: '待分管领导审批',
  approved: '已通过',
  rejected: '已驳回',
}

export const purchaseStatusColors: Record<PurchaseRequestStatus, string> = {
  draft: 'default',
  pending_department_head: 'processing',
  pending_responsible_leader: 'warning',
  approved: 'success',
  rejected: 'error',
}

export const defaultPurchaseRequestItem: PurchaseRequestItemInput = {
  product_name: '',
  specification: '',
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
