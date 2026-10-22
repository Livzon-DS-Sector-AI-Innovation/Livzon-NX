/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}))
const currentRoute = vi.hoisted(() => ({ workshop: '', module: '' }))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: navigation.push, replace: navigation.replace }),
  usePathname: () => '/equipment',
  useSearchParams: () => new URLSearchParams(
    [
      ...(currentRoute.workshop ? [`workshop=${currentRoute.workshop}`] : []),
      ...(currentRoute.module ? [`module=${currentRoute.module}`] : []),
    ].join('&'),
  ),
}))

const authStore = vi.hoisted(() => ({
  state: {
    user: {
      id: 'u-test',
      role: 'admin' as string,
      permissions: ['*'] as string[],
      page_permissions: [] as Array<{ page_key: string; permissions: string[]; visible_sections?: string[] | null }>,
    },
  },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: (selector: (s: typeof authStore.state) => unknown) => selector(authStore.state),
}))

import { WorkshopNavBlocks } from './WorkshopNavBlocks'
import type { EquipmentPageKey } from '@/lib/equipment-page-permissions'
import { useEquipmentWorkshopStore } from '@/stores/equipment-workshop'

let root: Root | null = null

function renderBlocks(pageKey: EquipmentPageKey = 'equipment:assets') {
  const container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => {
    root!.render(<WorkshopNavBlocks pageKey={pageKey} />)
  })
}

function blocks() {
  return Array.from(document.querySelectorAll('[data-testid^="workshop-block:"]'))
}

beforeEach(() => {
  navigation.push.mockClear()
  navigation.replace.mockClear()
  currentRoute.workshop = ''
  currentRoute.module = ''
  useEquipmentWorkshopStore.setState({ workshopCode: '201-1' })
  try {
    window.localStorage.removeItem('dazah.equipment.workshop-context')
  } catch { /* 存储不可用时忽略 */ }
})

afterEach(() => {
  act(() => root?.unmount())
  document.body.innerHTML = ''
})

describe('WorkshopNavBlocks（产线块样式）', () => {
  it('渲染 10 个车间块并高亮 URL 指定的车间；无模块参数时点击不带 module', async () => {
    currentRoute.workshop = '201-1'
    renderBlocks()
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    const all = blocks()
    expect(all).toHaveLength(10)
    expect(all[0].getAttribute('data-testid')).toBe('workshop-block:101-1')
    const active = document.querySelector('[data-testid="workshop-block:201-1"]') as HTMLElement
    expect(active).toBeTruthy()
    expect(active.style.borderColor).toContain('var(--color-primary)')
    // 车间名与图标渲染
    expect(active.textContent).toContain('201一车间')
    // 201 二车间按产品线拆分为霉酚酸 / 多拉两个块；
    // 两块均显示短名，悬停提示用全名
    const mcBlock = document.querySelector('[data-testid="workshop-block:201-2-MC"]') as HTMLElement
    const drBlock = document.querySelector('[data-testid="workshop-block:201-2-DR"]') as HTMLElement
    expect(mcBlock?.textContent).toContain('201二车间（MC）')
    expect(mcBlock?.getAttribute('title')).toBe('切换到 201二车间（霉酚酸）')
    expect(drBlock?.textContent).toContain('201二车间（DR）')
    expect(drBlock?.getAttribute('title')).toBe('切换到 201二车间（多拉）')

    const plain = document.querySelector('[data-testid="workshop-block:203"]') as HTMLElement
    await act(async () => { plain.click() })
    expect(navigation.push).toHaveBeenCalledWith('/equipment?workshop=203', { scroll: false })
  })

  it('点击车间块更新 URL 查询参数并记忆车间；保留当前功能模块', async () => {
    currentRoute.workshop = '201-1'
    currentRoute.module = 'maintenance'
    renderBlocks()
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    const target = document.querySelector('[data-testid="workshop-block:103"]') as HTMLElement
    await act(async () => { target.click() })
    expect(navigation.push).toHaveBeenCalledWith(
      '/equipment?workshop=103&module=maintenance',
      { scroll: false },
    )
    expect(useEquipmentWorkshopStore.getState().workshopCode).toBe('103')
  })

  it('无 URL 参数时回落记忆车间（含模块参数）并按授权过滤车间', async () => {
    currentRoute.workshop = ''
    currentRoute.module = 'personnel'
    useEquipmentWorkshopStore.setState({ workshopCode: '101-1' })
    // 非管理员：人员配置页仅授权 101-1 / 203 两个车间
    authStore.state.user = {
      ...authStore.state.user,
      role: 'user',
      page_permissions: [
        { page_key: 'equipment:personnel', permissions: ['access', 'query', 'operate'], visible_sections: ['101-1', '203'] },
      ],
    }
    renderBlocks('equipment:personnel')
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    // 只渲染授权车间；记忆车间连同模块参数一起补到 URL
    expect(blocks().map((b) => b.getAttribute('data-testid'))).toEqual([
      'workshop-block:101-1',
      'workshop-block:203',
    ])
    expect(navigation.replace).toHaveBeenCalledWith(
      '/equipment?workshop=101-1&module=personnel',
      { scroll: false },
    )
  })
})
