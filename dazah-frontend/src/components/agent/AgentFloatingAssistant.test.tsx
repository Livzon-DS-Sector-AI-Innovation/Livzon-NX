import { describe, expect, it } from "vitest"

import {
  confirmationExecutionFeedback,
  confirmationNarrative,
} from "./AgentFloatingAssistant"
import type { AgentConfirmation } from "@/lib/api/agent"

const nativeConfirmation: AgentConfirmation = {
  id: "00000000-0000-0000-0000-000000000001",
  operation: "sheets +cells-set",
  summary: "修改飞书电子表格",
  risk_level: "medium",
  status: "pending",
  expires_at: "2026-08-05T12:00:00Z",
  request_payload: {
    resource_domain: "feishu_native",
    resource: "飞书资源 …ample",
    reason: "修改既有值",
    impact_count: 3,
  },
}

describe("Feishu native confirmation feedback", () => {
  it("shows the resource, impact and risk reason", () => {
    expect(confirmationNarrative(nativeConfirmation)).toContain("飞书资源 …ample")
    expect(confirmationNarrative(nativeConfirmation)).toContain("预计影响 3 项")
    expect(confirmationNarrative(nativeConfirmation)).toContain("修改既有值")
  })

  it("does not claim success when execution fails", () => {
    expect(
      confirmationExecutionFeedback(nativeConfirmation, {
        ok: false,
        operation: nativeConfirmation.operation,
      }),
    ).toContain("执行失败")
  })

  it("distinguishes an unverified write", () => {
    const feedback = confirmationExecutionFeedback(nativeConfirmation, {
      ok: false,
      operation: nativeConfirmation.operation,
      data: { status: "verification_failed" },
    })
    expect(feedback).toContain("回读验证未通过")
    expect(feedback).toContain("未确认")
    expect(feedback).not.toContain("已执行")
  })
})
