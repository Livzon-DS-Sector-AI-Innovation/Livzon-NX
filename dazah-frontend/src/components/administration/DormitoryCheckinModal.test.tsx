/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  recommend: vi.fn(),
  checkin: vi.fn(),
}))

vi.mock('@/lib/api/mapped-feishu', () => ({
  fetchDormitoryStats: vi.fn(),
  recommendDormitoryRooms: mocks.recommend,
  submitDormitoryCheckin: mocks.checkin,
}))
vi.mock('@/lib/user-error', () => ({
  getUserErrorMessage: (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback,
}))

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return { RobotOutlined: Icon }
})

const validateFieldsStub = vi.hoisted(() =>
  vi.fn(async () => ({
    name: '测试员工',
    gender: '男',
    department: '一车间',
    job_title: '操作工',
    shift_type: '白班',
  })),
)

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()

  // 真 form 实例（Form.Item 依赖内部方法），仅拦截 validateFields 走 stub。
  // 惰性创建：vi.mock 工厂提升阶段 React 未就绪，首次调用 useForm 时再建。
  let cachedWrapped: unknown = null
  const useFormStub = () => {
    if (cachedWrapped === null) {
      const realForm = actual.Form.useForm()[0]
      cachedWrapped = new Proxy(realForm, {
        get(target, prop, receiver) {
          if (prop === 'validateFields') return validateFieldsStub
          return Reflect.get(target, prop, receiver)
        },
      })
    }
    return [cachedWrapped]
  }

  return {
    ...actual,
    Form: { ...actual.Form, useForm: useFormStub },
    message: mocks.message,
    App: { ...actual.App, useApp: () => ({ message: mocks.message }) },
  }
})

import { App as AntApp } from 'antd'
import DormitoryCheckinModal from './DormitoryCheckinModal'

let root: Root | null = null
let container: HTMLDivElement | null = null

function buttons(text: string) {
  const needle = text.replace(/\s/g, '')
  return Array.from(
    document.body.querySelectorAll<HTMLButtonElement>('button'),
  ).filter((b) => b.textContent?.replace(/\s/g, '').includes(needle))
}

async function render() {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => {
    root!.render(
      <AntApp>
        <DormitoryCheckinModal open onClose={() => {}} onCheckedin={() => {}} />
      </AntApp>,
    )
  })
  await act(async () => {
    await new Promise((r) => setTimeout(r, 30))
  })
}

async function flush(rounds = 4) {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await Promise.resolve()
    })
  }
}

async function clickRecommend() {
  const btn = buttons('获取 AI 房间推荐')[0]
  expect(btn).toBeTruthy()
  await act(async () => {
    btn!.click()
  })
  await flush()
}

async function clickConfirm() {
  const btn = buttons('确认办理入住')[0]
  expect(btn).toBeTruthy()
  await act(async () => {
    btn!.click()
  })
  await flush()
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
  root = null
  container = null
})

describe('DormitoryCheckinModal', () => {
  it('渲染标题与两个操作按钮', async () => {
    await render()
    expect(buttons('获取 AI 房间推荐').length).toBe(1)
    expect(buttons('确认办理入住').length).toBe(1)
    // 未推荐前确认按钮禁用
    expect(buttons('确认办理入住')[0]?.disabled).toBe(true)
  })

  it('推荐→单候选自动选中→确认提交全链（成功文案+回调）', async () => {
    mocks.recommend.mockResolvedValue({
      recommendations: [{ room_no: '201-2-301' }],
      message: '',
      source: 'ai',
    })
    mocks.checkin.mockResolvedValue({ room_no: '201-2-301', synced: true })
    const onCheckedin = vi.fn()
    const onClose = vi.fn()
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    act(() => {
      root!.render(
        <AntApp>
          <DormitoryCheckinModal open onClose={onClose} onCheckedin={onCheckedin} />
        </AntApp>,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
    })
    await act(async () => {
      buttons('获取 AI 房间推荐')[0]?.click()
    })
    await flush()
    await act(async () => {
      buttons('确认办理入住')[0]?.click()
    })
    await flush()
    expect(mocks.recommend).toHaveBeenCalled()
    expect(mocks.checkin).toHaveBeenCalled()
    expect(mocks.message.success.mock.calls[0][0]).toContain('台账已同步')
    expect(onCheckedin).toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  }, 15000)
})

describe('DormitoryCheckinModal 错误分支', () => {
  it('推荐失败：显示用户可读错误（getUserErrorMessage 透传）', async () => {
    mocks.recommend.mockRejectedValue(new Error('镜像未同步'))
    await render()
    await act(async () => {
      buttons('获取 AI 房间推荐')[0]?.click()
    })
    await flush()
    expect(mocks.message.error).toHaveBeenCalledWith('镜像未同步')
    expect(mocks.checkin).not.toHaveBeenCalled()
  })

  it('提交失败：显示用户可读错误且不触发回调', async () => {
    mocks.recommend.mockResolvedValue({
      recommendations: [{ room_no: '201-2-301' }],
      message: '',
      source: 'ai',
    })
    mocks.checkin.mockRejectedValue(new Error('回写飞书失败'))
    const onCheckedin = vi.fn()
    const onClose = vi.fn()
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    act(() => {
      root!.render(
        <AntApp>
          <DormitoryCheckinModal
            open
            onClose={onClose}
            onCheckedin={onCheckedin}
          />
        </AntApp>,
      )
    })
    await act(async () => {
      buttons('获取 AI 房间推荐')[0]?.click()
    })
    await flush()
    await act(async () => {
      buttons('确认办理入住')[0]?.click()
    })
    await flush()
    expect(mocks.message.error).toHaveBeenCalledWith('回写飞书失败')
    expect(onCheckedin).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  }, 15000)
})
