import { expect, test, type Page } from '@playwright/test'
import { openCriticalBusinessSession } from '../critical-business-session'

const permitPath = '/safety/work-permits'
const detailPath = `${permitPath}/31000000-0000-4000-8000-000000000001`
const decisionPath = '/api/v1/safety/__test/permit-decision'
const nodeId = '31000000-0000-4000-8000-000000000002'

async function openHydratedList(page: Page, path: string) {
  // The list is server-rendered. Its metadata action runs after client hydration.
  await Promise.all([
    page.waitForResponse((response) => response.request().method() === 'POST'
      && new URL(response.url()).pathname === path && response.ok()),
    page.goto(path),
  ])
}

test('只读人员按状态筛选作业票，可查看详情但不可签批', async ({ context, page, baseURL }) => {
  await openCriticalBusinessSession(context, baseURL, 'safety-reader')
  await openHydratedList(page, permitPath)
  await expect(page.getByRole('link', { name: 'DH-E2E-002' })).toBeVisible()
  await page.getByRole('button', { name: '审批中：1' }).click()
  await expect(page.getByRole('link', { name: 'DH-E2E-002' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '新建作业票' })).toHaveCount(0)
  await page.getByRole('link', { name: 'DH-E2E-001' }).click()
  await expect(page).toHaveURL(new RegExp(`${detailPath}$`))
  await expect(page.getByText('车间审批', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /^同\s*意$/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /^驳\s*回$/ })).toHaveCount(0)
})

test('同意作业票后提交当前节点并刷新签批结果', async ({ context, page, baseURL }) => {
  const headers = await openCriticalBusinessSession(context, baseURL, 'safety-reviewer')
  await page.goto(detailPath)
  await page.getByRole('button', { name: /^同\s*意$/ }).click()
  await expect(page.getByText('已签', { exact: true })).toBeVisible()
  const receipt = await context.request.get(decisionPath, { headers })
  expect(await receipt.json()).toMatchObject({ data: { attempts: 1, decision: { status: 'approved', nodeId } } })
})

test('作业票驳回必须填写意见，确认后显示驳回结果', async ({ context, page, baseURL }) => {
  const headers = await openCriticalBusinessSession(context, baseURL, 'safety-reviewer')
  await page.goto(detailPath)
  await page.getByRole('button', { name: /^驳\s*回$/ }).click()
  const dialog = page.getByRole('dialog', { name: '驳回「车间审批」' })
  const confirm = dialog.getByRole('button', { name: '确认驳回' })
  await confirm.click()
  await expect(page.getByText('请填写驳回意见', { exact: true })).toBeVisible()
  const before = await context.request.get(decisionPath, { headers })
  expect(await before.json()).toMatchObject({ data: { attempts: 0, decision: null } })
  await dialog.getByPlaceholder('驳回意见（必填）').fill('请补充动火隔离措施')
  await confirm.click()
  await expect(dialog).toBeHidden()
  await expect(page.getByText('意见：请补充动火隔离措施', { exact: true })).toBeVisible()
  const receipt = await context.request.get(decisionPath, { headers })
  expect(await receipt.json()).toMatchObject({ data: {
    attempts: 1, decision: { status: 'rejected', opinion: '请补充动火隔离措施', nodeId },
  } })
})

test('证件到期汇总可筛选不同状态，查询账号不可导入或新建', async ({ context, page, baseURL }) => {
  await openCriticalBusinessSession(context, baseURL, 'safety-reader')
  await openHydratedList(page, '/safety/work-certificates')
  const expiring = page.getByRole('row', { name: /E2E-CERT-001/ })
  const expired = page.getByRole('row', { name: /E2E-CERT-002/ })
  await expect(expiring).toBeVisible()
  await expect(expired).toBeVisible()
  await page.getByRole('button', { name: '30天内到期：1' }).click()
  await expect(expired).toHaveCount(0)
  await expect(expiring).toBeVisible()
  await page.getByRole('button', { name: '已过期：1' }).click()
  await expect(expiring).toHaveCount(0)
  await expect(expired).toBeVisible()
  await expect(page.getByRole('button', { name: /Excel 导入|新建证件/ })).toHaveCount(0)
})
