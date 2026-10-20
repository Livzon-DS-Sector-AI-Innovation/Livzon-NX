/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}))
const currentRoute = vi.hoisted(() => ({ workshop: '' }))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: navigation.push, replace: navigation.replace }),
  usePathname: () => '/equipment/assets',
  useSearchParams: () => new URLSearchParams(currentRoute.workshop ? `workshop=${currentRoute.workshop}` : ''),
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
import { useEquipmentWorkshopStore } from '@/stores/equipment-workshop'

let root: Root | null = null

function renderBlocks() {
  const container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => {
    root!.render(<WorkshopNavBlocks pageKey="equipment:assets" />)
  })
}

function blocks() {
  return Array.from(document.querySelectorAll('[data-testid^="workshop-block:"]'))
}

beforeEach(() => {
  navigation.push.mockClear()
  navigation.replace.mockClear()
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
  it('渲染 9 个等宽车间块并高亮 URL 指定的车间', async () => {
    currentRoute.workshop = '201-1'
    renderBlocks()
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    expect(blocks()).toHaveLength(9)
    const active = document.querySelector('[data-testid="workshop-block:201-1"]') as HTMLElement
    expect(active).toBeTruthy()
    expect(active.style.borderColor).toContain('var(--color-primary)')
    // 车间名与图标渲染
    expect(active.textContent).toContain('201一车间')
  })

  it('点击车间块更新 URL 查询参数（不跳路由）', async () => {
    currentRoute.workshop = '201-1'
    renderBlocks()
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    const target = document.querySelector('[data-testid="workshop-block:103"]') as HTMLElement
    await act(async () => { target.click() })
    expect(navigation.push).toHaveBeenCalledWith('/equipment/assets?workshop=103', { scroll: false })
    expect(useEquipmentWorkshopStore.getState().workshopCode).toBe('103')
  })

  it('无 URL 参数时回落记忆车间；按授权过滤不可见车间', async () => {
    currentRoute.workshop = ''
    useEquipmentWorkshopStore.setState({ workshopCode: '101-1' })
    // 非管理员：台账页仅授权 101-1 / 203 两个车间
    authStore.state.user = {
      ...authStore.state.user,
      role: 'user',
      page_permissions: [
        { page_key: 'equipment:assets', permissions: ['access', 'query', 'operate'], visible_sections: ['101-1', '203'] },
      ],
    }
    renderBlocks()
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    // 只渲染授权车间；记忆车间（101-1）自动补到 URL
    expect(blocks().map((b) => b.getAttribute('data-testid'))).toEqual([
      'workshop-block:101-1',
      'workshop-block:203',
    ])
    expect(navigation.replace).toHaveBeenCalledWith('/equipment/assets?workshop=101-1', { scroll: false })
  })
})
