'use client'

import { useEffect, useMemo, useState } from 'react'
import { AutoComplete } from 'antd'
import { pinyin } from 'pinyin-pro'
import { fetchTrainers } from '@/lib/api/client/hr'

interface Props {
  value?: string
  onChange?: (v: string) => void
  placeholder?: string
  style?: React.CSSProperties
}

/** 授课人选择：候选来自培训师管理，支持中文/全拼/首字母搜索，也可直接手动输入 */
export default function InstructorAutoComplete({ value, onChange, placeholder, style }: Props) {
  const [trainers, setTrainers] = useState<{ name: string; department?: string | null }[]>([])
  const [search, setSearch] = useState('')

  // 后端 page_size 上限 100，超过则分页拉全
  useEffect(() => {
    (async () => {
      try {
        const first = await fetchTrainers({ page: 1, page_size: 100 })
        let all = first.data || []
        const total = first.total || all.length
        if (total > all.length) {
          const pages = Math.ceil(total / 100)
          const rest = await Promise.all(
            Array.from({ length: pages - 1 }, (_, i) => fetchTrainers({ page: i + 2, page_size: 100 })),
          )
          all = all.concat(...rest.map((r) => r.data || []))
        }
        setTrainers(all)
      } catch {
        /* 忽略：候选为空时仍可手动输入 */
      }
    })()
  }, [])

  const enriched = useMemo(
    () =>
      trainers.map((t) => ({
        ...t,
        py: pinyin(t.name, { toneType: 'none' }).replace(/\s/g, ''),
        pyf: pinyin(t.name, { pattern: 'first', toneType: 'none' }).replace(/\s/g, ''),
      })),
    [trainers],
  )

  const options = useMemo(() => {
    const q = search.trim().toLowerCase()
    const list = q
      ? enriched.filter(
          (t) => t.name.includes(search.trim()) || t.py.includes(q) || t.pyf.includes(q),
        )
      : enriched
    return list.map((t) => ({
      value: t.name,
      label: t.department ? `${t.name}（${t.department}）` : t.name,
    }))
  }, [enriched, search])

  return (
    <AutoComplete
      value={value}
      placeholder={placeholder || '授课人（可输入拼音/中文选择培训师，也可手动输入）'}
      style={{ width: '100%', ...style }}
      options={options}
      onSearch={setSearch}
      onChange={(v) => onChange?.(v)}
      filterOption={() => true}
      allowClear
    />
  )
}
