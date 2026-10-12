import { describe, expect, it } from "vitest"
import { buildAgentPageHint } from "./pageContext"

describe("agent page hints", () => {
  it("keeps the current route and supported query hints without identity or credentials", () => {
    expect(buildAgentPageHint({ pathname: "/production/batches", search: "?keyword=API&status=open&token=private&user_id=spoof#ignored" }))
      .toEqual({ route_path: "/production/batches", filters: { keyword: "API", status: "open" } })
  })

  it("drops oversized values and unrelated query parameters", () => {
    expect(buildAgentPageHint({ pathname: "/quality", search: `?keyword=${"a".repeat(201)}&return_to=/settings&page=2` }))
      .toEqual({ route_path: "/quality", filters: { page: "2" } })
  })
})
