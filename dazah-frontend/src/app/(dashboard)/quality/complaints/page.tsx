import { ExternalQualityManagementPage, ExternalQualityQueryProvider } from '@/components/quality'

export const dynamic = 'force-dynamic'

export default function QualityComplaintsPage() {
  return <ExternalQualityQueryProvider><ExternalQualityManagementPage initialTab="complaints" /></ExternalQualityQueryProvider>
}
