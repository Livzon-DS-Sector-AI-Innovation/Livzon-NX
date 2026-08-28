import { ProductQualityStandardPage, QualityQueryProvider } from '@/components/quality'
import { notFound } from 'next/navigation'

export const dynamic = 'force-dynamic'

const PRODUCT_QUALITY_LABELS: Record<string, string> = {
  mfn: '霉酚酸',
  dljs: '多拉菌素',
  lftt: '洛伐他汀',
  mftt: '美伐他汀',
  yslkms: '盐酸林可霉素',
  bbas: 'L-苯丙氨酸',
  sas: 'L-色氨酸',
}

export default async function ProductQualityProductPage({
  params,
}: {
  params: Promise<{ productCode: string }>
}) {
  const { productCode } = await params
  const productLabel = PRODUCT_QUALITY_LABELS[productCode]

  if (!productLabel) {
    notFound()
  }

  return <QualityQueryProvider><ProductQualityStandardPage productCode={productCode} productLabel={productLabel} /></QualityQueryProvider>
}
