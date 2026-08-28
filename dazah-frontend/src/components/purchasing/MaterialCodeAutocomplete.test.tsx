/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
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
    notFoundContent,
  }: {
    onChange: (value: string) => void
    onSelect: (value: string, option: unknown) => void
    options: Array<{ key?: string; label?: ReactNode; materialOption?: unknown; value?: string }>
    value?: string
    notFoundContent?: ReactNode
  }) => (
    <div>
      <input
        value={value ?? ''}
        onChange={(event) => onChange((event.target as HTMLInputElement).value)}
        onInput={(event) => onChange((event.target as HTMLInputElement).value)}
      />
      <button
        type="button"
        data-clear
        onClick={() => onChange(undefined as unknown as string)}
      >
        clear
      </button>
      {notFoundContent != null && <div data-empty-hint>{notFoundContent}</div>}
      {options.map((option) => (
        <button
          type="button"
          data-option={option.key}
          data-code={option.value}
          key={option.key}
          onClick={() => onSelect(option.value ?? '', option)}
        >
          {option.value}
          {option.label}
        </button>
      ))}
    </div>
  ),
  Spin: () => <span>loading</span>,
}))

import {
  clearMaterialOptionsCache,
  MATERIAL_OPTION_TIMEOUT_MS,
  MaterialCodeAutocomplete,
} from './MaterialCodeAutocomplete'

const firstOption = {
  record_id: 'rec-1',
  material_code: 'MAT-001',
  material_description: '第一条物料',
  rule_model: 'A 型',
  material_unit: '件',
  material_template: '模板A',
  material_category: '五金',
  material_subcategory: '螺丝',
  material_cost_category: '成本A',
}

describe('MaterialCodeAutocomplete', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.useFakeTimers()
    api.fetchMaterialOptions.mockReset()
    clearMaterialOptionsCache()
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
    act(() => vi.advanceTimersByTime(179))
    expect(api.fetchMaterialOptions).not.toHaveBeenCalled()

    await act(async () => {
      vi.advanceTimersByTime(1)
      await Promise.resolve()
    })
    expect(api.fetchMaterialOptions).toHaveBeenCalledWith(
      { keyword: 'MAT', limit: 20 },
      undefined,
      expect.any(AbortSignal),
    )
    expect(container.querySelectorAll('[data-option]').length).toBe(2)

    act(() => container.querySelector('[data-option="rec-2-1"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    expect(onUserChange).toHaveBeenCalledWith('MAT')
    expect(onSelectMaterial).toHaveBeenCalledWith(
      expect.objectContaining({ record_id: 'rec-2', material_description: '第二条物料' }),
    )
  })

  it('puts the exact material code before broader matches', async () => {
    api.fetchMaterialOptions.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [
        { ...firstOption, record_id: 'rec-broader', material_code: 'MAT-001-EXT' },
        { ...firstOption, record_id: 'rec-exact', material_code: 'MAT-001' },
      ],
    })

    act(() => {
      root.render(<MaterialCodeAutocomplete value="MAT-001" />)
    })
    await act(async () => {
      vi.advanceTimersByTime(180)
      await Promise.resolve()
    })

    expect(Array.from(container.querySelectorAll('[data-option]')).map((item) => item.getAttribute('data-code'))).toEqual([
      'MAT-001',
      'MAT-001-EXT',
    ])
  })

  it('shows the complete material details in the option content', async () => {
    const description = '加氢器组件及配套连接件（完整物料说明）'
    const ruleModel = 'SC-3G40A-加长型'
    api.fetchMaterialOptions.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [{ ...firstOption, material_description: description, rule_model: ruleModel }],
    })

    act(() => {
      root.render(<MaterialCodeAutocomplete value="MAT-001" />)
    })
    await act(async () => {
      vi.advanceTimersByTime(180)
      await Promise.resolve()
    })

    expect(container.textContent).toContain(description)
    expect(container.textContent).toContain(`规格型号：${ruleModel}`)
    expect(container.textContent).toContain('主要单位：件')
    expect(container.textContent).toContain('大类：五金')
    expect(container.textContent).toContain('小类：螺丝')
    expect(container.textContent).toContain('成本大类：成本A')
    expect(container.textContent).toContain('模板：模板A')
  })

  it('hides empty optional fields in the option content', async () => {
    api.fetchMaterialOptions.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [
        {
          ...firstOption,
          material_unit: '',
          material_template: '',
          material_category: '',
          material_subcategory: '',
          material_cost_category: '',
        },
      ],
    })

    act(() => {
      root.render(<MaterialCodeAutocomplete value="MAT-001" />)
    })
    await act(async () => {
      vi.advanceTimersByTime(180)
      await Promise.resolve()
    })

    expect(container.textContent).toContain('规格型号：A 型')
    expect(container.textContent).not.toContain('主要单位')
    expect(container.textContent).not.toContain('大类：')
    expect(container.textContent).not.toContain('模板：')
  })

  it('serves a repeated lookup from the client cache', async () => {
    api.fetchMaterialOptions.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [firstOption],
    })

    act(() => {
      root.render(<MaterialCodeAutocomplete value="CACHE-001" />)
    })
    await act(async () => {
      vi.advanceTimersByTime(180)
      await Promise.resolve()
    })
    expect(api.fetchMaterialOptions).toHaveBeenCalledTimes(1)

    act(() => {
      root.unmount()
      root = createRoot(container)
      root.render(<MaterialCodeAutocomplete value="CACHE-001" />)
    })
    await act(async () => Promise.resolve())

    expect(api.fetchMaterialOptions).toHaveBeenCalledTimes(1)
    expect(container.querySelectorAll('[data-option]').length).toBe(1)
  })

  it('fills the linked material fields when a typed code has one exact match', async () => {
    api.fetchMaterialOptions.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [firstOption],
    })
    const onSelectMaterial = vi.fn()

    act(() => {
      root.render(<MaterialCodeAutocomplete onSelectMaterial={onSelectMaterial} />)
    })
    const input = container.querySelector('input') as HTMLInputElement
    act(() => {
      input.value = 'MAT-001'
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })

    await act(async () => {
      vi.advanceTimersByTime(300)
      await Promise.resolve()
    })

    expect(onSelectMaterial).toHaveBeenCalledWith(firstOption)
  })

  it('aborts the active request when the input changes and ignores AbortError', async () => {
    let rejectRequest: ((error: unknown) => void) | undefined
    api.fetchMaterialOptions.mockImplementation(
      () => new Promise((_, reject) => {
        rejectRequest = reject
      }),
    )

    act(() => {
      root.render(<MaterialCodeAutocomplete />)
    })
    const input = container.querySelector('input') as HTMLInputElement
    act(() => {
      input.value = 'MAT-001'
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      vi.advanceTimersByTime(180)
      await Promise.resolve()
    })
    const signal = api.fetchMaterialOptions.mock.calls[0][2] as AbortSignal
    expect(signal.aborted).toBe(false)

    act(() => {
      input.value = 'MAT-002'
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(signal.aborted).toBe(true)

    rejectRequest?.(new DOMException('The operation was aborted.', 'AbortError'))
    await act(async () => Promise.resolve())
    expect(container.textContent).not.toContain('物料编码联想失败')
  })

  it('aborts the request on timeout', async () => {
    api.fetchMaterialOptions.mockImplementation(() => new Promise(() => {}))

    act(() => {
      root.render(<MaterialCodeAutocomplete value="MAT-TIMEOUT" />)
    })
    await act(async () => {
      vi.advanceTimersByTime(180)
      await Promise.resolve()
    })
    const signal = api.fetchMaterialOptions.mock.calls[0][2] as AbortSignal
    expect(signal.aborted).toBe(false)

    await act(async () => {
      vi.advanceTimersByTime(MATERIAL_OPTION_TIMEOUT_MS)
      await Promise.resolve()
    })
    expect(signal.aborted).toBe(true)
    expect(container.textContent).toContain('联想请求超时，请重试')
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
    [new Error('请求失败: 504 Gateway Timeout'), '联想请求超时，请重试'],
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

  it('shows the empty state inside the popup as well as below the input', async () => {
    api.fetchMaterialOptions.mockResolvedValue({ code: 200, message: 'success', data: [] })

    act(() => {
      root.render(<MaterialCodeAutocomplete value="UNKNOWN" />)
    })
    await act(async () => {
      vi.advanceTimersByTime(300)
      await Promise.resolve()
    })

    const hint = container.querySelector('[data-empty-hint]')
    expect(hint).not.toBeNull()
    expect(hint?.textContent).toContain('未找到匹配物料编码，可继续手工输入')
  })

  it('resets the loading state when the input is cleared mid-lookup', async () => {
    api.fetchMaterialOptions.mockImplementation(() => new Promise(() => {}))

    act(() => {
      root.render(<MaterialCodeAutocomplete />)
    })
    const input = container.querySelector('input') as HTMLInputElement
    act(() => {
      input.value = 'MAT-001'
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      vi.advanceTimersByTime(180)
      await Promise.resolve()
    })
    expect(container.textContent).toContain('loading')

    act(() => {
      input.value = ''
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      await Promise.resolve()
    })

    expect(container.textContent).not.toContain('loading')
  })

  it('treats an undefined onChange value as an empty input', async () => {
    api.fetchMaterialOptions.mockImplementation(() => new Promise(() => {}))
    const onChange = vi.fn()
    const onUserChange = vi.fn()

    act(() => {
      root.render(
        <MaterialCodeAutocomplete onChange={onChange} onUserChange={onUserChange} />,
      )
    })
    const input = container.querySelector('input') as HTMLInputElement
    act(() => {
      input.value = 'MAT-001'
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      vi.advanceTimersByTime(180)
      await Promise.resolve()
    })
    expect(container.textContent).toContain('loading')

    // antd AutoComplete 清空时可能回调 undefined，必须按空串处理而不是抛错
    const clearButton = container.querySelector('[data-clear]') as HTMLButtonElement
    await act(async () => {
      clearButton.click()
      await Promise.resolve()
    })

    expect(onChange).toHaveBeenLastCalledWith('')
    expect(onUserChange).toHaveBeenLastCalledWith('')
    expect(container.textContent).not.toContain('loading')
  })

  it('recovers from a stalled lookup with a timeout status and frees the in-flight entry', async () => {
    api.fetchMaterialOptions.mockImplementation(() => new Promise(() => {}))

    act(() => {
      root.render(<MaterialCodeAutocomplete />)
    })
    const input = container.querySelector('input') as HTMLInputElement
    act(() => {
      input.value = 'MAT-001'
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      vi.advanceTimersByTime(180)
      await Promise.resolve()
    })
    expect(container.textContent).toContain('loading')

    // The upstream request never settles; the timeout must end the loading
    // state and surface a retryable status.
    await act(async () => {
      vi.advanceTimersByTime(MATERIAL_OPTION_TIMEOUT_MS)
      await Promise.resolve()
    })
    expect(container.textContent).toContain('联想请求超时，请重试')
    expect(container.textContent).not.toContain('loading')

    // The in-flight entry is released, so typing the same code again issues
    // a fresh lookup instead of reusing the hung promise.
    act(() => {
      input.value = ''
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      await Promise.resolve()
    })
    act(() => {
      input.value = 'MAT-001'
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      vi.advanceTimersByTime(180)
      await Promise.resolve()
    })
    expect(api.fetchMaterialOptions).toHaveBeenCalledTimes(2)
  })

  it('maps a 404 lookup failure to the not-configured status', async () => {
    api.fetchMaterialOptions.mockRejectedValue(new Error('请求失败: 404 Not Found'))

    act(() => {
      root.render(<MaterialCodeAutocomplete />)
    })
    const input = container.querySelector('input') as HTMLInputElement
    act(() => {
      input.value = 'MAT-404'
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      vi.advanceTimersByTime(180)
      await Promise.resolve()
    })

    expect(container.textContent).toContain('物料数据源尚未配置，可继续手工输入')
  })

  it('evicts the oldest cache entry once the cache is full', async () => {
    api.fetchMaterialOptions.mockResolvedValue({ code: 200, message: 'success', data: [] })

    act(() => {
      root.render(<MaterialCodeAutocomplete />)
    })
    const input = container.querySelector('input') as HTMLInputElement
    for (let index = 0; index < 50; index += 1) {
      act(() => {
        input.value = `CACHE-${index}`
        input.dispatchEvent(new Event('input', { bubbles: true }))
      })
      await act(async () => {
        vi.advanceTimersByTime(180)
        await Promise.resolve()
      })
    }
    expect(api.fetchMaterialOptions).toHaveBeenCalledTimes(50)

    // The oldest entry was evicted, so the same keyword is looked up again.
    act(() => {
      input.value = 'CACHE-0'
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      vi.advanceTimersByTime(180)
      await Promise.resolve()
    })
    expect(api.fetchMaterialOptions).toHaveBeenCalledTimes(51)
  })
})
