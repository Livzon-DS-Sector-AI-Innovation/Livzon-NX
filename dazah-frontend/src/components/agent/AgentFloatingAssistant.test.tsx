/* @vitest-environment happy-dom */

import { act, createElement } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { App } from "antd"

import {
  AgentFloatingAssistant,
  confirmationExecutionFeedback,
  confirmationNarrative,
  getAgentStreamTimeoutMs,
} from "./AgentFloatingAssistant"
import type { AgentConfirmation } from "@/lib/api/agent"
import { useAgentStore } from "@/stores/agent"

const mocks = vi.hoisted(() => ({
  streamAgentMessage: vi.fn(),
}))

vi.mock("@/lib/api/agent", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/agent")>()),
  streamAgentMessage: mocks.streamAgentMessage,
}))

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

describe("agent stream timeout", () => {
  it("allows image analysis more time than ordinary text requests", () => {
    expect(getAgentStreamTimeoutMs([])).toBe(90_000)
    expect(
      getAgentStreamTimeoutMs([{ content_type: "image/png" }]),
    ).toBe(300_000)
  })

  let root: Root
  let host: HTMLDivElement

  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true)
    useAgentStore.getState().startNewConversation()
    useAgentStore.getState().setOpen(true)
    host = document.createElement("div")
    document.body.append(host)
    root = createRoot(host)
    mocks.streamAgentMessage.mockImplementation(
      (_input: unknown, _handlers: unknown, options: { signal?: AbortSignal }) =>
        new Promise<void>((_resolve, reject) => {
          options.signal?.addEventListener(
            "abort",
            () => reject(new DOMException("Aborted", "AbortError")),
            { once: true },
          )
        }),
    )
  })

  afterEach(async () => {
    await act(async () => root.unmount())
    host.remove()
    useAgentStore.getState().startNewConversation()
    useAgentStore.getState().setOpen(false)
    mocks.streamAgentMessage.mockReset()
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it("uses the extended timeout and reports when image analysis is aborted", async () => {
    await act(async () => {
      root.render(
        createElement(
          App,
          null,
          createElement(AgentFloatingAssistant),
        ),
      )
    })

    const fileInput = host.querySelector<HTMLInputElement>('input[type="file"]')
    expect(fileInput).not.toBeNull()
    Object.defineProperty(fileInput, "files", {
      configurable: true,
      value: [new File(["image-bytes"], "sample.png", { type: "image/png" })],
    })
    await act(async () => {
      fileInput!.dispatchEvent(new Event("change", { bubbles: true }))
      await Promise.resolve()
    })

    const sendButton = [...host.querySelectorAll("button")].find((button) =>
      button.textContent?.includes("发送"),
    )
    expect(sendButton).not.toBeUndefined()
    await act(async () => sendButton!.click())
    expect(mocks.streamAgentMessage).toHaveBeenCalledOnce()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300_000)
    })

    expect(host.textContent).toContain("超过 300 秒")
  })
})
