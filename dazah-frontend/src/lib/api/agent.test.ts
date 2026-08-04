import { afterEach, describe, expect, it, vi } from "vitest"

import { streamAgentMessage } from "./agent"

function v2Event(
  type: string,
  sequence: number,
  data: Record<string, unknown>,
): string {
  return [
    `event: ${type}`,
    `data: ${JSON.stringify({
      protocol_version: "2.0",
      event_id: `event-${sequence}`,
      trace_id: "trace-1",
      run_id: "run-1",
      sequence,
      occurred_at: "2026-07-30T08:00:00Z",
      type,
      data,
    })}`,
    "",
    "",
  ].join("\n")
}

function streamResponse(body: string): Response {
  const encoded = new TextEncoder().encode(body)
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoded)
        controller.close()
      },
    }),
    {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    },
  )
}

describe("streamAgentMessage AgentBackend V2 protocol", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("consumes accepted, text_delta and finished envelopes", async () => {
    const onStart = vi.fn()
    const onDelta = vi.fn()
    const onDone = vi.fn()
    const response = [
      v2Event("accepted", 1, { session_id: "session-1" }),
      v2Event("text_delta", 2, { text: "你好" }),
      v2Event("finished", 3, {
        session_id: "session-1",
        message: { role: "assistant", content: "你好" },
        pending_confirmations: [],
        tool_trace: [],
      }),
    ].join("")
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(streamResponse(response)))

    await streamAgentMessage(
      { message: "测试" },
      { onStart, onDelta, onDone },
    )

    expect(onStart).toHaveBeenCalledWith({ session_id: "session-1" })
    expect(onDelta).toHaveBeenCalledWith("你好")
    expect(onDone).toHaveBeenCalledWith(
      expect.objectContaining({ session_id: "session-1" }),
    )
  })

  it("rejects removed V1 stream events", async () => {
    const response = [
      "event: start",
      'data: {"session_id":"session-1"}',
      "",
      "event: done",
      'data: {"message":{"role":"assistant","content":"旧协议"}}',
      "",
      "",
    ].join("\n")
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(streamResponse(response)))

    await expect(
      streamAgentMessage({ message: "测试" }, {}),
    ).rejects.toThrow("无效的 V2 流事件")
  })

  it("rejects non-monotonic V2 event sequences", async () => {
    const response = [
      v2Event("accepted", 1, { session_id: "session-1" }),
      v2Event("text_delta", 1, { text: "重复" }),
    ].join("")
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(streamResponse(response)))

    await expect(
      streamAgentMessage({ message: "测试" }, {}),
    ).rejects.toThrow("事件顺序或运行标识不一致")
  })

  it("reports non-sensitive capability and tool progress", async () => {
    const onProgress = vi.fn()
    const response = [
      v2Event("accepted", 1, { session_id: "session-1" }),
      v2Event("capability_search", 2, { status: "started" }),
      v2Event("tool_call", 3, {
        operation: "quality.create_deviation",
        call_id: "call-1",
        status: "started",
      }),
      v2Event("tool_result", 4, {
        operation: "quality.create_deviation",
        call_id: "call-1",
        status: "completed",
        ok: true,
      }),
      v2Event("finished", 5, {
        session_id: "session-1",
        message: { role: "assistant", content: "完成" },
        pending_confirmations: [],
        tool_trace: [],
      }),
    ].join("")
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(streamResponse(response)))

    await streamAgentMessage({ message: "测试" }, { onProgress })

    expect(onProgress).toHaveBeenNthCalledWith(1, {
      type: "capability_search",
      data: { status: "started" },
    })
    expect(onProgress).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ type: "tool_call" }),
    )
    expect(onProgress).toHaveBeenNthCalledWith(
      3,
      expect.objectContaining({ type: "tool_result" }),
    )
  })

  it("rejects unsupported V2 protocol versions", async () => {
    const response = v2Event("accepted", 1, {
      session_id: "session-1",
    }).replace('"protocol_version":"2.0"', '"protocol_version":"1.0"')
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(streamResponse(response)))

    await expect(
      streamAgentMessage({ message: "测试" }, {}),
    ).rejects.toThrow("无效的 V2 流事件")
  })
})
