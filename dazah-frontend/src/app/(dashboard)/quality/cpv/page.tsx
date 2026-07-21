"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { fetchCpvProducts } from "@/lib/api/quality-cpv"
import { CpvProductCreateDrawer } from "@/components/quality"
import { CpvProductWithStats } from "@/types/quality-cpv"

export default function CpvProductListPage() {
  const [products, setProducts] = useState<CpvProductWithStats[]>([])
  const [loading, setLoading] = useState(true)
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const result = await fetchCpvProducts({ page: 1, page_size: 50 })
        if (!cancelled) setProducts(result.items)
      } catch (err) {
        console.error(err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  async function loadProducts() {
    try {
      setLoading(true)
      const result = await fetchCpvProducts({ page: 1, page_size: 50 })
      setProducts(result.items)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">持续工艺验证</h1>
          <p className="text-sm text-gray-500 mt-1">原料药 CPV 产品管理与数据统计</p>
        </div>
        <button 
          onClick={() => setDrawerOpen(true)}
          className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-sm font-medium">
          新增产品
        </button>
      </div>

      {loading ? (
        <div className="text-center text-gray-500 py-12">加载中...</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">产品名称</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">规格</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">工艺版本</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">CPP指标数</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">CQA指标数</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">CPP累计批次</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">CQA累计批次</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">平均CPK</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">异常批次</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">状态</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">操作</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {products.map((product) => (
                <tr key={product.id} className="hover:bg-gray-50">
                  <td className="px-4 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{product.name}</td>
                  <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">{product.specification || "-"}</td>
                  <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">{product.process_version || "-"}</td>
                  <td className="px-4 py-4 whitespace-nowrap text-sm text-center text-gray-900">{product.cpp_parameter_count}</td>
                  <td className="px-4 py-4 whitespace-nowrap text-sm text-center text-gray-900">{product.cqa_parameter_count}</td>
                  <td className="px-4 py-4 whitespace-nowrap text-sm text-center text-gray-900">{product.cpp_batch_count}</td>
                  <td className="px-4 py-4 whitespace-nowrap text-sm text-center text-gray-900">{product.cqa_batch_count}</td>
                  <td className="px-4 py-4 whitespace-nowrap text-sm text-center font-medium text-gray-900">
                    {product.cpk_value !== null ? product.cpk_value.toFixed(2) : "-"}
                  </td>
                  <td className="px-4 py-4 whitespace-nowrap text-sm text-center">
                    <span className={product.abnormal_batch_count > 0 ? "font-medium text-red-600" : "text-gray-900"}>
                      {product.abnormal_batch_count}
                    </span>
                  </td>
                  <td className="px-4 py-4 whitespace-nowrap text-center">
                    <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${product.status === "active" ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-800"}`}>
                      {product.status === "active" ? "启用" : "停用"}
                    </span>
                  </td>
                  <td className="px-4 py-4 whitespace-nowrap text-center text-sm">
                    <Link href={`/quality/cpv/${product.id}`} className="text-purple-600 hover:text-purple-900 font-medium">
                      查看详情
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {products.length === 0 && (
            <div className="text-center py-12 text-gray-500">暂无产品数据</div>
          )}
        </div>
      )}

      <CpvProductCreateDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onSuccess={loadProducts}
      />
    </div>
  )
}
