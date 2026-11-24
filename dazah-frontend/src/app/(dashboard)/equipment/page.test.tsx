import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// next/navigation 的跳转信号：真实实现抛出内部错误终止渲染，这里用同样的方式中断
const navigation = vi.hoisted(() => ({
  redirect: vi.fn((url: string) => {
    throw new Error(`REDIRECT:${url}`)
  }),
  notFound: vi.fn(() => {
    throw new Error('NOT_FOUND')
  }),
}))
const auth = vi.hoisted(() => ({ getCurrentUser: vi.fn() }))

vi.mock('next/navigation', () => navigation)
vi.mock('@/actions/auth', () => auth)
// 三个功能模块的页面各自有测试；这里只关心入口页把哪个模块、哪个车间交给它们
vi.mock('./_modules/assets-view', () => ({
  default: ({ workshopCode }: { workshopCode: string }) => (
    <div data-testid="assets-view" data-workshop={workshopCode} />
  ),
}))
vi.mock('./_modules/inspection-view', () => ({
  default: ({ workshopCode, workshopLabel }: { workshopCode: string; workshopLabel: string }) => (
    <div data-testid="inspection-view" data-workshop={workshopCode} data-label={workshopLabel} />
  ),
}))
vi.mock('./_modules/repair-view', () => ({
  default: ({ workshopCode, workshopLabel }: { workshopCode: string; workshopLabel: string }) => (
    <div data-testid="repair-view" data-workshop={workshopCode} data-label={workshopLabel} />
  ),
}))
vi.mock('@/components/equipment', () => ({
  WorkshopNavBlocks: ({ pageKey }: { pageKey: string }) => (
    <nav data-testid="workshop-blocks" data-page-key={pageKey} />
  ),
}))

import AssetsRedirect from './assets/page'
import EquipmentConsolePage from './page'
import InspectionRedirect from './inspection/page'
import InspectionWorkshopRedirect from './inspection/[workshop]/page'

const renderPage = async (searchParams: Record<string, string | undefined>) =>
  renderToStaticMarkup(
    await EquipmentConsolePage({ searchParams: Promise.resolve(searchParams) }),
  )

const redirectTarget = async (render: () => Promise<unknown>) => {
  try {
    await render()
  } catch (error) {
    return (error as Error).message
  }
  return 'NO_REDIRECT'
}

const grant = (pageKey: string) => ({
  id: 'u-1',
  role: 'user',
  page_permissions: [{ page_key: pageKey, module_code: 'equipment', permissions: ['access', 'query'] }],
})

beforeEach(() => {
  vi.clearAllMocks()
  auth.getCurrentUser.mockResolvedValue(null)
})

describe('EquipmentConsolePage（设备工作台入口）', () => {
  it('renders the ledger module for the requested workshop and tells the blocks its page key', async () => {
    const html = await renderPage({ workshop: '101-1', module: 'assets' })

    expect(html).toContain('data-testid="assets-view" data-workshop="101-1"')
    expect(html).toContain('data-testid="workshop-blocks" data-page-key="equipment:assets"')
  })

  it('renders the inspection and repair modules with the workshop label', async () => {
    const inspection = await renderPage({ workshop: '101-1', module: 'inspection' })
    expect(inspection).toContain('data-testid="inspection-view" data-workshop="101-1" data-label="101一车间"')

    const repair = await renderPage({ workshop: '201-2-dr', module: 'maintenance' })
    expect(repair).toContain('data-testid="repair-view"')
    expect(repair).toContain('data-label="201二车间（DR）"')
    expect(repair).toContain('data-page-key="equipment:maintenance"')
  })

  it('keeps a well-formed unknown workshop code and falls back to the default workshop otherwise', async () => {
    const custom = await renderPage({ workshop: 'ab-12', module: 'assets' })
    expect(custom).toContain('data-workshop="ab-12"')

    const fallback = await renderPage({ workshop: '../etc', module: 'assets' })
    expect(fallback).toContain('data-workshop="201-1"')
  })

  it('redirects to the first module the user may enter when the module is missing or unknown', async () => {
    auth.getCurrentUser.mockResolvedValue(grant('equipment:assets'))

    expect(await redirectTarget(() => renderPage({ workshop: '101-1' })))
      .toBe('REDIRECT:/equipment?module=assets&workshop=101-1')
    expect(await redirectTarget(() => renderPage({ workshop: '101-1', module: 'personnel' })))
      .toBe('REDIRECT:/equipment?module=assets&workshop=101-1')
  })

  it('lands on inspection first for administrators and visitors without any grant', async () => {
    auth.getCurrentUser.mockResolvedValue({ id: 'u-1', role: 'admin', page_permissions: [] })
    expect(await redirectTarget(() => renderPage({ workshop: '203' })))
      .toBe('REDIRECT:/equipment?module=inspection&workshop=203')

    auth.getCurrentUser.mockResolvedValue(null)
    expect(await redirectTarget(() => renderPage({}))).toBe('REDIRECT:/equipment?module=inspection')
  })
})

describe('旧设备路径收敛到工作台对应模块', () => {
  it('redirects /equipment/inspection to the inspection module and keeps the workshop', async () => {
    expect(await redirectTarget(() => InspectionRedirect({ searchParams: Promise.resolve({ workshop: '101-1' }) })))
      .toBe('REDIRECT:/equipment?module=inspection&workshop=101-1')
    expect(await redirectTarget(() => InspectionRedirect({ searchParams: Promise.resolve({}) })))
      .toBe('REDIRECT:/equipment?module=inspection')
  })

  it('rejects a malformed workshop segment in the old inspection path', async () => {
    expect(await redirectTarget(() => InspectionWorkshopRedirect({ params: Promise.resolve({ workshop: 'not a code' }) })))
      .toBe('NOT_FOUND')
    expect(await redirectTarget(() => InspectionWorkshopRedirect({ params: Promise.resolve({ workshop: '103' }) })))
      .toBe('REDIRECT:/equipment?workshop=103&module=inspection')
  })

  it('keeps legacy ledger links pointing at the ledger module', async () => {
    expect(await redirectTarget(() => AssetsRedirect({ searchParams: Promise.resolve({ workshop: '101-2' }) })))
      .toBe('REDIRECT:/equipment?workshop=101-2&module=assets')
    expect(await redirectTarget(() => AssetsRedirect({ searchParams: Promise.resolve({}) })))
      .toBe('REDIRECT:/equipment?module=assets')
  })
})
