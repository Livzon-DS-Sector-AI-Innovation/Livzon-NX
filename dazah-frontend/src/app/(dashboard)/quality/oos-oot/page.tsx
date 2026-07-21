import { OosOotManagementPage, OosOotQueryProvider } from '@/components/quality'

export const dynamic = 'force-dynamic'

export default function QualityOosOotPage() {
  return (
    <OosOotQueryProvider>
      <OosOotManagementPage />
    </OosOotQueryProvider>
  )
}
