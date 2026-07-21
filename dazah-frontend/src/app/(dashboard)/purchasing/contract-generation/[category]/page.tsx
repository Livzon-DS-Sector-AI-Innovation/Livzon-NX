import { notFound } from 'next/navigation'
import { ContractGenerationClient } from '@/components/purchasing'

const contractCategoryLabels = {
  'fixed-assets': '固定资产',
  consumables: '耗材',
  hardware: '五金',
  'raw-materials': '原材料',
} as const

type ContractCategory = keyof typeof contractCategoryLabels

interface ContractGenerationCategoryPageProps {
  params: Promise<{ category: string }>
}

export function generateStaticParams() {
  return Object.keys(contractCategoryLabels).map((category) => ({ category }))
}

export default async function ContractGenerationCategoryPage({
  params,
}: ContractGenerationCategoryPageProps) {
  const { category } = await params
  const categoryLabel = contractCategoryLabels[category as ContractCategory]

  if (!categoryLabel) {
    notFound()
  }

  return <ContractGenerationClient category={category as ContractCategory} categoryLabel={categoryLabel} />
}
