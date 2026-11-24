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

describe('DormitoryCheckinModal 选房、作废推荐与关闭', () => {
  const TWO_ROOMS = {
    recommendations: [
      { room_no: '201-2-301', dorm_type: '男生宿舍', room_type: '两人间', vacant_beds: 1, reason: '同部门集中' },
      { room_no: '201-2-302', dorm_type: '男生宿舍', room_type: '两人间', vacant_beds: 2, reason: '同部门集中' },
    ],
    message: '',
    source: 'ai',
  }

  /** 轮询到条件成立（Modal 内容与异步推荐结果依赖真实定时器）。 */
  async function until(condition: () => boolean, message: string) {
    for (let i = 0; i < 80; i += 1) {
      if (condition()) return
      await act(async () => {
        await new Promise((r) => setTimeout(r, 25))
      })
    }
    throw new Error(message)
  }

  function radio(value: string): HTMLInputElement | null {
    return document.body.querySelector<HTMLInputElement>(`input[type="radio"][value="${value}"]`)
  }

  function confirmButton(): HTMLButtonElement {
    const button = buttons('确认办理入住')[0]
    expect(button).toBeTruthy()
    return button!
  }

  function inputWithPlaceholder(fragment: string): HTMLInputElement {
    const input = Array.from(document.body.querySelectorAll<HTMLInputElement>('input')).find((node) =>
      node.getAttribute('placeholder')?.includes(fragment),
    )
    expect(input).toBeTruthy()
    return input!
  }

  async function typeInto(input: HTMLInputElement, value: string) {
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!.call(input, value)
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
  }

  async function renderWithCallbacks() {
    const onClose = vi.fn()
    const onCheckedin = vi.fn()
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
    return { onClose, onCheckedin }
  }

  async function recommendTwoRooms() {
    mocks.recommend.mockResolvedValue(TWO_ROOMS)
    await act(async () => {
      buttons('获取 AI 房间推荐')[0]?.click()
    })
    await until(() => radio('201-2-302') !== null, '推荐房间未渲染')
    // 多个候选时不自动选中：必须由用户选定
    expect(confirmButton().disabled).toBe(true)
  }

  it('多候选：手动选定房间后按所选房间提交', async () => {
    mocks.checkin.mockResolvedValue({ room_no: '201-2-302', synced: false })
    const { onCheckedin, onClose } = await renderWithCallbacks()
    await recommendTwoRooms()

    await act(async () => {
      radio('201-2-302')?.click()
    })
    expect(confirmButton().disabled).toBe(false)

    await act(async () => {
      confirmButton().click()
    })

    await until(() => mocks.checkin.mock.calls.length > 0, '未提交入住')
    expect(mocks.checkin).toHaveBeenCalledWith(
      'administration',
      expect.objectContaining({ room_no: '201-2-302' }),
    )
    expect(mocks.message.success).toHaveBeenCalledWith(
      '已办理入住：201-2-302（台账将在数分钟内同步）',
    )
    expect(onCheckedin).toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  }, 15000)

  it('修改性别：作废已有推荐，确认按钮回到禁用', async () => {
    mocks.recommend.mockResolvedValue({
      recommendations: [{ room_no: '201-2-301' }],
      message: '',
      source: 'ai',
    })
    await renderWithCallbacks()
    await act(async () => {
      buttons('获取 AI 房间推荐')[0]?.click()
    })
    // 单候选自动选中
    await until(() => confirmButton().disabled === false, '单候选未自动选中')

    await act(async () => {
      radio('女')?.click()
    })

    await until(
      () => document.body.textContent?.includes('201-2-301') === false,
      '修改性别后未作废推荐',
    )
    expect(confirmButton().disabled).toBe(true)
  })

  it('修改岗位：作废已有推荐', async () => {
    mocks.recommend.mockResolvedValue({
      recommendations: [{ room_no: '201-2-301' }],
      message: '',
      source: 'ai',
    })
    await renderWithCallbacks()
    await act(async () => {
      buttons('获取 AI 房间推荐')[0]?.click()
    })
    await until(() => confirmButton().disabled === false, '单候选未自动选中')

    await typeInto(inputWithPlaceholder('主管'), '工艺员')

    await until(
      () => document.body.textContent?.includes('201-2-301') === false,
      '修改岗位后未作废推荐',
    )
    expect(confirmButton().disabled).toBe(true)
  })

  it('点击弹窗关闭按钮：通知父级关闭且不提交', async () => {
    const { onClose, onCheckedin } = await renderWithCallbacks()

    await act(async () => {
      document.body.querySelector<HTMLElement>('.ant-modal-close')?.click()
    })

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(mocks.checkin).not.toHaveBeenCalled()
    expect(onCheckedin).not.toHaveBeenCalled()
  })
})
