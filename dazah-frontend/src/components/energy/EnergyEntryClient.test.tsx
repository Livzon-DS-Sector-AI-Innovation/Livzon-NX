/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { afterEach, expect, it, vi } from 'vitest'
import type { DirectReading } from '@/lib/api/energy-ledger'
const state = vi.hoisted(() => ({ data: undefined as DirectReading | undefined, params: 'date=2026-10-20&dataset=电量', error: undefined as Error | undefined, canOperate: true, invalidate: vi.fn(), refetch: vi.fn() }))
vi.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams(state.params) }))
vi.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({ invalidateQueries: state.invalidate }), useQuery: ({ queryKey }: { queryKey: string[] }) => queryKey[1] === 'input-readings' ? { data: state.data, error: state.error, refetch: state.refetch } : {} }))
vi.mock('@/actions/energy-ledger', () => ({ saveDirectReadings: vi.fn() }))
vi.mock('@/stores/auth', () => ({ useAuthStore: (selector: (value: { hasPagePermission: () => boolean }) => boolean) => selector({ hasPagePermission: () => state.canOperate }) }))
import { saveDirectReadings } from '@/actions/energy-ledger'
import { EnergyEntryClient } from './EnergyEntryClient'
let root: Root | undefined
const data: DirectReading = { reading_date: '2026-10-20', dataset: '电量', items: [{ point_id: 'p1', name: '101车间电量', unit: 'kWh', precision: 3, value: null, draft_value: null, version: 0 }] }
afterEach(async () => { await act(async () => root?.unmount()); root = undefined; state.data = undefined; state.error = undefined; state.canOperate = true; vi.clearAllMocks(); vi.unstubAllGlobals(); document.body.replaceChildren() })
async function render(dark = false) {
  const host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  await act(async () => root?.render(<ConfigProvider locale={zhCN} theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyEntryClient /></App></ConfigProvider>))
}
async function click(label: string, scope: ParentNode = document) {
  const button = [...scope.querySelectorAll<HTMLButtonElement>('button')].find(item => item.textContent?.replace(/\s/g, '') === label)
  expect(button).toBeDefined()
  await act(async () => button!.click())
}
async function fill(value: string) {
  const input = document.querySelector<HTMLInputElement>('[aria-label="101车间电量本次填写"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true }))
  })
}
it.each([false, true])('allows direct date-based filling without plans or task generation (dark=%s)', async dark => {
  state.data = data
  await render(dark)
  expect(document.body.textContent).toContain('101车间电量')
  expect(document.querySelector<HTMLInputElement>('[aria-label="数据日期"]')?.value).toBe('2026年10月20日')
  expect(document.body.textContent).not.toContain('生成该日清单')
  expect(document.body.textContent).not.toContain('我的待填清单')
  vi.mocked(saveDirectReadings).mockResolvedValue({ ok: true, data })
  await fill('12.5'); await click('提交生效')
  expect(saveDirectReadings).not.toHaveBeenCalled()
  await click('确定', document.querySelector('[role=dialog]')!)
  expect(saveDirectReadings).toHaveBeenCalledWith({ reading_date: '2026-10-20', dataset: '电量', values: [{ point_id: 'p1', version: 0, value: '12.5' }], draft: false, reason: '' })
  expect(state.invalidate).toHaveBeenCalledWith({ queryKey: ['energy-ledger'] })
})
it('submits an existing zero draft without copying an earlier reading', async () => {
  state.data = { ...data, items: [{ ...data.items[0], draft_value: '0', version: 2 }] }
  vi.mocked(saveDirectReadings).mockResolvedValue({ ok: true, data })
  await render(); await click('提交生效'); await click('确定', document.querySelector('[role=dialog]')!)
  expect(saveDirectReadings).toHaveBeenCalledWith(expect.objectContaining({ values: [{ point_id: 'p1', version: 2, value: '0' }] }))
})
it.each([false, true])('shows original field names without the development prefix and retains point identity (dark=%s)', async dark => {
  state.data = { ...data, items: [
    { ...data.items[0], name: '开发验证 · 201一车间（-5°）', draft_value: '12.5' },
    { ...data.items[0], point_id: 'p2', name: '103车间开发验证管道', value: '0' },
  ] }
  vi.mocked(saveDirectReadings).mockResolvedValue({ ok: true, data })
  await render(dark)
  const rows = document.querySelectorAll('tbody tr[data-row-key]')
  expect(rows[0].querySelector('td')?.textContent).toBe('201一车间（-5°）')
  expect(rows[1].querySelector('td')?.textContent).toBe('103车间开发验证管道')
  expect(rows[1].querySelectorAll('td')[2].textContent).toBe('0')
  expect(document.querySelector('[aria-label="201一车间（-5°）本次填写"]')).not.toBeNull()
  expect(document.querySelector('label[for="energy-entry-date"]')?.textContent).toBe('数据日期')
  expect(document.querySelector('label[for="energy-entry-dataset"]')?.textContent).toBe('原始数据表')
  await click('保存草稿')
  expect(saveDirectReadings).toHaveBeenCalledWith(expect.objectContaining({ values: [{ point_id: 'p1', version: 0, value: '12.5' }], draft: true }))
  expect(state.data.items[0].name).toBe('开发验证 · 201一车间（-5°）')
})
it('preserves input when a concurrent save fails', async () => {
  state.data = data
  vi.mocked(saveDirectReadings).mockResolvedValue({ ok: false, message: '数据已被修改，请刷新后核对最新版本' })
  await render(); await fill('20'); await click('保存草稿')
  expect(document.body.textContent).toContain('数据已被修改')
  expect(Number(document.querySelector<HTMLInputElement>('[aria-label="101车间电量本次填写"]')?.value)).toBe(20)
  expect(state.invalidate).not.toHaveBeenCalled()
})
it('keeps read-only users from editing or submitting', async () => {
  state.data = data; state.canOperate = false
  await render()
  expect(document.querySelector<HTMLInputElement>('[aria-label="101车间电量本次填写"]')?.disabled).toBe(true)
  expect([...document.querySelectorAll('button')].find(button => button.textContent?.replace(/\s/g, '') === '提交生效')?.disabled).toBe(true)
})
it('distinguishes denied access from an empty original table', async () => {
  state.error = new Error('无权查看当前能源数据')
  await render()
  expect(document.body.textContent).toContain('无权查看当前能源数据')
  expect(document.body.textContent).not.toContain('暂无当前权限内的字段')
})
it('retains unsaved readings when a calendar shortcut change is cancelled', async () => {
  state.data = data
  await render(); await fill('20')
  await act(async () => document.querySelector<HTMLInputElement>('[aria-label="数据日期"]')!.click())
  await click('本月初')
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain('有未保存的输入，切换将放弃这些输入。')
  await click('继续填写', document.querySelector('[role="dialog"]')!)
  expect(document.querySelector<HTMLInputElement>('[aria-label="数据日期"]')?.value).toBe('2026年10月20日')
  expect(Number(document.querySelector<HTMLInputElement>('[aria-label="101车间电量本次填写"]')?.value)).toBe(20)
})
it('discards inputs only after confirming a date change in the Ant Design modal', async () => {
  state.data = data
  await render(); await fill('20')
  await act(async () => document.querySelector<HTMLInputElement>('[aria-label="数据日期"]')!.click())
  await click('本月初')
  await click('放弃并切换', document.querySelector('[role="dialog"]')!)
  expect(document.querySelector<HTMLInputElement>('[aria-label="数据日期"]')?.value).toBe('2026年10月01日')
  expect(document.querySelector<HTMLInputElement>('[aria-label="101车间电量本次填写"]')?.value).toBe('')
})
it('guards link navigation with a themed confirmation and continues only after approval', async () => {
  state.data = data
  await render(true); await fill('20')
  const link = document.createElement('a'); link.href = '/energy/reports'; document.body.append(link)
  const navigate = vi.fn((event: MouseEvent) => event.preventDefault())
  link.addEventListener('click', navigate)
  await act(async () => link.click())
  expect(navigate).not.toHaveBeenCalled()
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain('有未保存的能源填写')
  await click('继续填写', document.querySelector('[role="dialog"]')!)
  expect(document.querySelector<HTMLInputElement>('[aria-label="101车间电量本次填写"]')?.value).not.toBe('')
  await act(async () => link.click())
  await click('放弃并离开', document.querySelector('[role="dialog"]')!)
  expect(navigate).toHaveBeenCalledOnce()
})
