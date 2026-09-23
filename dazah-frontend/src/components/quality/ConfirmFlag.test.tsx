/* @vitest-environment happy-dom */
import React from 'react'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { describe, expect, it } from 'vitest'
import { ConfirmFlag, ConfirmFlagFromResult } from './ConfirmFlag'

function renderFlag(node: React.ReactNode): HTMLElement {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  act(() => root.render(node))
  return container
}

describe('ConfirmFlag', () => {
  it('renders a green check mark for confirmed values', () => {
    const el = renderFlag(<ConfirmFlag confirmed />)
    expect(el.querySelector('[aria-label="已确认"]')).toBeTruthy()
    expect(el.textContent).not.toContain('未确认')
  })

  it('renders a muted placeholder for unconfirmed or blank values', () => {
    for (const value of [false, null, undefined]) {
      const el = renderFlag(<ConfirmFlag confirmed={value} />)
      expect(el.querySelector('[aria-label="未确认"]')).toBeTruthy()
    }
  })

  it('treats only the approved review result as confirmed', () => {
    const confirmed = renderFlag(<ConfirmFlagFromResult value="approved" />)
    expect(confirmed.querySelector('[aria-label="已确认"]')).toBeTruthy()
    for (const value of [null, '', 'pending', 'rejected']) {
      const el = renderFlag(<ConfirmFlagFromResult value={value} />)
      expect(el.querySelector('[aria-label="未确认"]')).toBeTruthy()
    }
  })
})
