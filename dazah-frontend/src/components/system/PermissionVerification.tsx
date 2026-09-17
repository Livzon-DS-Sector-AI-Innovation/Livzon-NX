"use client"

import { PermissionRolloutManager } from "./PermissionRolloutManager"
import { PagePermissionDiagnostics } from "./PagePermissionDiagnostics"
import { PagePermissionHealthPanel } from "./PagePermissionHealthPanel"

/** Read-only view of each module's permission integration gate. */
export function PermissionVerification() {
  return <div className="space-y-4">
    <PagePermissionDiagnostics />
    <PagePermissionHealthPanel />
    <PermissionRolloutManager />
  </div>
}
