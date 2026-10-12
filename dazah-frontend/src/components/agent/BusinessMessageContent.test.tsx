import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { BusinessMessageContent } from "./BusinessMessageContent"

describe("assistant message presentation", () => {
  it("hides legacy task and evidence details while preserving the answer", () => {
    const content = [
      "能力介绍 query_access_scope：已完成",
      "任务：查询当前用户可访问的平台模块、工具与权限范围",
      "我可以帮助你查询库存和处理业务草稿。",
      "来源：实时授权目录；时间：2026-10-12T01:50:29+00:00；证据：",
      "665e7debf64248e9aace7cfbc643c4fc",
      '查询条件：{"query":"当前用户可以查询哪些模块","limit":50}',
      "任务需要你确认后才会执行。",
    ].join("\n\n")
    const html = renderToStaticMarkup(createElement(BusinessMessageContent, { content }))
    expect(html).toContain("我可以帮助你查询库存和处理业务草稿。")
    expect(html).toContain("任务需要你确认后才会执行。")
    for (const detail of ["能力介绍", "query_access_scope", "任务：", "来源：", "查询条件：", "665e7debf", "2026-10-12"]) {
      expect(html).not.toContain(detail)
    }
  })

  it("does not render evidence metadata as a data basis section", () => {
    const metadata = { evidence: {
      sources: [{ operation: "agent.get_my_access_scope", params: { limit: 50 }, ok: true }],
      queried_at: "2026-10-12T01:51:10Z", scope: ["warehouse"], truncated: true,
    } }
    const html = renderToStaticMarkup(createElement(BusinessMessageContent, { content: "可查询仓储记录。", metadata }))
    expect(html).toContain("可查询仓储记录。")
    for (const detail of ["数据依据", "agent.get_my_access_scope", "查询时间", "请求模块范围", "agent-evidence"]) {
      expect(html).not.toContain(detail)
    }
    expect(metadata.evidence.sources).toHaveLength(1)
  })

  it("keeps business tables and confirmation warnings", () => {
    const content = "| 产品 | 数量 |\n| --- | --- |\n| 物料A | 12 |\n\n待确认，尚未执行。"
    const html = renderToStaticMarkup(createElement(BusinessMessageContent, { content }))
    expect(html).toContain("物料A")
    expect(html).toContain("12")
    expect(html).toContain("待确认，尚未执行。")
  })
})
