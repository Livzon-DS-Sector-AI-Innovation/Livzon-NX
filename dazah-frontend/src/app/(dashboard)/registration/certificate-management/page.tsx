import { CertificateDashboardPage } from '@/components/registration'
import {
  fetchCertificateReminderRecipientsServer,
  fetchCertificateReminderSettingsServer,
  fetchCertificateWorkbookOverviewServer,
} from '@/lib/api/server/registration'

export const dynamic = 'force-dynamic'

export default async function RegistrationCertificateManagementPage() {
  const [overview, reminderSettings, reminderRecipients] = await Promise.all([
    fetchCertificateWorkbookOverviewServer(),
    fetchCertificateReminderSettingsServer(),
    fetchCertificateReminderRecipientsServer(),
  ])

  return (
    <CertificateDashboardPage
      overview={overview}
      reminderSettings={reminderSettings}
      reminderRecipients={reminderRecipients}
    />
  )
}
