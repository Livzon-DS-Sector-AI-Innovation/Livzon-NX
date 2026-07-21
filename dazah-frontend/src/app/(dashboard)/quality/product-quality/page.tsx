import { ExternalQualityManagementPage, ExternalQualityQueryProvider } from '@/components/quality'

export const dynamic = 'force-dynamic'

export default function QualityProductQualityPage() {
  return <ExternalQualityQueryProvider><ExternalQualityManagementPage initialTab="product-quality" /></ExternalQualityQueryProvider>
}
