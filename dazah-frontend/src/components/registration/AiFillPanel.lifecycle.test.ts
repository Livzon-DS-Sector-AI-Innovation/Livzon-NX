import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const lifecycle = vi.hoisted(() => ({
  effects: [] as Array<() => void | (() => void)>,
  setters: [] as Array<ReturnType<typeof vi.fn>>,
  stateIndex: 0,
}))

const api = vi.hoisted(() => ({
  aiConfirmAndFill: vi.fn(),
  aiPreviewExtraction: vi.fn(),
  fetchAssetCategories: vi.fn(),
  splitConfirmAndInsert: vi.fn(),
  splitPreview: vi.fn(),
}))

const ui = vi.hoisted(() => ({
  message: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

const previewField = {
  field_name: '产品名称',
  field_type: 'text',
  value: '阿莫西林',
  confidence: 0.95,
  source: '质量标准',
}
const previewResult = {
  success: true,
  message: 'ok',
  fields: [previewField],
}

vi.mock('react', async (importOriginal) => {
  const original = await importOriginal<typeof import('react')>()
  return {
    ...original,
    useCallback: vi.fn((callback: unknown) => callback),
    useEffect: vi.fn((effect: () => void | (() => void)) => {
      lifecycle.effects.push(effect)
    }),
    useState: vi.fn((initial: unknown) => {
      const index = lifecycle.stateIndex++
      const setter = vi.fn()
      lifecycle.setters.push(setter)
      if (index === 3) return [previewResult, setter]
      if (index === 4) return [[previewField], setter]
      return [initial, setter]
    }),
  }
})

vi.mock('antd', () => {
  const component = () => null
  const Select = Object.assign(component, { Option: component })
  return {
    Alert: component,
    App: { useApp: () => ({ message: ui.message }) },
    Badge: component,
    Button: component,
    Card: component,
    Empty: component,
    Input: component,
    InputNumber: component,
    Modal: component,
    Popconfirm: component,
    Select,
    Space: component,
    Spin: component,
    Table: component,
    Tag: component,
    Typography: { Paragraph: component, Text: component },
  }
})

vi.mock('@/lib/api/dossier-writer-client', () => api)

import { AiFillPanel } from './AiFillPanel'

interface ElementLike {
  props?: Record<string, unknown>
}

function walk(node: ReactNode | unknown, seen = new Set<object>()): ElementLike[] {
  if (Array.isArray(node)) {
    return node.flatMap((item) => walk(item, seen))
  }
  if (typeof node !== 'object' || node === null || seen.has(node)) {
    return []
  }
  seen.add(node)
  const element = node as ElementLike
  return [
    element,
    ...Object.values(element.props ?? {}).flatMap((value) => walk(value, seen)),
  ]
}

function textOf(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') {
    return String(node)
  }
  if (Array.isArray(node)) {
    return node.map(textOf).join('')
  }
  if (typeof node === 'object' && node !== null) {
    return textOf((node as ElementLike).props?.children)
  }
  return ''
}

describe('AiFillPanel lifecycle', () => {
  beforeEach(() => {
    lifecycle.effects.length = 0
    lifecycle.setters.length = 0
    lifecycle.stateIndex = 0
    vi.clearAllMocks()
    api.fetchAssetCategories.mockResolvedValue([
      { id: 'category-1', category_name: '质量标准' },
    ])
    api.aiPreviewExtraction.mockResolvedValue(previewResult)
    api.aiConfirmAndFill.mockResolvedValue({
      success: true,
      results: [
        { field_name: '产品名称', status: 'filled', message: 'ok' },
      ],
    })
  })

  it('loads categories, previews fields and confirms the fill', async () => {
    const onFillComplete = vi.fn()
    const tree = AiFillPanel({
      chapterId: 'chapter-1',
      chapterCode: '3.2.S.1',
      assets: [
        {
          id: 'asset-1',
          original_filename: 'standard.docx',
          file_type: 'docx',
          file_size: 1,
          category_id: 'category-1',
          uploaded_at: '2026-07-31T00:00:00Z',
        },
      ],
      onAssetsChange: vi.fn(),
      onFillComplete,
    })

    expect(lifecycle.effects).toHaveLength(2)
    lifecycle.effects.forEach((effect) => effect())
    await vi.waitFor(() => {
      expect(api.fetchAssetCategories).toHaveBeenCalledWith('3.2.S.1')
      expect(lifecycle.setters[0]).toHaveBeenCalled()
      expect(lifecycle.setters[1]).toHaveBeenCalledWith(false)
    })

    const buttons = walk(tree).filter(
      (element) => typeof element.props?.onClick === 'function',
    )
    const preview = buttons.find(
      (element) => textOf(element) === 'AI 智能提取',
    )
    const confirm = buttons.find(
      (element) => textOf(element) === '确认并填充',
    )
    expect(preview).toBeDefined()
    expect(confirm).toBeDefined()

    await (preview?.props?.onClick as () => Promise<void>)()
    expect(api.aiPreviewExtraction).toHaveBeenCalledWith('chapter-1')
    expect(ui.message.success).toHaveBeenCalledWith('提取完成: 1 个字段')

    await (confirm?.props?.onClick as () => Promise<void>)()
    expect(api.aiConfirmAndFill).toHaveBeenCalledWith('chapter-1', {
      fields: [previewField],
    })
    expect(onFillComplete).toHaveBeenCalled()
    expect(ui.message.success).toHaveBeenCalledWith('填充完成: 1/1 个字段')
  })
})
