'use client'

import { useEffect, useMemo, useState } from 'react'
import { AutoComplete, Spin } from 'antd'
import type { DefaultOptionType } from 'antd/es/select'
import { fetchMaterialOptions } from '@/lib/api/purchasing'
import type { MaterialOptionResponse } from '@/types/purchasing'

type MaterialOptionEntry = DefaultOptionType & {
  materialOption: MaterialOptionResponse
}

export type MaterialCodeAutocompleteProps = {
  value?: string
  onChange?: (value: string) => void
  onUserChange?: (value: string) => void
  onSelectMaterial?: (option: MaterialOptionResponse) => void
  placeholder?: string
}

function getErrorStatus(error: unknown): number | undefined {
  const message = error instanceof Error ? error.message : String(error)
  const match = message.match(/请求失败:\s*(\d{3})/)
  return match ? Number(match[1]) : undefined
}

function getStatusMessage(status: 'idle' | 'empty' | 'not-configured' | 'unavailable' | 'error') {
  switch (status) {
    case 'empty':
      return '未找到匹配物料编码，可继续手工输入'
    case 'not-configured':
      return '物料数据源尚未配置，可继续手工输入'
    case 'unavailable':
      return '飞书物料数据源暂时不可用，可继续手工输入'
    case 'error':
      return '物料编码联想失败，可继续手工输入'
    default:
      return ''
  }
}

function optionLabel(option: MaterialOptionResponse) {
  return (
    <div className="min-w-[260px] py-0.5">
      <div className="flex items-center gap-2">
        <span className="font-medium text-[var(--color-charcoal)]">{option.material_code}</span>
        <span className="truncate text-[var(--color-steel)]">
          {option.material_description || '暂无物料说明'}
        </span>
      </div>
      <div className="mt-0.5 text-[12px] text-[var(--color-stone)]">
        规格型号：{option.rule_model || '暂无'}
      </div>
    </div>
  )
}

export function MaterialCodeAutocomplete({
  value,
  onChange,
  onUserChange,
  onSelectMaterial,
  placeholder = '输入物料编码联想',
}: MaterialCodeAutocompleteProps) {
  const [inputValue, setInputValue] = useState(value ?? '')
  const [options, setOptions] = useState<MaterialOptionEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<
    'idle' | 'empty' | 'not-configured' | 'unavailable' | 'error'
  >('idle')

  const searchValue = (value ?? inputValue).trim()

  useEffect(() => {
    if (!searchValue) return

    let cancelled = false
    const timer = window.setTimeout(async () => {
      setLoading(true)
      try {
        const response = await fetchMaterialOptions({ keyword: searchValue, limit: 20 })
        if (cancelled) return
        const entries = (response.data ?? []).map((option, index) => ({
          key: `${option.record_id || 'record'}-${index}`,
          value: option.material_code,
          label: optionLabel(option),
          materialOption: option,
        }))
        setOptions(entries)
        setStatus(entries.length > 0 ? 'idle' : 'empty')
      } catch (error) {
        if (cancelled) return
        const httpStatus = getErrorStatus(error)
        setOptions([])
        setStatus(
          httpStatus === 404
            ? 'not-configured'
            : httpStatus === 502 || httpStatus === 503 || httpStatus === 504
              ? 'unavailable'
              : 'error'
        )
      } finally {
        if (!cancelled) setLoading(false)
      }
    }, 300)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [searchValue])

  const helperText = useMemo(() => getStatusMessage(status), [status])

  return (
    <div>
      <AutoComplete
        value={value ?? inputValue}
        options={searchValue ? options : []}
        filterOption={false}
        onChange={(nextValue) => {
          setInputValue(nextValue)
          onChange?.(nextValue)
          onUserChange?.(nextValue)
        }}
        onSelect={(nextValue, option) => {
          const selected = (option as MaterialOptionEntry).materialOption
          setInputValue(nextValue)
          onChange?.(nextValue)
          if (selected) onSelectMaterial?.(selected)
        }}
        placeholder={placeholder}
        notFoundContent={searchValue && loading ? <Spin size="small" /> : null}
        className="w-full"
        allowClear
      />
      {searchValue && helperText && (
        <div className="mt-1 text-[11px] leading-4 text-[var(--color-stone)]" aria-live="polite">
          {helperText}
        </div>
      )}
    </div>
  )
}
