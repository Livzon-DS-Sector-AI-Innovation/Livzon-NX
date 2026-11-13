/* @vitest-environment happy-dom */

import { act } from "react"
import { createRoot } from "react-dom/client"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { AuthorizationReasonInput } from "./AuthorizationReasonInput"

const presets = ["岗位权限调整", "数据范围调整", "恢复角色基线"] as const
let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true)
  container = document.createElement("div")
  document.body.append(container)
  root = createRoot(container)
})

afterEach(async () => {
  await act(async () => root.unmount())
  container.remove()
  vi.unstubAllGlobals()
})

it("passes manual input to the caller and disables both input methods when requested", async () => {
  const onChange = vi.fn()
  await act(async () => root.render(<AuthorizationReasonInput value="" onChange={onChange} presets={presets} />))

  const input = container.querySelector("input")!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, "临时工作授权")
    input.dispatchEvent(new Event("input", { bubbles: true }))
  })
  expect(onChange).toHaveBeenCalledWith("临时工作授权")

  await act(async () => root.render(<AuthorizationReasonInput value="临时工作授权" onChange={onChange} presets={presets} disabled />))

  expect(input.disabled).toBe(true)
  expect(container.querySelector<HTMLButtonElement>('button[aria-label="快捷授权调整原因"]')?.disabled).toBe(true)
})
