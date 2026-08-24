'use client'
// DR 多拉菌素 — 层析及一次结晶岗位台账（原生 <table> + 分级合并单元格，与过滤萃取同风格）

import React from 'react'

type Fmt = 'text' | 'num' | 'pct'
// group 表示合并层级：fl=发酵液批号级，date=生产日期级，chrom=层析批号级，extr=萃取批号级，null=明细（不合并）
interface ColDef { key: string; title: string; group: 'fl' | 'date' | 'chrom' | 'extr' | null; fmt: Fmt }

const COLUMNS: ColDef[] = [
  // 层级1：发酵液批号（跨该批所有生产日期合并）
  { key: 'fl_batch_no', title: '发酵液批号', group: 'fl', fmt: 'text' },
  // 层级2：生产日期
  { key: 'production_date', title: '生产日期', group: 'date', fmt: 'text' },
  // 层级3：层析批号 + 柱号 + 上柱液/洗脱液/收率/湿粉/结晶/母液（同层析批号合并）
  { key: 'chromatography_batch_no', title: '层析生产批号', group: 'chrom', fmt: 'text' },
  { key: 'column_no', title: '柱号', group: 'chrom', fmt: 'text' },
  // 层级4：萃取批号（相邻相同合并，同一萃取批号可对应多行上样）
  { key: 'extraction_batch_no', title: '萃取批号', group: 'extr', fmt: 'text' },
  // 层级5：上样明细（每行独立，不合并）
  { key: 'volume_kl', title: '体积(KL)', group: null, fmt: 'num' },
  { key: 'potency_mg_l', title: '效价(mg/L)', group: null, fmt: 'num' },
  { key: 'product_qty_kg', title: '产品量(kg)', group: null, fmt: 'num' },
  // 层级3 汇总列（层析批号级，仅在首行有值）
  { key: 'total_product_qty_kg', title: '累计产品量', group: 'chrom', fmt: 'num' },
  { key: 'column_load_vol_kl', title: '上柱液体积(KL)', group: null, fmt: 'num' },
  { key: 'column_load_potency_mg_l', title: '上柱液效价(mg/L)', group: null, fmt: 'num' },
  { key: 'column_load_product_kg', title: '上柱液产品量(kg)', group: null, fmt: 'num' },
  { key: 'column_load_total_product_kg', title: '上柱液累计产品量', group: 'chrom', fmt: 'num' },
  { key: 'elution_volume', title: '合格洗脱液体积', group: 'chrom', fmt: 'num' },
  { key: 'elution_unit', title: '合格洗脱液单位', group: 'chrom', fmt: 'num' },
  { key: 'elution_product_kg', title: '产品量(kg)', group: 'chrom', fmt: 'num' },
  { key: 'chromatography_yield', title: '层析收率', group: 'chrom', fmt: 'pct' },
  { key: 'wet_powder_batch_no', title: '一次湿粉生产批号', group: 'chrom', fmt: 'text' },
  { key: 'wet_powder_weight_kg', title: '重量(kg)', group: 'chrom', fmt: 'num' },
  { key: 'wet_powder_content', title: '含量', group: 'chrom', fmt: 'num' },
  { key: 'wet_powder_dry_loss', title: '干燥失重', group: 'chrom', fmt: 'num' },
  { key: 'wet_powder_pure_kg', title: '折纯(kg)', group: 'chrom', fmt: 'num' },
  { key: 'crystallization_yield', title: '结晶收率', group: 'chrom', fmt: 'pct' },
  { key: 'mother_liquor_volume', title: '母液体积', group: 'chrom', fmt: 'num' },
  { key: 'mother_liquor_content', title: '母液含量', group: 'chrom', fmt: 'num' },
  { key: 'mother_liquor_product_qty', title: '产品量', group: 'chrom', fmt: 'num' },
]

// 每个合并层级的合并键（相邻行这些键全部相同时合并）
const GROUP_KEYS: Record<'fl' | 'date' | 'chrom' | 'extr', string[]> = {
  fl: ['fl_batch_no'],
  date: ['fl_batch_no', 'production_date'],
  chrom: ['fl_batch_no', 'production_date', 'chromatography_batch_no', 'column_no'],
  extr: ['fl_batch_no', 'production_date', 'chromatography_batch_no', 'column_no', 'extraction_batch_no'],
}

const fmtVal = (v: any, fmt: Fmt) => {
  if (v == null) return '-'
  if (fmt === 'num') return typeof v === 'number' ? v.toFixed(2) : String(v)
  if (fmt === 'pct') return typeof v === 'number' ? `${(v * 100).toFixed(2)}%` : String(v)
  return String(v)
}

export const DRChromatographyTable: React.FC<{ data: any[] }> = ({ data }) => {
  // 对每个合并层级独立计算组首行的 rowSpan
  const rows = React.useMemo(() => {
    const arr = data.map(r => ({ ...r }))
    ;(Object.keys(GROUP_KEYS) as Array<'fl' | 'date' | 'chrom' | 'extr'>).forEach(g => {
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
            {COLUMNS.map(c => (
              <th key={c.key} className="border border-gray-300 px-1 py-0.5 whitespace-nowrap">{c.title}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={row.id || idx} className="text-center hover:bg-gray-50 align-middle">
              {COLUMNS.map(c => {
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
                return (
                  <td key={c.key} className="border border-gray-300 px-1 py-0.5 whitespace-nowrap">
                    {fmtVal(row[c.key], c.fmt)}
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

export default DRChromatographyTable
