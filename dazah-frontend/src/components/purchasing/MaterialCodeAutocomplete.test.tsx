/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchMaterialOptions: vi.fn(),
}))

vi.mock('@/lib/api/purchasing', () => api)

vi.mock('antd', () => ({
  AutoComplete: ({
    onChange,
    onSelect,
    options,
    value,
  }: {
    onChange: (value: string) => void
    onSelect: (value: string, option: unknown) => void
    options: Array<{ key?: string; materialOption?: unknown; value?: string }>
    value?: string
  }) => (
    <div>
      <input
        value={value ?? ''}
        onChange={(event) => onChange((event.target as HTMLInputElement).value)}
        onInput={(event) => onChange((event.target as HTMLInputElement).value)}
      />
      {options.map((option) => (
        <button
          type="button"
          data-option={option.key}
          key={option.key}
          onClick={() => onSelect(option.value ?? '', option)}
        >
          {option.value}
        </button>
      ))}
    </div>
  ),
  Spin: () => <span>loading</span>,
}))

import { MaterialCodeAutocomplete } from './MaterialCodeAutocomplete'

const firstOption = {
  record_id: 'rec-1',
  material_code: 'MAT-001',
  material_description: '第一条物料',
  rule_model: 'A 型',
}

describe('MaterialCodeAutocomplete', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.useFakeTimers()
    api.fetchMaterialOptions.mockReset()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('debounces remote lookup and exposes duplicate options for selection', async () => {
    api.fetchMaterialOptions.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [
        firstOption,
        { ...firstOption, record_id: 'rec-2', material_description: '第二条物料' },
      ],
    })
    const onChange = vi.fn()
    const onUserChange = vi.fn()
    const onSelectMaterial = vi.fn()

    act(() => {
      root.render(
        <MaterialCodeAutocomplete
          onChange={onChange}
          onUserChange={onUserChange}
          onSelectMaterial={onSelectMaterial}
        />,
      )
    })
    const input = container.querySelector('input') as HTMLInputElement
    act(() => {
      input.value = 'MAT'
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => Promise.resolve())
    act(() => vi.advanceTimersByTime(299))
    expect(api.fetchMaterialOptions).not.toHaveBeenCalled()

    await act(async () => {
      vi.advanceTimersByTime(1)
      await Promise.resolve()
    })
    expect(api.fetchMaterialOptions).toHaveBeenCalledWith({ keyword: 'MAT', limit: 20 })
    expect(container.querySelectorAll('[data-option]').length).toBe(2)

    act(() => container.querySelector('[data-option="rec-2-1"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    expect(onUserChange).toHaveBeenCalledWith('MAT')
    expect(onSelectMaterial).toHaveBeenCalledWith(
      expect.objectContaining({ record_id: 'rec-2', material_description: '第二条物料' }),
    )
  })

  it('keeps manual entry usable when the source is not configured', async () => {
    api.fetchMaterialOptions.mockRejectedValue(new Error('请求失败: 404 Not Found'))
    const onUserChange = vi.fn()

    act(() => {
      root.render(
        <MaterialCodeAutocomplete onUserChange={onUserChange} />,
      )
    })
    const input = container.querySelector('input') as HTMLInputElement
    act(() => {
      input.value = 'MANUAL-001'
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      vi.advanceTimersByTime(300)
      await Promise.resolve()
    })

    expect(onUserChange).toHaveBeenCalledWith('MANUAL-001')
    expect(container.textContent).toContain('物料数据源尚未配置，可继续手工输入')
  })

  it.each([
    [new Error('请求失败: 502 Bad Gateway'), '飞书物料数据源暂时不可用，可继续手工输入'],
    ['unexpected failure', '物料编码联想失败，可继续手工输入'],
  ])('shows a recoverable status for lookup failures', async (error, expectedMessage) => {
    api.fetchMaterialOptions.mockRejectedValue(error)

    act(() => {
      root.render(<MaterialCodeAutocomplete value="MAT-FAIL" />)
    })
    await act(async () => {
      vi.advanceTimersByTime(300)
      await Promise.resolve()
    })

    expect(container.textContent).toContain(expectedMessage)
  })

  it('shows an empty result while preserving manual input', async () => {
    api.fetchMaterialOptions.mockResolvedValue({ code: 200, message: 'success', data: [] })

    act(() => {
      root.render(<MaterialCodeAutocomplete value="UNKNOWN" />)
    })
    await act(async () => {
      vi.advanceTimersByTime(300)
      await Promise.resolve()
    })

    expect(container.textContent).toContain('未找到匹配物料编码，可继续手工输入')
  })
})
