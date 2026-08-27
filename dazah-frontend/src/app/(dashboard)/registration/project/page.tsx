import { ProjectOverviewClient, RegistrationQueryProvider } from '@/components/registration'

export const dynamic = 'force-dynamic'

export default function ProjectPage() {
  return (
    <RegistrationQueryProvider>
      <ProjectOverviewClient />
    </RegistrationQueryProvider>
  )
}
