/* @vitest-environment happy-dom */

import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AgentEntryButton } from "./AgentEntryButton"

describe("AgentEntryButton", () => {
  let host: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true)
    host = document.createElement("div")
    document.body.append(host)
    root = createRoot(host)
  })

  afterEach(async () => {
    await act(async () => root.unmount())
    host.remove()
    vi.unstubAllGlobals()
  })

  it("shows the Agent identity and opens the assistant", async () => {
    const onClick = vi.fn()
    await act(async () => root.render(<AgentEntryButton onClick={onClick} />))

    const button = host.querySelector("button")
    expect(button?.getAttribute("aria-label")).toBe("打开中枢助手")
    expect(button?.textContent).toContain("LIVZON")
    expect(button?.textContent).toContain("智能助手")
    await act(async () => button?.click())
    expect(onClick).toHaveBeenCalledOnce()
  })

  it("identifies a minimized conversation and keeps loading non-interactive", async () => {
    await act(async () => root.render(<AgentEntryButton minimized />))
    expect(host.querySelector("button")?.getAttribute("aria-label")).toBe("展开中枢助手")
    expect(host.querySelector("button")?.textContent).toContain("继续对话")

    await act(async () => root.render(<AgentEntryButton loading />))
    expect(host.querySelector("button")?.getAttribute("aria-label")).toBe("正在加载中枢助手")
    expect(host.querySelector("button")?.disabled).toBe(true)
  })
})
