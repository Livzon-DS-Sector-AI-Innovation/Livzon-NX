/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}))
const currentRoute = vi.hoisted(() => ({ module: '' }))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: navigation.push, replace: navigation.replace }),
  usePathname: () => '/equipment',
  useSearchParams: () => new URLSearchParams(
    currentRoute.module ? `module=${currentRoute.module}` : '',
  ),
}))

const authStore = vi.hoisted(() => ({
  state: {
    user: {
      id: 'u-test',
      role: 'admin' as string,
      page_permissions: [] as Array<{
        page_key: string
        module_code?: string
        permissions: string[]
        visible_sections?: string[] | null
      }>,
    },
  },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: (selector: (s: typeof authStore.state) => unknown) => selector(authStore.state),
}))

import { ModuleTabs } from './ModuleTabs'
import type { EquipmentModule } from '@/lib/equipment-page-permissions'

let root: Root | null = null

function renderTabs(activeModule?: EquipmentModule) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => {
    root!.render(<ModuleTabs workshop="103" activeModule={activeModule} />)
  })
}

function tabLabels() {
  return Array.from(document.querySelectorAll('.ant-tabs-tab')).map(
    (node) => node.textContent,
  )
}

beforeEach(() => {
  navigation.push.mockClear()
  navigation.replace.mockClear()
  currentRoute.module = ''
  authStore.state.user = {
    ...authStore.state.user,
    role: 'admin',
    page_permissions: [],
  }
})

afterEach(() => {
  act(() => root?.unmount())
  document.body.innerHTML = ''
})

describe('ModuleTabs（统一工作台模块切换）', () => {
  it('管理员渲染全部 5 个模块 Tab 并高亮当前模块', async () => {
    currentRoute.module = 'maintenance'
    renderTabs('maintenance')
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    expect(tabLabels()).toEqual(['设备台账', '维护保养', '设备巡检', '备件管理', '人员配置'])
    const active = document.querySelector('.ant-tabs-tab-active')
    expect(active?.textContent).toBe('维护保养')
  })

  it('点击模块 Tab 跳转到同车间的新模块地址', async () => {
    currentRoute.module = 'assets'
    renderTabs('assets')
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    const target = Array.from(document.querySelectorAll('.ant-tabs-tab')).find(
      (node) => node.textContent === '备件管理',
    ) as HTMLElement
    await act(async () => { target.click() })
    expect(navigation.push).toHaveBeenCalledWith(
      '/equipment?workshop=103&module=spare-parts',
      { scroll: false },
    )
  })

  it('按页面授权过滤模块 Tab；无模块参数时自动落到首个有权限模块', async () => {
    currentRoute.module = ''
    authStore.state.user = {
      ...authStore.state.user,
      role: 'user',
      page_permissions: [
        { page_key: 'equipment:inspection', module_code: 'equipment', permissions: ['access', 'query'] },
        { page_key: 'equipment:spare-parts', module_code: 'equipment', permissions: ['access', 'query'] },
      ],
    }
    renderTabs(undefined)
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    // 仅渲染授权模块，且自动 replace 到首个授权模块（设备台账在巡检之后被过滤）
    expect(tabLabels()).toEqual(['设备巡检', '备件管理'])
    expect(navigation.replace).toHaveBeenCalledWith(
      '/equipment?workshop=103&module=inspection',
      { scroll: false },
    )
  })

  it('旧车间叶授权经投影后同样打开对应模块 Tab', async () => {
    currentRoute.module = 'maintenance'
    authStore.state.user = {
      ...authStore.state.user,
      role: 'user',
      page_permissions: [
        {
          page_key: 'equipment:workshop-103:maintenance-103',
          module_code: 'equipment',
          permissions: ['access', 'query', 'operate'],
        },
      ],
    }
    renderTabs('maintenance')
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    expect(tabLabels()).toEqual(['维护保养'])
    expect(navigation.replace).not.toHaveBeenCalled()
  })
})
