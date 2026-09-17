import { act } from 'react'
import { expect } from 'vitest'

export async function chooseBatchWorkshop(code: string) {
  const input = document.querySelector<HTMLInputElement>('#workshop_code')
  expect(input).not.toBeNull()
  await act(async () => {
    input!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await new Promise(resolve => setTimeout(resolve, 50))
  })
  const option = Array.from(document.querySelectorAll<HTMLElement>('.ant-select-item-option'))
    .find(item => item.textContent === `${code}车间`)
  expect(option).toBeDefined()
  await act(async () => {
    option!.click()
    await new Promise(resolve => setTimeout(resolve, 30))
  })
}
