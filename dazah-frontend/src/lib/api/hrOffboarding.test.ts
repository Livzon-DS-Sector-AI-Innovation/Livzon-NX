import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchEmployees, fetchOffboardingRecords } from './hr'

describe('offboarding list API failures', () => {
  afterEach(() => vi.unstubAllGlobals())

  it.each([401, 403, 500])('provides safe status-aware errors for HTTP %s', async status => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ message: 'sensitive upstream diagnostics' }), { status },
    )))
    await expect(fetchOffboardingRecords()).rejects.toMatchObject({
      status,
      message: status === 401 ? '登录已失效，请重新登录'
        : status === 403 ? '没有执行此操作的权限，请联系管理员' : '离职记录加载失败，请稍后重试',
    })
  })

  it('preserves employee, keyword and pagination filters', async () => {
    vi.stubGlobal('window', { location: { pathname: '/hr/offboarding' } })
    const payload = { code: 200, data: [], meta: { total: 0 } }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload)))
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchOffboardingRecords({ employee_id: 'employee-1', keyword: '测试', page: 2, page_size: 50 })).resolves.toEqual(payload)
    const url = new URL(fetchMock.mock.calls[0][0], 'http://localhost')
    expect(Object.fromEntries(url.searchParams)).toEqual({ employee_id: 'employee-1', keyword: '测试', page: '2', page_size: '50' })
    expect(fetchMock.mock.calls[0][1].headers).toEqual({ 'X-Dazah-Page-Path': '/hr/offboarding' })
  })

  it('preserves every employee profile filter and page permission context', async () => {
    vi.stubGlobal('window', { location: { pathname: '/hr/profile' } })
    const filters = { department: '质量部', sub_department: '分析组', status: '在职', keyword: '测试', gender: '男', level: '高级', position: '分析员', page: 2, page_size: 50 }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: [], meta: { total: 0 } })))
    vi.stubGlobal('fetch', fetchMock)
    await fetchEmployees(filters)
    const url = new URL(fetchMock.mock.calls[0][0], 'http://localhost')
    expect(url.pathname).toBe('/api/v1/hr/employees')
    expect(Object.fromEntries(url.searchParams)).toEqual({ ...filters, page: '2', page_size: '50' })
    expect(fetchMock.mock.calls[0][1].headers).toEqual({ 'X-Dazah-Page-Path': '/hr/profile' })
  })

  it.each([401, 403, 500])('employee reads retain HTTP %s without upstream diagnostics', async status => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('sensitive diagnostics', { status })))
    await expect(fetchEmployees()).rejects.toMatchObject({
      status,
      message: status === 401 ? '登录已失效，请重新登录'
        : status === 403 ? '没有执行此操作的权限，请联系管理员' : '员工档案加载失败，请稍后重试',
    })
  })

  it.each(['not JSON', 'null', '{}', '{"data":null}', '{"data":[],"meta":{"total":"invalid"}}'])('rejects invalid list payload %s', async body => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body)))
    await expect(fetchOffboardingRecords()).rejects.toMatchObject({ status: 502, message: '离职记录加载失败，请稍后重试' })
  })
})
