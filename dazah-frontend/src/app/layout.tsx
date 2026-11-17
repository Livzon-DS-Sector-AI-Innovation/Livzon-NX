import type { Metadata } from "next"
import "./globals.css"
import "./workspace-identity-transition.css"
import { appearanceInitScript } from "@/lib/appearance"
import { WorkspaceEntryTransition } from "@/components/auth/WorkspaceEntryTransition"
import { WorkspaceIdentitySync } from "@/components/auth/WorkspaceIdentitySync"
import { workspaceIdentityTransitionInitScript } from "@/lib/workspaceIdentityTransition"

export const metadata: Metadata = {
  title: "工厂管理平台",
  description: "原料药制药厂综合业务管理平台",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="zh-CN" className="h-full" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: appearanceInitScript }} />
        <script dangerouslySetInnerHTML={{ __html: workspaceIdentityTransitionInitScript }} />
      </head>
      <body className="h-full antialiased">
        <WorkspaceIdentitySync />
        <WorkspaceEntryTransition>{children}</WorkspaceEntryTransition>
      </body>
    </html>
  )
}
