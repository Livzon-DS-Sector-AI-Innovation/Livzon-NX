"use client"

import { Button, Tag } from "antd"

export type AgentArtifact =
  | { type: "automation_list"; queryRef: string }
  | { type: "automation_detail"; automationId: string; version: number | null }
  | { type: "run_timeline"; runId: string | null }
  | { type: "push_delivery_list"; queryRef: string }
  | { type: "audit_diff"; auditId: string }
  | { type: "confirmation_preview"; confirmationId: string }

const artifactLabels: Record<AgentArtifact["type"], string> = {
  automation_list: "自动化列表",
  automation_detail: "自动化详情",
  run_timeline: "运行时间线",
  push_delivery_list: "投递记录",
  audit_diff: "审计差异",
  confirmation_preview: "确认预览",
}

const artifactActions: Record<AgentArtifact["type"], string> = {
  automation_list: "刷新列表",
  automation_detail: "查看详情",
  run_timeline: "查看进度",
  push_delivery_list: "查看投递",
  audit_diff: "查看修改记录",
  confirmation_preview: "查看确认项",
}

function isArtifact(value: unknown): value is AgentArtifact {
  if (!value || typeof value !== "object" || !("type" in value)) return false
  const type = (value as { type?: unknown }).type
  return typeof type === "string" && type in artifactLabels
}

export function collectAgentArtifacts(value: unknown): AgentArtifact[] {
  const found: AgentArtifact[] = []
  const seen = new Set<string>()

  function visit(item: unknown) {
    if (Array.isArray(item)) {
      item.forEach(visit)
      return
    }
    if (!item || typeof item !== "object") return
    if (isArtifact(item)) {
      const key = JSON.stringify(item)
      if (!seen.has(key)) {
        seen.add(key)
        found.push(item)
      }
    }
    Object.values(item).forEach(visit)
  }

  visit(value)
  return found
}

function artifactReference(artifact: AgentArtifact): string | null {
  switch (artifact.type) {
    case "automation_detail":
      return artifact.version === null
        ? artifact.automationId
        : `${artifact.automationId} · v${artifact.version}`
    case "run_timeline":
      return artifact.runId
    case "automation_list":
    case "push_delivery_list":
      return artifact.queryRef
    case "audit_diff":
      return artifact.auditId
    case "confirmation_preview":
      return artifact.confirmationId
  }
}

export function AutomationArtifacts({
  artifacts,
  onAction,
}: {
  artifacts: AgentArtifact[]
  onAction?: (artifact: AgentArtifact) => void
}) {
  if (artifacts.length === 0) return null
  return (
    <div className="mt-3 space-y-2" aria-label="Livzon 结构化结果">
      {artifacts.map((artifact) => {
        const reference = artifactReference(artifact)
        return (
          <section
            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2"
            key={JSON.stringify(artifact)}
          >
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium text-[var(--color-text-primary)]">
                {artifactLabels[artifact.type]}
              </span>
              <div className="flex items-center gap-2">
                <Tag color="purple" className="!m-0">
                  已生成
                </Tag>
                {onAction && (
                  <Button
                    type="link"
                    size="small"
                    className="!h-auto !p-0"
                    onClick={() => onAction(artifact)}
                  >
                    {artifactActions[artifact.type]}
                  </Button>
                )}
              </div>
            </div>
            {reference && (
              <div className="mt-1 truncate text-xs text-[var(--color-text-secondary)]">
                {reference}
              </div>
            )}
          </section>
        )
      })}
    </div>
  )
}
