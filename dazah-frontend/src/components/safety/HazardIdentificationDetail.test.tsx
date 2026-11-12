/* @vitest-environment happy-dom */
import { App } from 'antd'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import HazardIdentificationDetail from './HazardIdentificationDetail'

const mocks = vi.hoisted(() => ({
  router: { push: vi.fn() },
  load: vi.fn(),
  run: vi.fn(),
  review: vi.fn(),
  update: vi.fn(),
}))

vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'record-1' }),
  useRouter: () => mocks.router,
}))
vi.mock('@/actions/safety', () => ({
  getHazardIdentification: mocks.load,
  runHazardScript: mocks.run,
  reviewHazardScript: mocks.review,
  updateHazardIdentification: mocks.update,
}))
vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({ canOperate: true, canApprove: true, canReject: true }),
}))

const record = {
  id: 'record-1',
  hazard_id_no: 'HI-TEST',
  overall_status: 'in_progress',
  ai_node_progress: 'pending_script1',
  script1_review_status: 'pending',
  hazard_source: '测试记录',
}
let container: HTMLDivElement
let root: Root

beforeEach(() => {
  vi.resetAllMocks()
  mocks.load.mockResolvedValue({ code: 200, data: record })
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
})

afterEach(async () => {
  await act(async () => root.unmount())
  container.remove()
})

async function renderDetail(ledger = false) {
  await act(async () => root.render(
    <App><HazardIdentificationDetail ledger={ledger} /></App>,
  ))
}

function findButton(text: string) {
  return [...document.body.querySelectorAll('button')].find(
    (button) => button.textContent?.replace(/\s/g, '') === text,
  )
}

async function clickButton(text: string) {
  const button = findButton(text)
  if (!button) throw new Error(`Missing button: ${text}`)
  await act(async () => button.click())
}

it.each([true, false])('renders ledger and workflow actions separately (ledger=%s)', async (ledger) => {
  await renderDetail(ledger)
  expect(container.textContent).toContain('HI-TEST')
  expect(Boolean(findButton('执行AI'))).toBe(!ledger)
  await clickButton('返回列表')
  expect(mocks.router.push).toHaveBeenLastCalledWith(
    ledger ? '/safety/hazard-identification/ledger' : '/safety/hazard-identification',
  )
})

it('returns to the originating ledger when the record is unavailable', async () => {
  mocks.load.mockResolvedValue({ code: 404 })
  await renderDetail(true)
  expect(mocks.router.push).toHaveBeenCalledWith('/safety/hazard-identification/ledger')
  expect(document.body.textContent).toContain('加载失败')
})

it('reports a rejected request while keeping the workflow route', async () => {
  mocks.load.mockRejectedValue(new Error('unavailable'))
  await renderDetail()
  expect(document.body.textContent).toContain('加载失败')
  expect(mocks.router.push).not.toHaveBeenCalled()
})

it('advances to the returned workflow step after execution', async () => {
  mocks.run.mockResolvedValue({
    code: 200,
    data: { ...record, ai_node_progress: 'pending_script2', hazard_id_no: 'HI-UPDATED' },
  })
  await renderDetail()
  await clickButton('执行AI')
  expect(mocks.run).toHaveBeenCalledWith('record-1', 1)
  expect(container.textContent).toMatch(/步骤2：.*输出结果/)
  expect(container.textContent).toContain('HI-UPDATED')
  expect(document.body.textContent).toContain('执行完成')
})

it('shows workflow execution errors and leaves execution available', async () => {
  mocks.run
    .mockResolvedValueOnce({ code: 503, message: '工作流暂不可用' })
    .mockRejectedValueOnce(new Error('unavailable'))
  await renderDetail()
  await clickButton('执行AI')
  expect(document.body.textContent).toContain('工作流暂不可用')
  await clickButton('执行AI')
  expect(document.body.textContent).toContain('工作流执行失败')
  expect(container.textContent).toMatch(/步骤1：.*输出结果/)
})

it.each([
  ['审核通过', 'approved', '已审核'],
  ['驳回', 'rejected', '已驳回'],
])('submits the selected review action %s and displays the returned state', async (button, decision, label) => {
  const pending = { ...record, specific_activity: '检查工艺设备' }
  mocks.load.mockResolvedValue({ code: 200, data: pending })
  mocks.review
    .mockResolvedValueOnce({ code: 409, message: '审核版本已更新' })
    .mockResolvedValueOnce({ code: 200, data: { ...pending, script1_review_status: decision } })
  await renderDetail()
  expect(container.textContent).toContain('检查工艺设备')
  await clickButton(button)
  expect(document.body.textContent).toContain('审核版本已更新')
  await clickButton(button)
  expect(mocks.review).toHaveBeenLastCalledWith('record-1', 1, decision)
  expect(container.textContent).toContain(label)
  expect(findButton(button)).toBeUndefined()
})

it('keeps an edited result open on failure and displays it after saving', async () => {
  mocks.load.mockResolvedValue({
    code: 200,
    data: { ...record, specific_activity: '原作业活动' },
  })
  mocks.update
    .mockResolvedValueOnce({ code: 409, message: '记录已变化' })
    .mockResolvedValueOnce({ code: 200, data: { ...record, specific_activity: '新作业活动' } })
  await renderDetail()
  await clickButton('编辑')
  const textarea = document.body.querySelector<HTMLTextAreaElement>('[role="dialog"] textarea')
  if (!textarea) throw new Error('Missing workflow result editor')
  expect(textarea.value).toBe('原作业活动')
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set?.call(textarea, '新作业活动')
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await clickButton('确认')
  expect(mocks.update).toHaveBeenLastCalledWith('record-1', expect.objectContaining({ specific_activity: '新作业活动' }))
  expect(document.body.textContent).toContain('记录已变化')
  expect(textarea.value).toBe('新作业活动')
  await clickButton('确认')
  expect(container.textContent).toContain('新作业活动')
  expect(document.body.textContent).toContain('更新成功')
})
