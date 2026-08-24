/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

import Workshop203FermentationPage from './page'

describe('Workshop203FermentationPage', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders the fermentation stage navigation page', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<Workshop203FermentationPage />)
    })
    const text = container.textContent || ''
    expect(text).toContain('发酵液放罐')
    expect(text).toContain('酸化过滤')
  })
})
