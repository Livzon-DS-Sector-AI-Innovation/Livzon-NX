import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { ServerApiError } from '@/lib/api/server/registration'

const mocks = vi.hoisted(() => ({
  fetchCertificateWorkbookOverviewServer: vi.fn(),
  fetchCertificateReminderSettingsServer: vi.fn(),
  fetchCertificateReminderRecipientsServer: vi.fn(),
  fetchCertificateSheetDetailServer: vi.fn(),
  fetchProjectLedgerSheetDetailServer: vi.fn(),
  fetchDeclarationProgressSheetDetailServer: vi.fn(),
}))

const navMocks = vi.hoisted(() => ({
  notFound: vi.fn(),
}))

vi.mock('@/lib/api/server/registration', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/server/registration')>()
  return { ...actual, ...mocks }
})

vi.mock('@/components/registration', () => ({
  CertificateDashboardPage: () => React.createElement('div', null, 'cert-dashboard'),
  CertificateSheetPage: () => React.createElement('div', null, 'cert-sheet'),
  ProjectLedgerSheetPage: () => React.createElement('div', null, 'project-ledger-sheet'),
  DeclarationProgressPage: () => React.createElement('div', null, 'declaration-progress-page'),
}))

vi.mock('next/navigation', () => ({
  notFound: navMocks.notFound,
}))

function defaultReminderSettings() {
  return {
    is_enabled: false,
    reminder_days: 90,
    recipient_open_id: null,
    recipient_name: null,
    recipient_department: null,
    pending_count: 0,
  }
}

describe('registration xlsx 缺失降级', () => {
  it('ServerApiError 携带 HTTP 状态码且 instanceof Error', () => {
    const err = new ServerApiError('台账文件不存在', 404)
    expect(err).toBeInstanceOf(Error)
    expect(err.name).toBe('ServerApiError')
    expect(err.message).toBe('台账文件不存在')
    expect(err.status).toBe(404)
  })

  it('证书台账 overview 404 时渲染错误提示而非崩溃', async () => {
    mocks.fetchCertificateWorkbookOverviewServer.mockRejectedValueOnce(
      new ServerApiError('药政证书台账文件不存在', 404)
    )
    mocks.fetchCertificateReminderSettingsServer.mockResolvedValueOnce(
      defaultReminderSettings()
    )
    mocks.fetchCertificateReminderRecipientsServer.mockResolvedValueOnce([])

    const { default: Page } = await import('./certificate-management/page')
    const markup = renderToStaticMarkup(await Page())
    expect(markup).toContain('药政证书台账加载失败')
  })

  it('证书台账空数据时渲染导入引导空态', async () => {
    mocks.fetchCertificateWorkbookOverviewServer.mockResolvedValueOnce({
      workbook_name: '2. 药政证书台账.xlsx',
      updated_at: null,
      total_records: 0,
      sheet_count: 4,
      issuer_count: 0,
      product_count: 0,
      expired_count: 0,
      due_90_count: 0,
      total_pages: 0,
      sheet_summaries: [],
      upcoming_expirations: [],
      recent_issued: [],
    })
    mocks.fetchCertificateReminderSettingsServer.mockResolvedValueOnce(
      defaultReminderSettings()
    )
    mocks.fetchCertificateReminderRecipientsServer.mockResolvedValueOnce([])

    const { default: Page } = await import('./certificate-management/page')
    const markup = renderToStaticMarkup(await Page())
    expect(markup).toContain('暂无药政证书台账数据')
    expect(markup).toContain('cert-dashboard')
  })

  it('申报台账子表 404 时调用 notFound 而非抛给错误边界', async () => {
    mocks.fetchProjectLedgerSheetDetailServer.mockRejectedValueOnce(
      new ServerApiError('申报台账子表不存在', 404)
    )
    navMocks.notFound.mockImplementation(() => {
      throw new Error('NEXT_NOT_FOUND')
    })

    const { default: Page } = await import('./project-ledger/[sheetKey]/page')
    await expect(
      Page({ params: Promise.resolve({ sheetKey: 'international-associated-review' }) }),
    ).rejects.toThrow('NEXT_NOT_FOUND')
    expect(navMocks.notFound).toHaveBeenCalled()
  })

  it('申报台账子表 500 时重新抛出交由全局错误边界处理', async () => {
    mocks.fetchProjectLedgerSheetDetailServer.mockRejectedValueOnce(
      new ServerApiError('内部错误', 500)
    )
    navMocks.notFound.mockClear()

    const { default: Page } = await import('./project-ledger/[sheetKey]/page')
    await expect(
      Page({ params: Promise.resolve({ sheetKey: 'international-associated-review' }) }),
    ).rejects.toThrow('内部错误')
    expect(navMocks.notFound).not.toHaveBeenCalled()
  })

  it('证书子表 404 时调用 notFound', async () => {
    mocks.fetchCertificateSheetDetailServer.mockRejectedValueOnce(
      new ServerApiError('证书子表不存在', 404)
    )
    navMocks.notFound.mockImplementation(() => {
      throw new Error('NEXT_NOT_FOUND')
    })

    const { default: Page } = await import('./certificate-management/[sheetKey]/page')
    await expect(
      Page({ params: Promise.resolve({ sheetKey: 'international-registration' }) }),
    ).rejects.toThrow('NEXT_NOT_FOUND')
    expect(navMocks.notFound).toHaveBeenCalled()
  })

  it('申报进度子表 404 时调用 notFound', async () => {
    mocks.fetchDeclarationProgressSheetDetailServer.mockRejectedValueOnce(
      new ServerApiError('申报进度子表不存在', 404)
    )
    navMocks.notFound.mockImplementation(() => {
      throw new Error('NEXT_NOT_FOUND')
    })

    const { default: Page } = await import('./declaration-progress/[sheetKey]/page')
    await expect(
      Page({ params: Promise.resolve({ sheetKey: 'import' }) }),
    ).rejects.toThrow('NEXT_NOT_FOUND')
    expect(navMocks.notFound).toHaveBeenCalled()
  })
})
