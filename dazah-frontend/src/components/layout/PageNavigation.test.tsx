import { describe, expect, it, vi } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import type { ModuleMenu } from "@/lib/menu-config"

const navigation = vi.hoisted(() => ({ pathname: "/production/batches/workshop/101-1", query: "" }))

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useSearchParams: () => new URLSearchParams(navigation.query),
}))

import { PageNavigation } from "./PageNavigation"

const modules: ModuleMenu[] = [{
  key: "production", moduleCode: "production", label: "生产管理", icon: "factory", path: "/production",
  children: [
    { key: "overview", label: "生产管理概览", path: "/production" },
    { key: "batches", label: "批次管理", path: "", children: [
      { key: "workshop", label: "101一车间（菌种）", path: "/production/batches/workshop/101-1" },
    ] },
  ],
}]

describe("PageNavigation", () => {
  it("uses breadcrumbs without separate return buttons", () => {
    const html = renderToStaticMarkup(<PageNavigation modules={modules} />)
    expect(html).toContain('href="/production"')
    expect(html).toContain("批次管理")
    expect(html).toContain("101一车间（菌种）")
    expect(html).toContain("展开批次管理菜单")
    expect(html).not.toContain("返回上一级")
    expect(html).not.toContain("返回模块入口")
  })

  it("restores list filters through the breadcrumb on a detail page", () => {
    navigation.pathname = "/production/batches/workshop/101-1/detail"
    navigation.query = "returnTo=%2Fproduction%2Fbatches%2Fworkshop%2F101-1%3Fpage%3D4%26page_size%3D50"
    const html = renderToStaticMarkup(<PageNavigation modules={modules} />)
    expect(html).toContain('href="/production/batches/workshop/101-1?page=4&amp;page_size=50"')
    navigation.pathname = "/production/batches/workshop/101-1"
    navigation.query = ""
  })

  it("adds a list breadcrumb when the list is outside the module menu", () => {
    navigation.pathname = "/registration/validation-audit/7"
    navigation.query = "returnTo=%2Fregistration%2Fvalidation-audit%3Fpage%3D3"
    const registration: ModuleMenu = {
      key: "registration", moduleCode: "registration", label: "注册管理", icon: "file", path: "/registration",
      children: [{ key: "overview", label: "注册概览", path: "/registration" }],
    }
    const html = renderToStaticMarkup(<PageNavigation modules={[registration]} />)
    expect(html).toContain('href="/registration/validation-audit?page=3"')
    expect(html).toContain('>列表</a>')
    navigation.pathname = "/production/batches/workshop/101-1"
    navigation.query = ""
  })
})
