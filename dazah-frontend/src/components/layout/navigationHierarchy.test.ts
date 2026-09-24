import { describe, expect, it } from "vitest"
import type { ModuleMenu } from "@/lib/menu-config"
import { getNavigationHierarchy } from "./navigationHierarchy"

const moduleMenu: ModuleMenu = {
  key: "quality", moduleCode: "quality", label: "质量管理", icon: "quality", path: "/quality",
  children: [
    { key: "home", label: "模块首页", path: "/quality" },
    { key: "records", label: "记录管理", path: "", children: [
      { key: "ledger", label: "偏差台账", path: "/quality/deviations" },
    ] },
  ],
}

describe("getNavigationHierarchy", () => {
  it("builds clickable ancestors and menu choices for a detail route", () => {
    const result = getNavigationHierarchy(moduleMenu, "/quality/deviations/123")
    expect(result.levels.map((level) => level.label)).toEqual(["质量管理", "记录管理", "偏差台账", "详情"])
    expect(result.levels[0].path).toBe("/quality")
    expect(result.levels[1].options).toEqual([{ label: "偏差台账", path: "/quality/deviations" }])
    expect(result.levels[2].path).toBe("/quality/deviations")
    expect(result.modulePath).toBe("/quality")
  })

  it("links a menu page to the module entry", () => {
    const result = getNavigationHierarchy(moduleMenu, "/quality/deviations")
    expect(result.levels[0].path).toBe("/quality")
  })

  it("uses the first visible page when the module landing page is unavailable", () => {
    const restricted = { ...moduleMenu, children: [moduleMenu.children[1]] }
    const result = getNavigationHierarchy(restricted, "/quality/deviations/123")
    expect(result.modulePath).toBe("/quality/deviations")
    expect(result.levels[0].path).toBe("/quality/deviations")
    expect(result.levels[1].options).toEqual([{ label: "偏差台账", path: "/quality/deviations" }])
  })
})
