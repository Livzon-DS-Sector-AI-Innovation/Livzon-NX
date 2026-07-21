import { AntdProvider } from "@/components/AntdProvider"
import { AppShell } from "@/components/layout/AppShell"
import { getCurrentUser } from "@/actions/auth"
import { redirect } from "next/navigation"
import '@/lib/dayjs-config'

export const dynamic = 'force-dynamic'

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const user = await getCurrentUser()

  if (!user) {
    redirect('/login')
  }

  return (
    <AntdProvider>
      <AppShell user={user}>{children}</AppShell>
    </AntdProvider>
  )
}
