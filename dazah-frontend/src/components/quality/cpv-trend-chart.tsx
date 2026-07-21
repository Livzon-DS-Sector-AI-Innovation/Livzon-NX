"use client"

import ReactECharts from "echarts-for-react"
import type { EChartsOption } from "echarts"
import { CpvTrendResponse } from "@/types/quality-cpv"

interface CpvTrendChartProps {
  trend: CpvTrendResponse | null
  avgValue: number | null
}

export function CpvTrendChart({ trend, avgValue }: CpvTrendChartProps) {
  if (!trend || trend.items.length === 0) {
    return (
      <div className="h-80 bg-gray-50 rounded-lg flex items-center justify-center text-gray-400 text-sm">
        暂无趋势数据
      </div>
    )
  }

  const batchNos = trend.items.map((i) => i.batch_no)
  const values = trend.items.map((i) => i.value)
  const upperLimits = trend.items.map((i) => i.upper_limit)
  const lowerLimits = trend.items.map((i) => i.lower_limit)
  const avgLines = trend.items.map(() => avgValue)

  // 异常点数据
  const abnormalPoints = trend.items.map((item, index) => {
    if (item.is_abnormal) {
      return { value: [index, item.value] }
    }
    return null
  }).filter(Boolean)

  const option: EChartsOption = {
    tooltip: {
      trigger: "axis",
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params : [params]
        let result = `<strong>${p[0]?.axisValue}</strong><br/>`
        p.forEach((item: any) => {
          if (item.value !== null && item.value !== undefined) {
            result += `${item.marker} ${item.seriesName}: ${typeof item.value === "number" ? item.value.toFixed(2) : item.value}<br/>`
          }
        })
        return result
      },
    },
    legend: {
      data: ["实测值", "上限", "下限", "均值"],
      top: 0,
    },
    grid: {
      left: "3%",
      right: "4%",
      bottom: "10%",
      top: "12%",
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: batchNos,
      axisLabel: {
        rotate: 45,
        fontSize: 10,
      },
    },
    yAxis: {
      type: "value",
      scale: true,
    },
    dataZoom: [
      {
        type: "inside",
        start: 0,
        end: 100,
      },
      {
        type: "slider",
        start: 0,
        end: 100,
      },
    ],
    series: [
      {
        name: "实测值",
        type: "line",
        data: values,
        lineStyle: { color: "#3b82f6", width: 2 },
        itemStyle: { color: "#3b82f6" },
        symbolSize: 4,
      },
      {
        name: "上限",
        type: "line",
        data: upperLimits,
        lineStyle: { color: "#ef4444", type: "dashed", width: 1 },
        itemStyle: { color: "#ef4444" },
        symbol: "none",
      },
      {
        name: "下限",
        type: "line",
        data: lowerLimits,
        lineStyle: { color: "#f59e0b", type: "dashed", width: 1 },
        itemStyle: { color: "#f59e0b" },
        symbol: "none",
      },
      {
        name: "均值",
        type: "line",
        data: avgLines,
        lineStyle: { color: "#10b981", type: "dotted", width: 1 },
        itemStyle: { color: "#10b981" },
        symbol: "none",
      },
      {
        name: "异常点",
        type: "scatter",
        data: abnormalPoints,
        itemStyle: { color: "#ef4444" },
        symbolSize: 12,
        symbol: "circle",
        z: 10,
      },
    ],
  }

  return (
    <div>
      <div className="text-sm text-gray-500 mb-2">
        {trend.parameter_name} {trend.parameter_unit ? `(${trend.parameter_unit})` : ""} · 
        共 {trend.items.length} 个数据点，异常点 {trend.items.filter((i) => i.is_abnormal).length} 个
      </div>
      <ReactECharts
        option={option}
        style={{ height: "320px" }}
        notMerge={true}
        opts={{ renderer: "svg" }}
      />
    </div>
  )
}
