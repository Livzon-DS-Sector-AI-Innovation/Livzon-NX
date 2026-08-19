'use client'
// DR 多拉菌素 — 过滤萃取工段四级嵌套表格组件

import React from 'react'

interface Impurities {
  impurity_6?: number
  impurity_1?: number
  impurity_2?: number
  impurity_7?: number
  impurity_3?: number
  impurity_4?: number
  impurity_5?: number
  rrt_068?: number
  unknown_max_single?: number
  total_impurities?: number
  purity?: number
}

interface TableRow {
  batchDate?: string
  batchNo?: string
  impurities?: Impurities
  batchRowspan: number

  tankNo?: string
  handoverUnit?: number
  handoverVolume?: number
  fermentationProductQty?: number
  actualProductQty?: number
  handoverProductQty?: number
  bacteriaResiduePlates?: number
  batchActualProductQty?: number
  batchHandoverProductQty?: number
  batchBacteriaResiduePlates?: number
  batchFermentationLiquidYield?: number
  tankRowspan: number

  feedingTime?: string
  extractionBatchNo?: string
  feedingPlates?: number
  extractionProductQty?: number
  totalQty?: number
  fermentationLiquidYield?: number
  singleBatchYield?: number
  extractionRowspan: number

  filtrateTankNo: string
  volume?: number
  potency?: number
  filtrateProductQty?: number
  diluteWashVolume?: number
  diluteWashPotency?: number
  diluteWashProductQty?: number
}

export const DRTable: React.FC<{ data: any[] }> = ({ data }) => {
  const FIXED_EXTRACTION_ROWS = 4
  const FIXED_TANK_NOS = ['1#', '2#', '3#', '4#']

  const flattenData = (batches: any[]): TableRow[] => {
    const rows: TableRow[] = []

    batches.forEach(batch => {
      const tanks = batch.tanks || []
      const tankCount = tanks.length

      // 第一步：把整批数据拍平成数组（每个萃取固定 4 行）
      type RowInput = { tank: any; extraction: any; filtrateTankNo: string; filtrate: any }
      const flatRows: RowInput[] = []

      tanks.forEach((tank: any) => {
        ;(tank.extractions || []).forEach((extraction: any) => {
          const filtrateMap: Record<string, any> = {}
          ;(extraction.filtrates || []).forEach((f: any) => { filtrateMap[f.tank_no] = f })
          FIXED_TANK_NOS.forEach((tankNo) => {
            flatRows.push({ tank, extraction, filtrateTankNo: tankNo, filtrate: filtrateMap[tankNo] })
          })
        })
      })

      const totalRows = flatRows.length

      // 提取批次级字段（飞书中是合并单元格，只首行有值）
      let batchActualProductQty: number | undefined
      let batchHandoverProductQty: number | undefined
      let batchBacteriaResiduePlates: number | undefined
      let batchFermentationLiquidYield: number | undefined
      for (const t of tanks) {
        if (batchActualProductQty == null) batchActualProductQty = t.actual_product_qty
        if (batchHandoverProductQty == null) batchHandoverProductQty = t.handover_product_qty
        if (batchBacteriaResiduePlates == null) batchBacteriaResiduePlates = t.bacteria_residue_plates
        for (const e of (t.extractions || [])) {
          if (batchFermentationLiquidYield == null) batchFermentationLiquidYield = e.fermentation_liquid_yield
        }
      }

      // 第二步：均分行数给罐
      const baseRowspan = Math.floor(totalRows / tankCount)
      const remainder = totalRows % tankCount
      const tankRowspans: number[] = []
      for (let i = 0; i < tankCount; i++) {
        tankRowspans.push(baseRowspan + (i < remainder ? 1 : 0))
      }

      let isBatchFirst = true
      let tankIndex = -1
      let tankRowsLeft = 0
      let currentTankRowspan = 0
      let isTankFirst = false
      let currentTank: any = null

      // 萃取：每 4 行切一个萃取
      let isExtractionFirst = false
      let currentExtraction: any = null

      flatRows.forEach((item, rowIdx) => {
        // 罐边界：找到当前行属于哪个罐
        let cumulative = 0
        for (let ti = 0; ti < tankCount; ti++) {
          cumulative += tankRowspans[ti]
          if (rowIdx < cumulative) {
            if (ti !== tankIndex) {
              tankIndex = ti
              currentTank = tanks[ti]
              currentTankRowspan = tankRowspans[ti]
              tankRowsLeft = currentTankRowspan
              isTankFirst = true
            }
            break
          }
        }

        // 萃取边界：每 4 行换一个萃取
        if (rowIdx % FIXED_EXTRACTION_ROWS === 0) {
          currentExtraction = item.extraction
          isExtractionFirst = true
        }

        rows.push({
          batchDate: isBatchFirst ? batch.tank_date : undefined,
          batchNo: isBatchFirst ? batch.batch_no : undefined,
          impurities: isBatchFirst ? batch.impurities : undefined,
          batchRowspan: isBatchFirst ? totalRows : 0,
          batchActualProductQty: isBatchFirst ? batchActualProductQty : undefined,
          batchHandoverProductQty: isBatchFirst ? batchHandoverProductQty : undefined,
          batchBacteriaResiduePlates: isBatchFirst ? batchBacteriaResiduePlates : undefined,
          batchFermentationLiquidYield: isBatchFirst ? batchFermentationLiquidYield : undefined,

          tankNo: isTankFirst ? currentTank?.tank_no : undefined,
          handoverUnit: isTankFirst ? currentTank?.handover_unit : undefined,
          handoverVolume: isTankFirst ? currentTank?.handover_volume : undefined,
          fermentationProductQty: isTankFirst ? currentTank?.fermentation_product_qty : undefined,
          tankRowspan: isTankFirst ? currentTankRowspan : 0,

          feedingTime: isExtractionFirst ? currentExtraction?.feeding_time : undefined,
          extractionBatchNo: isExtractionFirst ? currentExtraction?.extraction_batch_no : undefined,
          feedingPlates: isExtractionFirst ? currentExtraction?.feeding_plates : undefined,
          extractionProductQty: isExtractionFirst ? currentExtraction?.extraction_product_qty : undefined,
          totalQty: isExtractionFirst ? currentExtraction?.total_qty : undefined,
          singleBatchYield: isExtractionFirst ? currentExtraction?.single_batch_yield : undefined,
          extractionRowspan: isExtractionFirst ? FIXED_EXTRACTION_ROWS : 0,

          filtrateTankNo: item.filtrateTankNo,
          volume: item.filtrate?.volume,
          potency: item.filtrate?.potency,
          filtrateProductQty: item.filtrate?.product_qty,
          diluteWashVolume: item.filtrate?.dilute_wash_volume,
          diluteWashPotency: item.filtrate?.dilute_wash_potency,
          diluteWashProductQty: item.filtrate?.dilute_wash_product_qty,
        })

        isBatchFirst = false
        isTankFirst = false
        isExtractionFirst = false
        tankRowsLeft--
      })
    })

    return rows
  }

  const rows = flattenData(data)

  if (!data || data.length === 0) {
    return <div className="text-center py-10 text-gray-400">暂无数据，请先导入</div>
  }

  return (
    <div className="overflow-auto">
      <table className="border-collapse border border-gray-300 text-[10px] leading-tight w-full">
        <thead>
          <tr className="bg-[#fafafa] text-center text-[9px] align-middle">
            <th className="border border-gray-300 px-0.5 py-0.5">接罐日期</th>
            <th className="border border-gray-300 px-0.5 py-0.5">批号</th>
            <th className="border border-gray-300 px-0.5 py-0.5">罐号</th>
            <th className="border border-gray-300 px-0.5 py-0.5">交接单位<br/>(mg/l)</th>
            <th className="border border-gray-300 px-0.5 py-0.5">交接体积<br/>(m³)</th>
            <th className="border border-gray-300 px-0.5 py-0.5">产品量<br/>(kg)</th>
            <th className="border border-gray-300 px-0.5 py-0.5">实际<br/>产品量</th>
            <th className="border border-gray-300 px-0.5 py-0.5">交接<br/>产品量</th>
            <th className="border border-gray-300 px-0.5 py-0.5">菌渣<br/>盘数</th>
            <th className="border border-gray-300 px-0.5 py-0.5">投料时间</th>
            <th className="border border-gray-300 px-0.5 py-0.5">萃取批号</th>
            <th className="border border-gray-300 px-0.5 py-0.5">投料<br/>盘数</th>
            <th className="border border-gray-300 px-0.5 py-0.5">产品量</th>
            <th className="border border-gray-300 px-0.5 py-0.5">罐号</th>
            <th className="border border-gray-300 px-0.5 py-0.5">体积</th>
            <th className="border border-gray-300 px-0.5 py-0.5">效价</th>
            <th className="border border-gray-300 px-0.5 py-0.5">产品量</th>
            <th className="border border-gray-300 px-0.5 py-0.5">合计</th>
            <th className="border border-gray-300 px-0.5 py-0.5">萃取液对应<br/>发酵液收率</th>
            <th className="border border-gray-300 px-0.5 py-0.5">单批萃取<br/>收率</th>
            <th className="border border-gray-300 px-0.5 py-0.5">体积</th>
            <th className="border border-gray-300 px-0.5 py-0.5">效价</th>
            <th className="border border-gray-300 px-0.5 py-0.5">产品量</th>
            <th className="border border-gray-300 px-0.5 py-0.5">杂质6</th>
            <th className="border border-gray-300 px-0.5 py-0.5">杂质1</th>
            <th className="border border-gray-300 px-0.5 py-0.5">杂质2</th>
            <th className="border border-gray-300 px-0.5 py-0.5">杂质7</th>
            <th className="border border-gray-300 px-0.5 py-0.5">杂质3</th>
            <th className="border border-gray-300 px-0.5 py-0.5">杂质4</th>
            <th className="border border-gray-300 px-0.5 py-0.5">杂质5</th>
            <th className="border border-gray-300 px-0.5 py-0.5">RRT0.68</th>
            <th className="border border-gray-300 px-0.5 py-0.5">未知最<br/>大单杂</th>
            <th className="border border-gray-300 px-0.5 py-0.5">总杂</th>
            <th className="border border-gray-300 px-0.5 py-0.5">纯度</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={`${row.batchNo}-${row.tankNo}-${idx}`} className="text-center hover:bg-gray-50 align-middle">
              {/* 批号级 */}
              {row.batchRowspan > 0 && (
                <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5">
                  {row.batchDate}
                </td>
              )}
              {row.batchRowspan > 0 && (
                <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5 font-bold">
                  {row.batchNo}
                </td>
              )}

              {/* 发酵罐级 */}
              {row.tankRowspan > 0 && (
                <>
                  <td rowSpan={row.tankRowspan} className="border border-gray-300 px-0.5 py-0.5 font-semibold">
                    {row.tankNo}
                  </td>
                  <td rowSpan={row.tankRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.handoverUnit}
                  </td>
                  <td rowSpan={row.tankRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.handoverVolume}
                  </td>
                  <td rowSpan={row.tankRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.fermentationProductQty != null ? row.fermentationProductQty.toFixed(2) : '-'}
                  </td>
                </>
              )}

              {/* 批次级（实际产品量 / 交接产品量 / 菌渣盘数 — 飞书中为合并单元格） */}
              {row.batchRowspan > 0 && (
                <>
                  <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.batchActualProductQty != null ? row.batchActualProductQty.toFixed(2) : '-'}
                  </td>
                  <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.batchHandoverProductQty != null ? row.batchHandoverProductQty.toFixed(2) : '-'}
                  </td>
                  <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.batchBacteriaResiduePlates ?? '-'}
                  </td>
                </>
              )}

              {/* 萃取批次级 */}
              {row.extractionRowspan > 0 && (
                <>
                  <td rowSpan={row.extractionRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.feedingTime}
                  </td>
                  <td rowSpan={row.extractionRowspan} className="border border-gray-300 px-0.5 py-0.5 font-medium">
                    {row.extractionBatchNo}
                  </td>
                  <td rowSpan={row.extractionRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.feedingPlates}
                  </td>
                  <td rowSpan={row.extractionRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.extractionProductQty != null ? row.extractionProductQty.toFixed(2) : '-'}
                  </td>
                </>
              )}

              {/* 滤液罐级 */}
              <td className="border border-gray-300 px-0.5 py-0.5">{row.filtrateTankNo}</td>
              <td className="border border-gray-300 px-0.5 py-0.5">{row.volume ?? '-'}</td>
              <td className="border border-gray-300 px-0.5 py-0.5">{row.potency != null ? `${row.potency}` : '-'}</td>
              <td className="border border-gray-300 px-0.5 py-0.5">{row.filtrateProductQty != null ? row.filtrateProductQty.toFixed(2) : '-'}</td>

              {/* 萃取批次级续 */}
              {row.extractionRowspan > 0 && (
                <td rowSpan={row.extractionRowspan} className="border border-gray-300 px-0.5 py-0.5 font-semibold">
                  {row.totalQty != null ? row.totalQty.toFixed(2) : '-'}
                </td>
              )}
              {/* 批次级：发酵液收率（飞书合并单元格） */}
              {row.batchRowspan > 0 && (
                <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5">
                  {row.batchFermentationLiquidYield != null ? `${(row.batchFermentationLiquidYield * 100).toFixed(2)}%` : '-'}
                </td>
              )}
              {row.extractionRowspan > 0 && (
                <td rowSpan={row.extractionRowspan} className="border border-gray-300 px-0.5 py-0.5">
                  {row.singleBatchYield != null ? `${(row.singleBatchYield * 100).toFixed(2)}%` : '-'}
                </td>
              )}

              {/* 稀洗液级 */}
              <td className="border border-gray-300 px-0.5 py-0.5">{row.diluteWashVolume ?? '-'}</td>
              <td className="border border-gray-300 px-0.5 py-0.5">{row.diluteWashPotency ?? '-'}</td>
              <td className="border border-gray-300 px-0.5 py-0.5">{row.diluteWashProductQty != null ? row.diluteWashProductQty.toFixed(2) : '-'}</td>

              {/* 杂质列 */}
              {row.batchRowspan > 0 && (
                <>
                  <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.impurities?.impurity_6 ?? '-'}
                  </td>
                  <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.impurities?.impurity_1 ?? '-'}
                  </td>
                  <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.impurities?.impurity_2 ?? '-'}
                  </td>
                  <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.impurities?.impurity_7 ?? '-'}
                  </td>
                  <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.impurities?.impurity_3 ?? '-'}
                  </td>
                  <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.impurities?.impurity_4 ?? '-'}
                  </td>
                  <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.impurities?.impurity_5 ?? '-'}
                  </td>
                  <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.impurities?.rrt_068 ?? '-'}
                  </td>
                  <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.impurities?.unknown_max_single ?? '-'}
                  </td>
                  <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5">
                    {row.impurities?.total_impurities ?? '-'}
                  </td>
                  <td rowSpan={row.batchRowspan} className="border border-gray-300 px-0.5 py-0.5 font-bold">
                    {row.impurities?.purity != null ? `${row.impurities.purity}%` : '-'}
                  </td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default DRTable
