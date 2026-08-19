'use client'
// DR 多拉菌素 — 精制岗位台账通用组件（原生 <table> + 分级合并单元格，与层析台账同风格）

import React from 'react'
import { Popover } from 'antd'
import { FileTextOutlined } from '@ant-design/icons'

type Fmt = 'text' | 'num' | 'num3' | 'pct'
// group 表示合并层级：fl=发酵液批号级，date=生产日期级，refine=生产批号级，null=明细（不合并）
export interface RefineColDef { key: string; title: string; group: 'fl' | 'date' | 'refine' | null; fmt: Fmt; remark?: boolean; multiline?: boolean }

// 一次精制默认列
const DEFAULT_COLUMNS: RefineColDef[] = [
  // 层级1：发酵液批号（跨该批所有生产日期合并）
  { key: 'fl_batch_no', title: '发酵液批号', group: 'fl', fmt: 'text' },
  // 层级2：生产日期
  { key: 'production_date', title: '生产日期', group: 'date', fmt: 'text' },
  // 层级3：生产批号
  { key: 'refinement_batch_no', title: '生产批号', group: 'refine', fmt: 'text' },
  // 层级4：一次湿粉投料明细（每行独立，不合并）
  { key: 'feed_weight_kg', title: '重量(kg)', group: null, fmt: 'num' },
  { key: 'feed_content', title: '含量', group: null, fmt: 'num' },
  { key: 'feed_dry_loss', title: '干燥失重', group: null, fmt: 'num' },
  { key: 'feed_pure_kg', title: '折纯(kg)', group: null, fmt: 'num' },
  // 母液
  { key: 'mother_liquor_volume', title: '母液体积', group: null, fmt: 'num' },
  { key: 'mother_liquor_unit', title: '母液单位', group: null, fmt: 'num' },
  { key: 'mother_liquor_product_kg', title: '母液产品量(kg)', group: null, fmt: 'num' },
  // 一次湿粉成品方法杂质
  { key: 'impurity_6', title: '杂质6\nRRT=0.51(≤0.39)', group: null, fmt: 'num3' },
  { key: 'impurity_1', title: '杂质1\nRRT=0.59(不得检出)', group: null, fmt: 'num3' },
  { key: 'impurity_2', title: '杂质2\nRRT=0.69(≤0.7)', group: null, fmt: 'num3' },
  { key: 'impurity_7', title: '杂质7\nRRT=0.72(≤0.36)', group: null, fmt: 'num3' },
  { key: 'impurity_3', title: '杂质3\nRRT=0.88(≤0.8)', group: null, fmt: 'num3' },
  { key: 'impurity_4', title: '杂质4\nRRT=1.38(≤0.35)', group: null, fmt: 'num3' },
  { key: 'impurity_5', title: '杂质5\nRRT=1.56(≤0.50)', group: null, fmt: 'num3' },
  { key: 'rrt_068', title: 'RRT=0.68', group: null, fmt: 'num3' },
  { key: 'unknown_max_single', title: '未知最大单杂', group: null, fmt: 'num3' },
  { key: 'total_impurities', title: '总杂', group: null, fmt: 'num3' },
  { key: 'purity', title: '纯度', group: null, fmt: 'num3' },
]

// 每个合并层级的合并键（相邻行这些键全部相同时合并）
// 注意：refine（生产批号）层去掉 fl_batch_no，因为一个精制批可跨多个发酵液批号投料
//（如 DR-F2-24016-5/017-1 同时投 DR-24016、DR-24017 的湿粉），需要让生产批号跨发酵液批号合并成一格
const GROUP_KEYS: Record<'fl' | 'date' | 'refine', string[]> = {
  fl: ['fl_batch_no'],
  date: ['fl_batch_no', 'production_date'],
  refine: ['production_date', 'refinement_batch_no'],
}

const fmtVal = (v: any, fmt: Fmt) => {
  if (v == null) return '-'
  if (fmt === 'num') {
    if (typeof v === 'number') return v.toFixed(2)
    // 兼容数字字符串（如活性炭加量 '16.77892162716'、'16kg'、'16.5'），统一保留两位小数
    const s = String(v).trim()
    if (s === '' || s === '-') return '-'
    const n = parseFloat(s)
    return Number.isNaN(n) ? s : n.toFixed(2)
  }
  if (fmt === 'num3') return typeof v === 'number' ? v.toFixed(3) : String(v)
  if (fmt === 'pct') return typeof v === 'number' ? `${(v * 100).toFixed(2)}%` : String(v)
  return String(v)
}

// 多行列：只把换行符 \n 转成 <br/>，其余保持单行（nowrap 禁止在 / 等符号处自动断行）
const renderMultiline = (v: any) => {
  if (v == null) return '-'
  return String(v).split('\n').map((line, i) => (
    <React.Fragment key={i}>
      {i > 0 && <br />}
      {line}
    </React.Fragment>
  ))
}

export const DRRefinementTable: React.FC<{ data: any[]; columns?: RefineColDef[] }> = ({ data, columns }) => {
  const cols = columns || DEFAULT_COLUMNS

  // 对每个合并层级独立计算组首行的 rowSpan
  const rows = React.useMemo(() => {
    const arr = data.map(r => ({ ...r }))
    ;(Object.keys(GROUP_KEYS) as Array<'fl' | 'date' | 'refine'>).forEach(g => {
      const keys = GROUP_KEYS[g]
      let i = 0
      while (i < arr.length) {
        let j = i + 1
        while (j < arr.length && keys.every(k => arr[j][k] === arr[i][k])) j++
        arr[i][`_span_${g}`] = j - i
        i = j
      }
    })
    return arr
  }, [data])

  if (!data || data.length === 0) {
    return <div className="text-center py-10 text-gray-400">暂无数据，请先导入</div>
  }

  return (
    <div className="overflow-auto">
      <table className="border-collapse border border-gray-300 text-[10px] leading-tight w-full">
        <thead>
          <tr className="bg-[#fafafa] text-center text-[9px] align-middle">
            {cols.map(c => (
              <th key={c.key} className="border border-gray-300 px-1 py-0.5 whitespace-pre-line">{c.title}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={row.id || idx} className="text-center hover:bg-gray-50 align-middle">
              {cols.map(c => {
                if (c.group) {
                  const span = row[`_span_${c.group}`] as number | undefined
                  if (span && span > 0) {
                    const bold = c.group === 'fl' ? ' font-bold' : ' font-medium'
                    return (
                      <td key={c.key} rowSpan={span}
                        className={`border border-gray-300 px-1 py-0.5 whitespace-nowrap${bold}`}>
                        {fmtVal(row[c.key], c.fmt)}
                      </td>
                    )
                  }
                  return null // 组内其余行不渲染该单元格（被 rowSpan 覆盖）
                }
                // 备注列：有备注时只显示展开入口图标，点击弹气泡展示完整内容；无备注留空
                if (c.remark) {
                  const val = row[c.key]
                  const has = val != null && String(val).trim() !== ''
                  return (
                    <td key={c.key} className="border border-gray-300 px-1 py-0.5 text-center">
                      {has ? (
                        <Popover
                          trigger="click"
                          content={
                            <div className="max-w-[360px] whitespace-pre-wrap break-all text-[12px] leading-relaxed">
                              {String(val)}
                            </div>
                          }
                        >
                          <FileTextOutlined className="text-blue-500 cursor-pointer text-[13px]" />
                        </Popover>
                      ) : null}
                    </td>
                  )
                }
                return (
                  <td key={c.key} className={`border border-gray-300 px-1 py-0.5 whitespace-nowrap${c.multiline ? ' text-left' : ''}`}>
                    {c.multiline ? renderMultiline(row[c.key]) : fmtVal(row[c.key], c.fmt)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default DRRefinementTable
