import { act } from 'react'
import { expect } from 'vitest'

export async function openNoticeDetails(summary: string) {
  const notice = [...document.querySelectorAll<HTMLElement>('[data-platform-notice]')]
    .find((node) => node.textContent?.includes(summary))
  expect(notice, summary).toBeTruthy()
  expect(notice!.querySelector('.ant-alert-description')).toBeNull()
  const rules = [...notice!.querySelectorAll<HTMLButtonElement>('button')]
    .find((button) => button.textContent?.includes('了解访问规则'))
  expect(rules, 'persistent notices have a rules entry').toBeTruthy()
  await act(async () => rules!.click())
}
