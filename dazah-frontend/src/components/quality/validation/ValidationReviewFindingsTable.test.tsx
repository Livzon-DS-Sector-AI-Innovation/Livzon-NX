/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { ValidationReviewFindingsTable } from './ValidationReviewFindingsTable'

import type { ValidationReviewFinding } from '@/types/quality'

let container: HTMLElement
let root: Root

function renderTable(findings: ValidationReviewFinding[], loading = false) {
  act(() => {
    root.render(<ValidationReviewFindingsTable findings={findings} loading={loading} />)
  })
}

describe('ValidationReviewFindingsTable', () => {
  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    document.body.removeChild(container)
  })

  it('renders empty state when no findings', () => {
    renderTable([])
    expect(container.textContent).toContain('未发现问题')
  })

  it('renders findings with severity and category labels', () => {
    const findings: ValidationReviewFinding[] = [
      {
        category: 'version_mismatch',
        severity: 'high',
        location: '引用文件',
        quote: 'SMP-QA-105/02',
        quote_verified: false,
        basis_source: null,
        basis_match_type: 'related',
        detail: '引用版本与目录现行版不一致',
      },
      {
        category: 'format_issue',
        severity: 'medium',
        location: '方案文档编号',
        quote: 'VP-01 / VP-02',
        quote_verified: true,
        basis_source: null,
        basis_match_type: 'document',
        detail: '文件名与正文编号不一致',
      },
    ]
    renderTable(findings)
    expect(container.textContent).toContain('引用版本不一致')
    expect(container.textContent).toContain('格式/编号问题')
    expect(container.textContent).toContain('高')
    expect(container.textContent).toContain('中')
    expect(container.textContent).toContain('SMP-QA-105/02')
    expect(container.textContent).toContain('引文未核')
    expect(container.textContent).toContain('已核')
  })
})
