import { HrQueryProvider, OnboardingManagementPage } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default function OnboardingManagementRoute() {
  return (
    <HrQueryProvider>
      <OnboardingManagementPage />
    </HrQueryProvider>
  )
}
