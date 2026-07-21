import { notFound } from 'next/navigation'
import {
  PurchaseRequestFormClient,
  purchaseCategoryLabels,
} from '@/components/purchasing'
import { fetchPurchaseRequests } from '@/lib/api/purchasing'
import { getAuthHeaders } from '@/lib/auth'
import type { PurchaseRequestCategory } from '@/types/purchasing'

export const dynamic = 'force-dynamic'

const DEFAULT_PAGE_SIZE = 20

interface PurchaseRequestCategoryPageProps {
  params: Promise<{ category: string }>
}

export function generateStaticParams() {
  return Object.keys(purchaseCategoryLabels).map((category) => ({ category }))
}

export default async function PurchaseRequestCategoryPage({
  params,
}: PurchaseRequestCategoryPageProps) {
  const { category } = await params
  const categoryLabel = purchaseCategoryLabels[category as PurchaseRequestCategory]

  if (!categoryLabel) {
    notFound()
  }

  const response = await fetchPurchaseRequests({
    category: category as PurchaseRequestCategory,
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
    <PurchaseRequestFormClient
      category={category as PurchaseRequestCategory}
      categoryLabel={categoryLabel}
      initialRequests={response.data}
      initialTotal={Number(response.meta?.total ?? response.data.length)}
    />
  )
}
