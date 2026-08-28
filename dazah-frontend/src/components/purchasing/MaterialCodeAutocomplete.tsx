'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { AutoComplete, Spin } from 'antd'
import type { DefaultOptionType } from 'antd/es/select'
import { fetchMaterialOptions } from '@/lib/api/purchasing'
import type { MaterialOptionResponse } from '@/types/purchasing'
import {
  getPurchaseDetailInputWidth,
  purchaseDetailInputSizing,
} from './PurchaseDetailAutoInput'

type MaterialOptionEntry = DefaultOptionType & {
  materialOption: MaterialOptionResponse
}

type MaterialOptionsCacheEntry = {
  expiresAt: number
  options: MaterialOptionResponse[]
}

const MATERIAL_OPTION_LIMIT = 20
const MATERIAL_OPTION_DEBOUNCE_MS = 180
const MATERIAL_OPTION_CACHE_TTL_MS = 5 * 60 * 1000
const MATERIAL_OPTION_CACHE_MAX_ENTRIES = 48
const MATERIAL_OPTION_POPUP_MIN_WIDTH = 360
// 必须大于后端联想总预算（MATERIAL_OPTION_TOTAL_TIMEOUT_SECONDS = 12 秒），
// 否则前端会先中断请求而后端仍在执行，飞书慢查询也会被误报为超时。
export const MATERIAL_OPTION_TIMEOUT_MS = 15_000

const materialOptionsCache = new Map<string, MaterialOptionsCacheEntry>()

export type MaterialCodeAutocompleteProps = {
  value?: string
  onChange?: (value: string) => void
  onUserChange?: (value: string) => void
  onSelectMaterial?: (option: MaterialOptionResponse) => void
  placeholder?: string
}

function isAbortError(error: unknown) {
  return error instanceof DOMException
    ? error.name === 'AbortError'
    : error instanceof Error && error.name === 'AbortError'
}

function getErrorStatus(error: unknown): number | undefined {
  const message = error instanceof Error ? error.message : String(error)
  const match = message.match(/请求失败:\s*(\d{3})/)
  return match ? Number(match[1]) : undefined
}

function normalizeSearchValue(value: string) {
  return value.trim().toLowerCase()
}

function getCachedMaterialOptions(keyword: string) {
  const cacheKey = normalizeSearchValue(keyword)
  const entry = materialOptionsCache.get(cacheKey)
  if (!entry) return undefined
  if (entry.expiresAt <= Date.now()) {
    materialOptionsCache.delete(cacheKey)
    return undefined
  }

  // Refresh insertion order so frequently used searches remain in the small LRU cache.
  materialOptionsCache.delete(cacheKey)
  materialOptionsCache.set(cacheKey, entry)
  return entry.options
}

function cacheMaterialOptions(keyword: string, options: MaterialOptionResponse[]) {
  const cacheKey = normalizeSearchValue(keyword)
  materialOptionsCache.delete(cacheKey)
  materialOptionsCache.set(cacheKey, {
    expiresAt: Date.now() + MATERIAL_OPTION_CACHE_TTL_MS,
    options: [...options],
  })

  while (materialOptionsCache.size > MATERIAL_OPTION_CACHE_MAX_ENTRIES) {
    const oldestKey = materialOptionsCache.keys().next().value
    if (oldestKey === undefined) break
    materialOptionsCache.delete(oldestKey)
  }
}

function withTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number,
  onTimeout: () => void,
): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      onTimeout()
      reject(new Error('请求超时，请稍后重试'))
    }, timeoutMs)
  })
  return Promise.race([promise, timeout]).finally(() => {
    if (timer !== undefined) clearTimeout(timer)
  })
}

function getMaterialOptions(keyword: string, controller: AbortController) {
  const cached = getCachedMaterialOptions(keyword)
  if (cached) return Promise.resolve(cached)

  const request = fetchMaterialOptions(
    {
      keyword: keyword.trim(),
      limit: MATERIAL_OPTION_LIMIT,
    },
    undefined,
    controller.signal,
  )
  return withTimeout(
    request.then((response) => {
      const options = response.data ?? []
      cacheMaterialOptions(keyword, options)
      return options
    }),
    MATERIAL_OPTION_TIMEOUT_MS,
    () => controller.abort(),
  )
}

export function clearMaterialOptionsCache() {
  materialOptionsCache.clear()
}

function materialMatchRank(option: MaterialOptionResponse, keyword: string) {
  const code = normalizeSearchValue(option.material_code)
  const normalizedKeyword = normalizeSearchValue(keyword)
  if (code === normalizedKeyword) return 0
  if (code.startsWith(normalizedKeyword)) return 1
  return 2
}

function sortMaterialOptions(
  options: MaterialOptionResponse[],
  keyword: string,
) {
  return options
    .map((option, index) => ({
      index,
      option,
      rank: materialMatchRank(option, keyword),
    }))
    .sort((left, right) => left.rank - right.rank || left.index - right.index)
    .map(({ option }) => option)
}

type MaterialOptionStatus =
  | 'idle'
  | 'empty'
  | 'timeout'
  | 'not-configured'
  | 'unavailable'
  | 'error'

function getStatusMessage(status: MaterialOptionStatus) {
  switch (status) {
    case 'empty':
      return '未找到匹配物料编码，可继续手工输入'
    case 'timeout':
      return '联想请求超时，请重试'
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
  const extraMeta = [
    option.material_category && `大类：${option.material_category}`,
    option.material_subcategory && `小类：${option.material_subcategory}`,
    option.material_cost_category && `成本大类：${option.material_cost_category}`,
    option.material_template && `模板：${option.material_template}`,
  ].filter(Boolean)
  return (
    <div
      className="whitespace-normal py-0.5 leading-5"
      style={{ minWidth: MATERIAL_OPTION_POPUP_MIN_WIDTH - 32 }}
    >
      <div className="flex items-start gap-2 whitespace-normal">
        <span className="shrink-0 whitespace-nowrap font-medium text-[var(--color-charcoal)]">
          {option.material_code}
        </span>
        <span className="min-w-0 whitespace-normal break-words text-[var(--color-steel)]">
          {option.material_description || '暂无物料说明'}
        </span>
      </div>
      <div className="mt-0.5 whitespace-normal break-words text-[12px] text-[var(--color-stone)]">
        规格型号：{option.rule_model || '暂无'}
        {option.material_unit ? ` ｜ 主要单位：${option.material_unit}` : ''}
      </div>
      {extraMeta.length > 0 && (
        <div className="mt-0.5 whitespace-normal break-words text-[12px] text-[var(--color-stone)]">
          {extraMeta.join(' ｜ ')}
        </div>
      )}
    </div>
  )
}

function isMaterialOptionEntry(value: unknown): value is MaterialOptionEntry {
  return Boolean(
    value &&
      typeof value === 'object' &&
      'materialOption' in value &&
      value.materialOption,
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
  const [status, setStatus] = useState<MaterialOptionStatus>('idle')
  const onSelectMaterialRef = useRef(onSelectMaterial)
  const manuallyEditedRef = useRef(false)
  const selectedValueRef = useRef<string | null>(null)

  useEffect(() => {
    onSelectMaterialRef.current = onSelectMaterial
  }, [onSelectMaterial])

  const searchValue = (value ?? inputValue).trim()

  useEffect(() => {
    if (!searchValue) return

    let cancelled = false
    const controller = new AbortController()
    const applyOptions = (materialOptions: MaterialOptionResponse[]) => {
      if (cancelled) return
      const entries = sortMaterialOptions(materialOptions, searchValue).map((option, index) => ({
        key: `${option.record_id || 'record'}-${index}`,
        value: option.material_code,
        label: optionLabel(option),
        materialOption: option,
      }))
      setOptions(entries)
      setStatus(entries.length > 0 ? 'idle' : 'empty')

      const normalizedSearchValue = normalizeSearchValue(searchValue)
      const exactMatches = entries.filter(
        (entry) => normalizeSearchValue(entry.materialOption.material_code) === normalizedSearchValue,
      )
      if (manuallyEditedRef.current && exactMatches.length === 1) {
        onSelectMaterialRef.current?.(exactMatches[0].materialOption)
      }
    }

    const cached = getCachedMaterialOptions(searchValue)
    if (cached) {
      applyOptions(cached)
      queueMicrotask(() => {
        if (!cancelled) setLoading(false)
      })
      return () => {
        cancelled = true
      }
    }

    const timer = window.setTimeout(() => {
      setOptions([])
      setStatus('idle')
      setLoading(true)
      void getMaterialOptions(searchValue, controller)
        .then(applyOptions)
        .catch((error: unknown) => {
          if (cancelled || isAbortError(error)) return
          const httpStatus = getErrorStatus(error)
          const isTimeout =
            error instanceof Error && error.message.includes('请求超时')
          setOptions([])
          setStatus(
            isTimeout
              ? 'timeout'
              : httpStatus === 404
                ? 'not-configured'
                : httpStatus === 502 || httpStatus === 503
                  ? 'unavailable'
                  : httpStatus === 504
                    ? 'timeout'
                    : 'error'
          )
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }, MATERIAL_OPTION_DEBOUNCE_MS)

    return () => {
      cancelled = true
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [searchValue])

  const helperText = useMemo(() => getStatusMessage(status), [status])
  const inputWidth = getPurchaseDetailInputWidth(
    value ?? inputValue,
    purchaseDetailInputSizing.materialCode,
  )

  return (
    <div>
      <AutoComplete
        value={value ?? inputValue}
        options={searchValue ? options : []}
        filterOption={false}
        popupMatchSelectWidth={MATERIAL_OPTION_POPUP_MIN_WIDTH}
        optionRender={(option) =>
          isMaterialOptionEntry(option.data)
            ? optionLabel(option.data.materialOption)
            : option.label
        }
        onChange={(nextValue) => {
          // antd AutoComplete 清空等场景会回调 undefined，统一按空串处理
          const safeValue = nextValue ?? ''
          const isSelection = selectedValueRef.current === safeValue
          selectedValueRef.current = null
          setInputValue(safeValue)
          // A lookup that was in flight when the input was cleared must not
          // leave the field stuck in a loading state.
          if (!safeValue.trim()) setLoading(false)
          onChange?.(safeValue)
          if (!isSelection) {
            manuallyEditedRef.current = true
            onUserChange?.(safeValue)
          }
        }}
        onSelect={(nextValue, option) => {
          selectedValueRef.current = nextValue
          manuallyEditedRef.current = false
          const selected = (option as MaterialOptionEntry).materialOption
          setInputValue(nextValue)
          onChange?.(nextValue)
          if (selected) onSelectMaterial?.(selected)
        }}
        placeholder={placeholder}
        notFoundContent={
          searchValue ? (
            loading ? (
              <Spin size="small" />
            ) : options.length === 0 && status !== 'idle' ? (
              <div className="px-3 py-2 text-[12px] leading-5 text-[var(--color-stone)]">
                {helperText}
              </div>
            ) : null
          ) : null
        }
        className="w-full"
        style={{
          width: inputWidth,
          minWidth: purchaseDetailInputSizing.materialCode.minWidth,
          maxWidth: purchaseDetailInputSizing.materialCode.maxWidth,
        }}
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
