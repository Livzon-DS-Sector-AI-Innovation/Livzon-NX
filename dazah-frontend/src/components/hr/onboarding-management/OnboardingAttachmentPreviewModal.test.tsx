/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

const mammothMock = vi.hoisted(() => ({
  convertToHtml: vi.fn(async () => ({
    value: '<p>简历正文</p><script>window.__docxXss = 1</script>',
  })),
}))

vi.mock('mammoth/mammoth.browser.js', () => ({
  __esModule: true,
  default: mammothMock,
}))

// 真实 antd Modal 依赖 rc-motion，happy-dom 下不会回调 afterOpenChange；
// 这里只替换 Modal，其余 antd 组件保持真实实现。
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  const React = await import('react')
  interface ModalProps {
    open?: boolean
    title?: ReactNode
    children?: ReactNode
    afterOpenChange?: (open: boolean) => void
  }
  function Modal({ open, title, children, afterOpenChange }: ModalProps) {
    const callback = React.useRef(afterOpenChange)
    callback.current = afterOpenChange
    React.useEffect(() => {
      callback.current?.(Boolean(open))
    }, [open])
    return open
      ? React.createElement(
          'div',
          { role: 'dialog' },
          React.createElement('h2', null, title),
          children,
        )
      : null
  }
  return { ...actual, Modal }
})

import OnboardingAttachmentPreviewModal from './OnboardingAttachmentPreviewModal'

interface Mounted {
  root: Root
  container: HTMLDivElement
}

let mounted: Mounted | null = null

function renderClient(element: ReactNode): Mounted {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  act(() => root.render(element))
  mounted = { root, container }
  return mounted
}

async function settle(): Promise<void> {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

afterEach(() => {
  if (mounted) {
    const current = mounted
    act(() => current.root.unmount())
    current.container.remove()
    mounted = null
  }
  document.body.innerHTML = ''
})

describe('OnboardingAttachmentPreviewModal docx safety', () => {
  it('renders docx html inside a sandboxed iframe with a restrictive CSP', async () => {
    renderClient(
      createElement(OnboardingAttachmentPreviewModal, {
        open: true,
        fileName: '候选人简历.docx',
        blob: new Blob(['docx-bytes']),
        onClose: vi.fn(),
      }),
    )

    await settle()

    const iframe = document.querySelector('iframe.docx-preview')
    expect(iframe).not.toBeNull()
    expect(iframe?.getAttribute('sandbox')).toBe('')

    const srcdoc = iframe?.getAttribute('srcdoc') ?? ''
    expect(srcdoc).toContain('简历正文')
    expect(srcdoc).toContain("default-src 'none'")
    expect(srcdoc).toContain('img-src data:')
  })

  it('never mounts untrusted docx html into the parent document', async () => {
    renderClient(
      createElement(OnboardingAttachmentPreviewModal, {
        open: true,
        fileName: '候选人简历.docx',
        blob: new Blob(['docx-bytes']),
        onClose: vi.fn(),
      }),
    )

    await settle()

    const preview = document.querySelector('.docx-preview')
    expect(preview?.tagName).toBe('IFRAME')
    expect(document.querySelector('.docx-preview p')).toBeNull()
    expect(document.querySelector('.docx-preview script')).toBeNull()
  })
})
