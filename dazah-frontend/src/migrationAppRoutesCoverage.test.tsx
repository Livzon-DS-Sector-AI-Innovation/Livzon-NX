/* @vitest-environment happy-dom */

import { describe, expect, it, vi } from 'vitest'

const routeMocks = vi.hoisted(() => {
  const fallback = (name: string): unknown => {
    if (name.toLowerCase().includes('workbook')) return { sheets: [] }
    if (name.toLowerCase().includes('dashboard') || name.toLowerCase().includes('stats')) return {}
    if (name.toLowerCase().includes('config') || name.toLowerCase().includes('recipients')) return []
    if (name.toLowerCase().includes('detail')) return { data: null, items: [], records: [], total: 0, meta: { total: 0 } }
    return { data: [], items: [], records: [], total: 0, meta: { total: 0, page: 1, page_size: 20 } }
  }
  const moduleFactory = async (importOriginal: () => Promise<Record<string, unknown>>) => {
    const actual = await importOriginal()
    return new Proxy(actual, {
      get: (target, name: string | symbol) => {
      if (name === 'then') return undefined
        if (typeof name !== 'string') return Reflect.get(target, name)
        const original = target[name]
        return typeof original === 'function' ? vi.fn(async () => fallback(String(name))) : original
      },
    })
  }
  return { moduleFactory }
})

vi.mock('next/navigation', () => ({
  redirect: vi.fn(() => ({ type: 'redirect' })),
  notFound: vi.fn(() => ({ type: 'not-found' })),
  useParams: vi.fn(() => ({ id: 'record-1', productId: 'product-1', productCode: 'LFT', group: 'raw', slug: 'raw-summary', planId: 'plan-1', sheetKey: 'projects', entityCode: 'candidate' })),
  usePathname: vi.fn(() => '/migration'),
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() })),
  useSearchParams: vi.fn(() => new URLSearchParams()),
}))

vi.mock('@/actions/hr', async (importOriginal) => routeMocks.moduleFactory(importOriginal))
vi.mock('@/actions/quality', async (importOriginal) => routeMocks.moduleFactory(importOriginal))
vi.mock('@/actions/quality-capa', async (importOriginal) => routeMocks.moduleFactory(importOriginal))
vi.mock('@/actions/quality-change', async (importOriginal) => routeMocks.moduleFactory(importOriginal))
vi.mock('@/actions/quality-deviation', async (importOriginal) => routeMocks.moduleFactory(importOriginal))
vi.mock('@/actions/registration', async (importOriginal) => routeMocks.moduleFactory(importOriginal))
vi.mock('@/actions/validation-audit', async (importOriginal) => routeMocks.moduleFactory(importOriginal))
vi.mock('@/actions/warehouse', async (importOriginal) => routeMocks.moduleFactory(importOriginal))
vi.mock('@/lib/api/server/admin', async (importOriginal) => routeMocks.moduleFactory(importOriginal))
vi.mock('@/lib/api/server/hr', async (importOriginal) => routeMocks.moduleFactory(importOriginal))
vi.mock('@/lib/api/server/quality', async (importOriginal) => routeMocks.moduleFactory(importOriginal))
vi.mock('@/lib/api/server/registration', async (importOriginal) => routeMocks.moduleFactory(importOriginal))
vi.mock('@/lib/api/server/regulatoryTracker', async (importOriginal) => routeMocks.moduleFactory(importOriginal))
vi.mock('@/lib/api/server/warehouse', async (importOriginal) => routeMocks.moduleFactory(importOriginal))
vi.mock('@/lib/api/quality-cpv', async (importOriginal) => routeMocks.moduleFactory(importOriginal))

type RouteLoader = () => Promise<Record<string, unknown>>
type GlobImportMeta = ImportMeta & {
  glob: <T>(patterns: string[], options: { eager: false }) => Record<string, T>
}

const routeLoaders = (import.meta as GlobImportMeta).glob<RouteLoader>(['./app/**/*.tsx'], { eager: false })

function routeProps(path: string): Record<string, unknown> {
  const params = {
    id: 'record-1', productId: 'product-1', productCode: 'LFT', group: 'raw', slug: 'summary',
    planId: 'plan-1', sheetKey: 'projects', entityCode: 'candidate', category: 'urgent', step: '1',
  }
  return {
    params: Promise.resolve(params),
    searchParams: Promise.resolve({}),
    ...(path.includes('/warehouse/') ? { searchParams: Promise.resolve({}) } : {}),
  }
}

describe('migrated app route coverage', () => {
  it('executes server route loaders with empty and partial-safe responses', async () => {
    const failures: string[] = []
    let executed = 0
    for (const [path, load] of Object.entries(routeLoaders)) {
      if (!path.includes('/app/(dashboard)/') || !path.endsWith('/page.tsx')) continue
      if (!path.match(/\/app\/\(dashboard\)\/(quality|registration|hr|warehouse|system)\//)) continue
      if (path.includes('/dossier-writer/')) continue
      // These routes are client components rather than server data loaders;
      // their interaction coverage is provided by component tests.
      if (path.includes('/cpv/') || path.includes('/production/')) continue
      const loadedModule = await load()
      const page = loadedModule.default
      if (typeof page !== 'function') continue
      try {
        await (page as (props?: Record<string, unknown>) => unknown)(routeProps(path))
        executed += 1
      } catch (error) {
        failures.push(`${path}: ${error instanceof Error ? error.message : String(error)}`)
      }
    }
    expect(executed).toBeGreaterThan(80)
    expect(failures).toEqual([])
  }, 120000)
})
