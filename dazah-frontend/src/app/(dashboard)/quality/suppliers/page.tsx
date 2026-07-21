import { ExternalQualityManagementPage, ExternalQualityQueryProvider } from '@/components/quality'

export const dynamic = 'force-dynamic'

export default function QualitySuppliersPage() {
  return <ExternalQualityQueryProvider><ExternalQualityManagementPage initialTab="suppliers" /></ExternalQualityQueryProvider>
}
