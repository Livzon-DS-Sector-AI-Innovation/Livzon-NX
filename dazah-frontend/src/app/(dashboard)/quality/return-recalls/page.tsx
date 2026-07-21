import { ExternalQualityManagementPage, ExternalQualityQueryProvider } from '@/components/quality'

export const dynamic = 'force-dynamic'

export default function QualityReturnRecallsPage() {
  return <ExternalQualityQueryProvider><ExternalQualityManagementPage initialTab="return-recalls" /></ExternalQualityQueryProvider>
}
