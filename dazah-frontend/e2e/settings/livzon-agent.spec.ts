import { expect, test } from '@playwright/test'

test.describe('Livzon Agent 治理台', () => {
  async function openAgentGovernance(page: import('@playwright/test').Page) {
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')
    const agentTab = page.getByRole('tab', { name: 'Livzon Agent管理' })
    await agentTab.click()
    await expect(agentTab).toHaveAttribute('aria-selected', 'true')
  }

  test('系统设置展示六个治理区域且默认进入运行总览', async ({ page }) => {
    await openAgentGovernance(page)

    await expect(page.getByRole('tab', { name: '运行总览' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '飞书接入' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '身份与准入' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '能力目录与策略' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '授权与确认' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '调用链路与投递诊断' })).toBeVisible()
    await expect(page.getByText('外部验收状态')).toHaveCount(0)
  })

  test('从最近异常直接打开并查询调用链路', async ({ page }) => {
    await openAgentGovernance(page)

    await page.getByRole('button', { name: '查看调用链路' }).click()

    await expect(
      page.getByRole('tab', { name: '调用链路与投递诊断' }),
    ).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByPlaceholder('输入调用链路编号或运行编号')).toHaveValue(
      '00000000-0000-0000-0000-000000000099',
    )
    await expect(page.getByText('飞书入站消息（正文已隐藏）')).toBeVisible()
    await expect(page.getByText('普通飞书对话不进入该队列')).toBeVisible()
  })

  test('飞书接入页不会展示 Secret 明文', async ({ page }) => {
    await openAgentGovernance(page)
    await page.getByRole('tab', { name: '飞书接入' }).click()

    await expect(page.getByLabel('应用密钥（App Secret）')).toHaveAttribute('type', 'password')
    await expect(page.getByLabel('应用密钥（App Secret）')).toHaveAttribute(
      'placeholder',
      '留空则不修改',
    )
  })

  test('保存配置明确展示接口成功结果', async ({ page }) => {
    await openAgentGovernance(page)
    await page.getByRole('tab', { name: '飞书接入' }).click()
    await page.getByRole('button', { name: '保存配置' }).click()
    await page.getByRole('button', { name: '确认保存' }).click()

    await expect(
      page
        .getByRole('tabpanel', { name: /飞书接入/ })
        .getByRole('alert')
        .filter({ hasText: '飞书接入配置保存成功' }),
    ).toBeVisible()
    await expect(page.getByText('配置版本 2 已写入，飞书网关已启用。')).toBeVisible()
  })

  test('六个治理区域的读取接口均能渲染', async ({ page }) => {
    await openAgentGovernance(page)

    await page.getByRole('tab', { name: '身份与准入' }).click()
    await expect(page.getByText('身份与准入目录')).toBeVisible()
    await expect(page.getByRole('button', { name: '同步飞书目录' })).toBeVisible()
    await expect(page.getByText('身份冲突工作台（0）')).toBeVisible()

    await page.getByRole('tab', { name: '能力目录与策略' }).click()
    await expect(page.getByText('quality.get_deviation')).toBeVisible()
    await page.getByRole('combobox', { name: '模块' }).click()
    const moduleDropdown = page.locator('.ant-select-dropdown:visible')
    for (const moduleName of ['energy', 'platform', 'procurement', 'quality', 'warehouse']) {
      await expect(
        moduleDropdown.locator(`.ant-select-item-option[title="${moduleName}"]`),
      ).toHaveCount(1)
    }
    await page.keyboard.press('Escape')
    await page
      .getByRole('row', { name: /quality\.get_deviation/ })
      .getByRole('button', { name: '详情' })
      .click()
    const capabilityDrawer = page.getByRole('dialog')
    await expect(capabilityDrawer.getByText('通用契约 · 待细化')).toBeVisible()
    await expect(capabilityDrawer.getByText('当前数据结构由处理程序的返回类型推导')).toBeVisible()
    await expect(capabilityDrawer.getByText(/additionalProperties/)).toBeVisible()
    await expect(
      capabilityDrawer.getByRole('rowheader', { name: '版本' }).locator('..'),
    ).toContainText('1')
    await page.keyboard.press('Escape')

    await page.getByRole('tab', { name: '授权与确认' }).click()
    await expect(page.getByText('Hermes 飞书记忆授权')).toBeVisible()

    await page.getByRole('tab', { name: '调用链路与投递诊断' }).click()
    await expect(page.getByText('调用链路查询')).toBeVisible()
  })

  test('调用链路查询展示跨渠道事件并导出脱敏诊断', async ({ page }) => {
    await openAgentGovernance(page)
    await page.getByRole('tab', { name: '调用链路与投递诊断' }).click()
    await page.getByPlaceholder('输入调用链路编号或运行编号').fill(
      '00000000-0000-0000-0000-000000000099',
    )
    await page.getByRole('button', { name: '查询' }).click()

    await expect(page.getByText('飞书入站消息（正文已隐藏）')).toBeVisible()
    await expect(page.getByText('会话事件').locator('..')).toContainText('2')
    const downloadPromise = page.waitForEvent('download')
    await page.getByRole('button', { name: '导出安全诊断' }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toContain('livzon-trace-')
  })
})
