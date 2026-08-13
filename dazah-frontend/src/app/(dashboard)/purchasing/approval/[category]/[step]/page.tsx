import { notFound } from 'next/navigation'
import {
  PurchaseApprovalClient,
  approvalRoleToStep,
  approvalStepToRole,
  purchaseApprovalWorkflows,
  purchaseCategoryLabels,
} from '@/components/purchasing'
import { fetchPurchaseRequests } from '@/lib/api/purchasing'
import { getAuthHeaders } from '@/lib/auth'
import type { PurchaseApprovalRole, PurchaseRequestCategory } from '@/types/purchasing'

export const dynamic = 'force-dynamic'

const DEFAULT_PAGE_SIZE = 20

interface PurchaseApprovalPageProps {
  params: Promise<{ category: string; step: string }>
}

export function generateStaticParams() {
  return Object.entries(purchaseApprovalWorkflows).flatMap(([category, roles]) =>
    roles.map((role) => ({
      category,
      step: approvalRoleToStep[role],
    }))
  )
}

export default async function PurchaseApprovalPage({
  params,
}: PurchaseApprovalPageProps) {
  const { category, step } = await params
  const categoryLabel = purchaseCategoryLabels[category as PurchaseRequestCategory]
  const approvalRole = approvalStepToRole[step as keyof typeof approvalStepToRole]
  const workflow = purchaseApprovalWorkflows[category as PurchaseRequestCategory]

  const roleIsInWorkflow = approvalRole
    ? workflow?.some((role) => role === approvalRole)
    : false

  if (!categoryLabel || !approvalRole || !roleIsInWorkflow) {
    notFound()
  }

  const response = await fetchPurchaseRequests({
    category: category as PurchaseRequestCategory,
    approval_role: approvalRole as PurchaseApprovalRole,
    approval_view: 'pending',
    page: 1,
    page_size: DEFAULT_PAGE_SIZE,
  }, await getAuthHeaders()).catch(() => ({
    code: 200,
    message: 'success',
    data: [],
    meta: {
      page: 1,
      page_size: DEFAULT_PAGE_SIZE,
      total: 0,
    },
  }))

  return (
    <PurchaseApprovalClient
      category={category as PurchaseRequestCategory}
      categoryLabel={categoryLabel}
      approvalRole={approvalRole as PurchaseApprovalRole}
      initialRequests={response.data}
      initialTotal={Number(response.meta?.total ?? response.data.length)}
    />
  )
}
