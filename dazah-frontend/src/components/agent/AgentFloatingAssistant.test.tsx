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
import type { AgentConfirmation, AgentSessionItem } from "@/lib/api/agent"
import { useAgentStore } from "@/stores/agent"
import { useAgentEntryPreferencesStore } from "@/stores/agent-entry-preferences"
import { useAuthStore } from "@/stores/auth"

const mocks = vi.hoisted(() => ({
  streamAgentMessage: vi.fn(),
  fetchAgentSessions: vi.fn(),
  fetchAgentSession: vi.fn(),
  archiveAgentSession: vi.fn(),
}))

vi.mock("@/lib/api/agent", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/agent")>()),
  streamAgentMessage: mocks.streamAgentMessage,
  fetchAgentSessions: mocks.fetchAgentSessions,
  fetchAgentSession: mocks.fetchAgentSession,
  archiveAgentSession: mocks.archiveAgentSession,
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

describe("agent session history", () => {
  const session: AgentSessionItem = {
    id: "00000000-0000-0000-0000-000000000002",
    title: "质量偏差查询",
    channel: "feishu",
    status: "active",
    created_at: "2026-08-05T10:00:00Z",
    updated_at: "2026-08-05T11:00:00Z",
    message_count: 3,
    pending_confirmation_count: 2,
    last_message_preview: "查询本月偏差记录",
  }
  let root: Root
  let host: HTMLDivElement

  beforeEach(() => {
    useAuthStore.getState().clearUser()
    useAgentStore.getState().startNewConversation()
    useAgentStore.getState().setOpen(true)
    mocks.fetchAgentSessions.mockResolvedValue({
      items: [session, { ...session, id: "empty-session", title: null, channel: "web", last_message_preview: null, pending_confirmation_count: 0 }],
      page: 1,
      page_size: 20,
      total: 2,
    })
    mocks.fetchAgentSession.mockResolvedValue({
      session,
      messages: [{ role: "assistant", content: "已恢复历史对话" }],
      confirmations: [],
    })
    host = document.createElement("div")
    document.body.append(host)
    root = createRoot(host)
  })

  afterEach(async () => {
    useAuthStore.getState().clearUser()
    await act(async () => root.unmount())
    host.remove()
    useAgentStore.getState().startNewConversation()
    useAgentStore.getState().setOpen(false)
    mocks.fetchAgentSessions.mockReset()
    mocks.fetchAgentSession.mockReset()
    mocks.archiveAgentSession.mockReset()
    vi.restoreAllMocks()
  })

  async function openHistory() {
    await act(async () => {
      root.render(createElement(App, null, createElement(AgentFloatingAssistant)))
    })
    const historyButton = host.querySelector<HTMLButtonElement>('button[aria-label="查看历史会话"]')
    expect(historyButton).not.toBeNull()
    expect(host.querySelector('button[aria-label="查看能力与运行"]')).toBeNull()
    expect(document.body.textContent).not.toContain("Livzon 能力与运行")
    await act(async () => historyButton!.click())
  }

  it("preserves an expanded conversation while hiding its minimized entry", async () => {
    useAgentStore.getState().setDraft("保留草稿")
    await act(async () => root.render(createElement(App, null, createElement(AgentFloatingAssistant))))
    try {
      await act(async () => useAgentEntryPreferencesStore.getState().setVisible(false))
      expect(host.querySelector('.agent-floating-assistant')).not.toBeNull()
      expect(useAgentStore.getState().draft).toBe("保留草稿")
      await act(async () => useAgentStore.getState().setMinimized(true))
      expect(host.querySelector('.agent-floating-entry-button')).toBeNull()
      await act(async () => useAgentEntryPreferencesStore.getState().setVisible(true))
      const entry = host.querySelector<HTMLButtonElement>('.agent-floating-entry-button')
      expect(entry).not.toBeNull()
      await act(async () => entry!.click())
      expect(host.querySelector('.agent-floating-assistant')).not.toBeNull()
      expect(useAgentStore.getState().draft).toBe("保留草稿")
    } finally {
      await act(async () => useAgentEntryPreferencesStore.getState().setVisible(true))
      localStorage.removeItem('dazah.agent.floating-entry-visible')
    }
  })

  it("starts a new conversation before slow archiving and preserves new messages", async () => {
    let finishArchive!: () => void
    mocks.archiveAgentSession.mockImplementation(() => new Promise<void>((resolve) => { finishArchive = resolve }))
    useAgentStore.getState().loadConversation({ sessionId: session.id, messages: [{ role: "assistant", content: "旧会话" }], confirmations: [] })
    await act(async () => root.render(createElement(App, null, createElement(AgentFloatingAssistant))))
    await act(async () => host.querySelector<HTMLButtonElement>('button[aria-label="开启新对话"]')!.click())
    expect(mocks.archiveAgentSession).toHaveBeenCalledWith(session.id)
    expect(useAgentStore.getState().sessionId).toBeNull()
    expect(host.textContent).not.toContain("旧会话")
    act(() => useAgentStore.getState().addMessage({ role: "user", content: "新请求" }))
    await act(async () => finishArchive())
    expect(host.textContent).toContain("新请求")
  })

  it("sends current page filters with a question without a fixed business scope", async () => {
    const previousUrl = window.location.pathname + window.location.search
    window.history.replaceState(null, "", "/production/batches?status=open&token=private")
    useAuthStore.getState().setUser({ id: "test-user", name: "用户", role: "admin" })
    mocks.streamAgentMessage.mockResolvedValue(undefined)
    try {
      await act(async () => root.render(createElement(App, null, createElement(AgentFloatingAssistant))))
      const suggestion = [...host.querySelectorAll("button")].find((button) => button.textContent?.includes("供应商"))
      expect(suggestion).toBeDefined()
      await act(async () => suggestion!.click())
      expect(mocks.streamAgentMessage).toHaveBeenCalled()
      expect(mocks.streamAgentMessage.mock.calls.at(-1)?.[0].context).toEqual({
        entry: "floating-assistant",
        page_context: { route_path: "/production/batches", filters: { status: "open" } },
      })
    } finally {
      window.history.replaceState(null, "", previousUrl)
      mocks.streamAgentMessage.mockReset()
    }
  })

  it("limits business suggestions to assigned page grants and reacts to revocation", async () => {
    useAuthStore.getState().setUser({
      id: "test-user", name: "只读用户", role: "user",
      page_permissions: [{page_key: "purchasing:supplier", module_code: "procurement",
        permissions: ["access", "query"], sensitive_actions: [],
        data_scope: {scope_type: "all"}, source: "role"}],
    })
    await act(async () => root.render(createElement(App, null, createElement(AgentFloatingAssistant))))
    expect(host.textContent).toContain("查询供应商清单")
    expect(host.textContent).not.toContain("查询质量偏差报告记录")
    expect(host.textContent).not.toContain("查看飞书同步状态")
    await act(async () => useAuthStore.getState().setUser({id: "test-user", name: "已撤权用户", role: "user", page_permissions: []}))
    expect(host.textContent).not.toContain("查询供应商清单")
    expect(host.textContent).not.toContain("试试这样提问")
  })

  it("renders session summaries and fallbacks without the deprecated List warning", async () => {
    const errors = vi.spyOn(console, "error")
    await openHistory()

    expect(mocks.fetchAgentSessions).toHaveBeenCalledOnce()
    expect(document.body.textContent).toContain("质量偏差查询")
    expect(document.body.textContent).toContain("查询本月偏差记录")
    expect(document.body.textContent).toContain("飞书 · 3 条消息")
    expect(document.body.textContent).toContain(new Date(session.updated_at).toLocaleString())
    expect(document.body.textContent).toContain("2 项待确认")
    expect(document.body.textContent).toContain("未命名对话")
    expect(document.body.textContent).toContain("暂无消息摘要")
    expect(document.body.textContent).toContain("Web · 3 条消息")
    expect(errors.mock.calls.flat().join(" ")).not.toContain("[antd: List]")
  })

  it("restores the selected conversation", async () => {
    await openHistory()
    const restoreButtons = [...document.body.querySelectorAll("button")].filter(
      (button) => button.textContent === "继续对话",
    )
    expect(restoreButtons).toHaveLength(2)
    await act(async () => restoreButtons[0].click())

    expect(mocks.fetchAgentSession).toHaveBeenCalledWith(session.id)
    expect(useAgentStore.getState().sessionId).toBe(session.id)
    expect(host.textContent).toContain("已恢复历史对话")
  })

  it("shows the empty state when there are no sessions", async () => {
    mocks.fetchAgentSessions.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 })
    await openHistory()

    expect(document.body.textContent).toContain("还没有历史会话")
    expect([...document.body.querySelectorAll("button")].some(
      (button) => button.textContent === "继续对话",
    )).toBe(false)
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
