"use client"

import { useEffect, useMemo, useState } from "react"
import { useParams } from "next/navigation"
import Link from "next/link"
import { fetchCpvProduct, fetchCpvParameters, fetchCpvStatistics, fetchCpvTrend } from "@/lib/api/quality-cpv"
import { CpvProduct, CpvParameter, CpvStatistics, CpvTrendResponse } from "@/types/quality-cpv"
import { CpvTrendChart } from "@/components/quality"

export default function CpvProductDetailPage() {
  const params = useParams()
  const productId = params.productId as string

  const [product, setProduct] = useState<CpvProduct | null>(null)
  const [cppParams, setCppParams] = useState<CpvParameter[]>([])
  const [cqaParams, setCqaParams] = useState<CpvParameter[]>([])
  const [selectedType, setSelectedType] = useState<"CPP" | "CQA">("CPP")
  const [selectedParamId, setSelectedParamId] = useState<string>("")
  const [statistics, setStatistics] = useState<CpvStatistics | null>(null)
  const [trend, setTrend] = useState<CpvTrendResponse | null>(null)
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const [prod, cpp, cqa] = await Promise.all([
          fetchCpvProduct(productId),
          fetchCpvParameters(productId, "CPP"),
          fetchCpvParameters(productId, "CQA"),
        ])
        if (!cancelled) {
          setProduct(prod)
          setCppParams(cpp)
          setCqaParams(cqa)
          // 自动选择第一个CPP参数
          if (cpp.length > 0) {
            setSelectedParamId(cpp[0].id)
          }
        }
      } catch (err) {
        console.error(err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [productId])

  const allParams = selectedType === "CPP" ? cppParams : cqaParams

  useEffect(() => {
    if (!selectedParamId) return
    let cancelled = false
    const load = async () => {
      try {
        const [stats, trendData] = await Promise.all([
          fetchCpvStatistics(productId, selectedParamId, { start_date: startDate || undefined, end_date: endDate || undefined }),
          fetchCpvTrend(productId, selectedParamId, { start_date: startDate || undefined, end_date: endDate || undefined }),
        ])
        if (!cancelled) {
          setStatistics(stats)
          setTrend(trendData)
        }
      } catch (err) {
        console.error(err)
      }
    }
    load()
    return () => { cancelled = true }
  }, [selectedParamId, startDate, endDate, productId])

  async function loadData() {
    try {
      setLoading(true)
      const [prod, cpp, cqa] = await Promise.all([
        fetchCpvProduct(productId),
        fetchCpvParameters(productId, "CPP"),
        fetchCpvParameters(productId, "CQA"),
      ])
      setProduct(prod)
      setCppParams(cpp)
      setCqaParams(cqa)
    } catch (err) { console.error(err) } finally { setLoading(false) }
  }

  async function loadTrendAndStats() {
    try {
      const [stats, trendData] = await Promise.all([
        fetchCpvStatistics(productId, selectedParamId, { start_date: startDate || undefined, end_date: endDate || undefined }),
        fetchCpvTrend(productId, selectedParamId, { start_date: startDate || undefined, end_date: endDate || undefined }),
      ])
      setStatistics(stats)
      setTrend(trendData)
    } catch (err) { console.error(err) }
  }

  if (loading) return <div className="p-6 text-center text-gray-500">加载中...</div>
  if (!product) return <div className="p-6 text-center text-red-500">产品不存在</div>

  return (
    <div className="p-6 space-y-6">
      {/* 面包屑 */}
      <div className="text-sm text-gray-500">
        <Link href="/quality/cpv" className="hover:text-purple-600">持续工艺验证</Link>
        <span className="mx-2">/</span>
        <span className="text-gray-900">{product.name}</span>
      </div>

      {/* 区域1: 产品基础信息 */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">产品基础信息</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
          <div><span className="text-gray-500">产品名称</span><div className="font-medium text-gray-900 mt-1">{product.name}</div></div>
          <div><span className="text-gray-500">规格</span><div className="font-medium text-gray-900 mt-1">{product.specification || "-"}</div></div>
          <div><span className="text-gray-500">工艺版本</span><div className="font-medium text-gray-900 mt-1">{product.process_version || "-"}</div></div>
          <div><span className="text-gray-500">状态</span><div className="mt-1"><span className={`px-2 py-1 text-xs rounded-full font-semibold ${product.status === "active" ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-800"}`}>{product.status === "active" ? "启用" : "停用"}</span></div></div>
          <div><span className="text-gray-500">创建时间</span><div className="font-medium text-gray-900 mt-1">{new Date(product.created_at).toLocaleDateString("zh-CN")}</div></div>
        </div>
      </div>

      {/* 区域2: 统计指标卡 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="text-sm text-gray-500">批次数量</div>
          <div className="text-2xl font-bold mt-1 text-gray-900">{statistics?.total_batches ?? "-"}</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="text-sm text-gray-500">平均值</div>
          <div className="text-2xl font-bold mt-1 text-gray-900">{statistics?.avg_value != null ? statistics.avg_value.toFixed(2) : "-"}</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="text-sm text-gray-500">CPK值</div>
          <div className={`text-2xl font-bold mt-1 ${statistics && statistics.cpk_value < 1.33 ? "text-red-600" : "text-green-600"}`}>{statistics?.cpk_value != null ? statistics.cpk_value.toFixed(2) : "-"}</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="text-sm text-gray-500">异常批次数</div>
          <div className={`text-2xl font-bold mt-1 ${statistics && statistics.abnormal_count > 0 ? "text-red-600" : "text-gray-900"}`}>{statistics?.abnormal_count ?? "-"}</div>
        </div>
      </div>

      {/* 区域3: 趋势分析图 */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-gray-900">趋势分析</h2>
          <div className="flex gap-3 items-center">
            <select value={selectedType} onChange={(e) => setSelectedType(e.target.value as "CPP" | "CQA")} className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm">
              <option value="CPP">CPP</option>
              <option value="CQA">CQA</option>
            </select>
            <select value={selectedParamId} onChange={(e) => setSelectedParamId(e.target.value)} className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm">
              {allParams.map((p) => <option key={p.id} value={p.id}>{p.name} {p.unit ? `(${p.unit})` : ""}</option>)}
            </select>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm" />
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm" />
          </div>
        </div>
        <CpvTrendChart trend={trend} avgValue={statistics?.avg_value ?? null} />
      </div>

      {/* 区域4: 子模块入口 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Link href={`/quality/cpv/${productId}/cpp`} className="block bg-white rounded-xl border border-gray-200 p-6 hover:shadow-lg hover:border-blue-300 transition-all">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center text-blue-600 text-xl font-bold">P</div>
            <div>
              <h3 className="text-lg font-semibold text-gray-900">CPP 工艺参数</h3>
              <p className="text-sm text-gray-500 mt-1">关键工艺参数批次数据查看与分析</p>
            </div>
          </div>
        </Link>
        <Link href={`/quality/cpv/${productId}/cqa`} className="block bg-white rounded-xl border border-gray-200 p-6 hover:shadow-lg hover:border-green-300 transition-all">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center text-green-600 text-xl font-bold">Q</div>
            <div>
              <h3 className="text-lg font-semibold text-gray-900">CQA 质量属性</h3>
              <p className="text-sm text-gray-500 mt-1">关键质量属性批次数据查看与分析</p>
            </div>
          </div>
        </Link>
      </div>
    </div>
  )
}
