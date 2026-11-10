import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/auth', () => ({ getAuthHeaders: async () => ({ Authorization: 'Bearer fixture' }) }))
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/components/equipment', () => ({
  EquipmentPage: ({ initialTotal }: { initialTotal: number }) => <div>设备列表：{initialTotal}</div>,
  MaintenancePage: ({ initialMaintenancePlanTotal }: { initialMaintenancePlanTotal: number }) => <div>保养计划：{initialMaintenancePlanTotal}</div>,
  SparePartsPage: ({ initialSparePartTotal }: { initialSparePartTotal: number }) => <div>备件列表：{initialSparePartTotal}</div>,
}))

import AssetsView from './assets-view'
import MaintenanceView from './maintenance-view'
import SparePartsView from './spare-parts-view'

afterEach(() => vi.unstubAllGlobals())

const views = [
  { name: '台账', view: AssetsView, path: '/categories?tree=true', label: '设备列表' },
  { name: '台账位置', view: AssetsView, path: '/locations?tree=true', label: '设备列表' },
  { name: '台账设备', view: AssetsView, path: '/equipments', label: '设备列表' },
  { name: '台账部门', view: AssetsView, path: '/departments', label: '设备列表' },
  { name: '维保设备', view: MaintenanceView, path: '/equipments', label: '保养计划' },
  ...(['symptoms', 'causes', 'actions'] as const).map(type => ({
    name: `维保故障 ${type}`, view: MaintenanceView,
    path: `/maintenance/failure-codes/${type}`, label: '保养计划',
  })),
  { name: '校准', view: MaintenanceView, path: '/maintenance/calibration/records', label: '保养计划' },
  { name: '保养', view: MaintenanceView, path: '/maintenance/plans/', label: '保养计划' },
  { name: '备件', view: SparePartsView, path: '/spare-parts/', label: '备件列表' },
]

function stubApi(deniedPath?: string, status = 200) {
  const fetchMock = vi.fn(async (url: string) => {
    const requested = new URL(url)
    const target = new URL(`/api/v1/equipment${deniedPath ?? ''}`, 'http://fixture.test')
    const failed = Boolean(deniedPath) && requested.pathname === target.pathname
      && (!target.search || requested.search === target.search)
    return new Response(JSON.stringify(failed
      ? { message: 'upstream sensitive detail' }
      : { data: [], meta: { total: 7 } }), {
      status: failed ? status : 200,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe.each([401, 403])('设备页面 HTTP %i', status => {
  it.each(views)('$name 显示访问状态，不呈现空列表', async ({ view, path, label }) => {
    stubApi(path, status)
    const html = renderToStaticMarkup(await view({ workshopCode: '201-1' }))
    expect(html).toContain(status === 401 ? '登录已失效，请重新登录' : '没有执行此操作的权限，请联系管理员')
    expect(html).toContain(status === 401 ? 'href="/login"' : 'href="/"')
    expect(html).not.toContain(label)
    expect(html).not.toContain('upstream sensitive detail')
  })
})

it.each([
  { name: '台账', view: AssetsView, label: '设备列表' },
  { name: '维保', view: MaintenanceView, label: '保养计划' },
  { name: '备件', view: SparePartsView, label: '备件列表' },
])('$name 正常呈现服务端总数', async ({ view, label }) => {
  const fetchMock = stubApi()
  const html = renderToStaticMarkup(await view({ workshopCode: '201-1' }))
  expect(html).toContain(`${label}：7`)
  expect(html).not.toContain('重新登录')
  expect(fetchMock).toHaveBeenCalled()
})

it('台账发现身份失效后停止后续查询', async () => {
  const fetchMock = stubApi('/categories?tree=true', 401)
  await AssetsView({ workshopCode: '201-1' })
  expect(fetchMock).toHaveBeenCalledOnce()
})
