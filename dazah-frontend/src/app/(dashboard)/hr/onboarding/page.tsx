import { OnboardingManagementPage } from '@/components/hr/onboarding-management'
import { HrQueryProvider } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default function OnboardingPage() {
  return (
    <HrQueryProvider>
      <OnboardingManagementPage />
    </HrQueryProvider>
  )
}
