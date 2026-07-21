"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import Link from "next/link"
import * as XLSX from "xlsx"
import { fetchCqaBatchesWide, fetchCpvParameters, fetchCpvProduct } from "@/lib/api/quality-cpv"
import { CpvParameter, CpvBatchWide, CpvProduct } from "@/types/quality-cpv"
import { CpvImportDrawer } from "@/components/quality"

export default function CqaBatchDataPage() {
  const params = useParams()
  const productId = params.productId as string

  const [product, setProduct] = useState<CpvProduct | null>(null)
  const [parameters, setParameters] = useState<CpvParameter[]>([])
  const [batches, setBatches] = useState<CpvBatchWide[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [batchNo, setBatchNo] = useState("")
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => { loadData() }, [productId, page])

  async function loadData() {
    try {
      setLoading(true)
      const [prod, paramsData, batchesData] = await Promise.all([
        fetchCpvProduct(productId),
        fetchCpvParameters(productId, "CQA"),
        fetchCqaBatchesWide(productId, {
          batch_no: batchNo || undefined,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
          page,
          page_size: 20,
        }),
      ])
      setProduct(prod)
      setParameters(paramsData)
      setBatches(batchesData.items)
      setTotal(batchesData.total)
    } catch (err) { console.error(err) } finally { setLoading(false) }
  }

  function handleSearch() { setPage(1); loadData() }

  async function handleExport() {
    try {
      setExporting(true);
      const allItems: CpvBatchWide[] = [];
      let currentPage = 1;
      const pageSize = 200;
      let totalPages = 1;
      while (currentPage <= totalPages) {
        const result = await fetchCqaBatchesWide(productId, {
          batch_no: batchNo || undefined,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
          page: currentPage,
          page_size: pageSize,
        });
        allItems.push(...result.items);
        totalPages = Math.ceil(result.total / pageSize);
        currentPage++;
      }
      const headers = ["批号", "生产日期", ...parameters.map(p => p.name + (p.unit ? `(${p.unit})` : "")), "状态"];
      const rows = allItems.map(b => [
        b.batch_no,
        b.production_date,
        ...parameters.map(p => b.parameters[p.name]?.value ?? "-"),
        b.has_abnormal ? "异常" : "正常"
      ]);
      const ws = XLSX.utils.aoa_to_sheet([headers, ...rows]);
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, "CQA数据");
      const productName = product?.name || "未知产品";
      const dateStr = new Date().toISOString().slice(0, 10);
      XLSX.writeFile(wb, `cqa_batches_${productName}_${dateStr}.xlsx`);
    } catch (err) {
      console.error("导出失败:", err);
    } finally {
      setExporting(false);
    }
  }

  const totalPages = Math.ceil(total / 20)

  if (loading && !product) return <div className="p-6 text-center text-gray-500">加载中...</div>

  return (
    <div className="p-6 space-y-6">
      <div className="text-sm text-gray-500">
        <Link href="/quality/cpv" className="hover:text-purple-600">持续工艺验证</Link>
        <span className="mx-2">/</span>
        <Link href={`/quality/cpv/${productId}`} className="hover:text-purple-600">产品详情</Link>
        <span className="mx-2">/</span>
        <span className="text-gray-900">CQA 数据</span>
      </div>

      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">CQA 质量属性批次数据</h1>
        <div className="flex gap-2">
          <button onClick={() => setDrawerOpen(true)} className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium">
            上传 Excel
          </button>
          <button onClick={handleExport} disabled={exporting} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium">
            {exporting ? "导出中..." : "导出 Excel"}
          </button>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">批号</label>
            <input type="text" value={batchNo} onChange={(e) => setBatchNo(e.target.value)} placeholder="输入批号" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">开始日期</label>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">结束日期</label>
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
          </div>
          <div className="flex items-end gap-2">
            <button onClick={handleSearch} className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm">查询</button>
            <button onClick={() => { setBatchNo(""); setStartDate(""); setEndDate(""); setPage(1) }} className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 text-sm">重置</button>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-700 sticky left-0 bg-gray-50">批号</th>
                <th className="px-4 py-3 text-left font-medium text-gray-700">生产日期</th>
                {parameters.map((p) => (
                  <th key={p.id} className="px-4 py-3 text-left font-medium text-gray-700 whitespace-nowrap">
                    {p.name} {p.unit ? `(${p.unit})` : ""}
                  </th>
                ))}
                <th className="px-4 py-3 text-center font-medium text-gray-700">状态</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {batches.map((batch) => (
                <tr key={batch.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium sticky left-0 bg-white">{batch.batch_no}</td>
                  <td className="px-4 py-3 text-gray-500 whitespace-nowrap">{batch.production_date}</td>
                  {parameters.map((p) => {
                    const d = batch.parameters[p.name]
                    return (
                      <td key={p.id} className={`px-4 py-3 whitespace-nowrap ${d?.is_abnormal ? "text-red-600 font-semibold bg-red-50" : ""}`}>
                        {d?.value ?? "-"}
                      </td>
                    )
                  })}
                  <td className="px-4 py-3 text-center">
                    {batch.has_abnormal ? (
                      <span className="px-2 py-1 text-xs bg-red-100 text-red-700 rounded-full font-medium">异常</span>
                    ) : (
                      <span className="px-2 py-1 text-xs bg-green-100 text-green-700 rounded-full font-medium">正常</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {batches.length === 0 && <div className="text-center py-12 text-gray-500">暂无数据</div>}
      </div>

      {total > 20 && (
        <div className="flex justify-between items-center">
          <div className="text-sm text-gray-500">共 {total} 条记录，第 {page}/{totalPages} 页</div>
          <div className="flex gap-2">
            <button onClick={() => setPage(1)} disabled={page === 1} className="px-3 py-1 border border-gray-300 rounded text-sm disabled:opacity-50">首页</button>
            <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1} className="px-3 py-1 border border-gray-300 rounded text-sm disabled:opacity-50">上一页</button>
            <button onClick={() => setPage(Math.min(totalPages, page + 1))} disabled={page >= totalPages} className="px-3 py-1 border border-gray-300 rounded text-sm disabled:opacity-50">下一页</button>
            <button onClick={() => setPage(totalPages)} disabled={page >= totalPages} className="px-3 py-1 border border-gray-300 rounded text-sm disabled:opacity-50">末页</button>
          </div>
        </div>
      )}

      <CpvImportDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        productId={productId}
        productName={product?.name || ""}
        dataType="CQA"
        onSuccess={loadData}
      />
    </div>
  )
}
