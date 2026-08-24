'use client'

import { useEffect, useState, useCallback, useMemo } from 'react'
import { App, Tabs, Button, Upload, DatePicker, Select, Modal, AutoComplete } from 'antd'
import { DownloadOutlined, UploadOutlined, PrinterOutlined, DeleteOutlined, SyncOutlined, PlusOutlined, CloseOutlined } from '@ant-design/icons'
import dayjs, { Dayjs } from 'dayjs'
import { importEsgRecordsByDept, clearTrainingLedgersByDept, syncEsgFromLedger, addCustomTrainingDepartment, deleteCustomTrainingDepartment } from '@/actions/hr'
import { fetchTrainingDepartments, fetchCustomTrainingDepartments, fetchTrainingDeptMappings } from '@/lib/api/client/hr'
import AnnualTrainingStatsClient from './AnnualTrainingStatsClient'
import EsgTrainingReportClient from './EsgTrainingReportClient'
import TrainingLedgerImportModal from './TrainingLedgerImportModal'

const MONTH_OPTIONS = Array.from({ length: 12 }, (_, i) => ({
  value: String(i + 1),
  label: `${i + 1}月`,
}))

// 部门Tab持久化：刷新后停留在上次选择的部门（localStorage，与培训签到页面同模式）
const LAST_DEPT_KEY = 'hr_training_last_dept'

function getLastDept(): string {
  try {
    return localStorage.getItem(LAST_DEPT_KEY) || ''
  } catch {
    return ''
  }
}

export default function TrainingLedgerPageClient() {
  const { message, modal } = App.useApp()
  const [viewTab, setViewTab] = useState<'annual-stats' | 'esg-report'>('annual-stats')
  // 初始为空字符串（避免 SSR/客户端 hydration 不一致；刷新恢复在 loadDepartments 客户端执行）
  const [selectedDept, setSelectedDept] = useState<string>('')
  const [deptTabs, setDeptTabs] = useState<{ key: string; label: string }[]>([])
  // 筛选：年份（全年） + 月份（优先于年份）
  const [filterYear, setFilterYear] = useState<Dayjs | null>(null)
  const [filterMonth, setFilterMonth] = useState<string>('')
  // 打印触发器（递增触发子组件按导出内容打印）
  const [printRequest, setPrintRequest] = useState(0)
  // AI 导入 Modal 与导入后刷新
  const [importOpen, setImportOpen] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [syncing, setSyncing] = useState(false)
  // 自定义部门管理
  const [customDepts, setCustomDepts] = useState<Set<string>>(new Set())
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [addInputValue, setAddInputValue] = useState('')
  const [addLoading, setAddLoading] = useState(false)
  // 映射配置中的部门列表（用于添加部门时的候选选项）
  const [mappingDepts, setMappingDepts] = useState<string[]>([])

  const { dateFrom, dateTo, periodLabel } = useMemo(() => {
    if (filterYear && filterMonth) {
      const d = filterYear.month(Number(filterMonth) - 1)
      return {
        dateFrom: d.startOf('month').format('YYYY-MM-DD'),
        dateTo: d.endOf('month').format('YYYY-MM-DD'),
        periodLabel: `${filterYear.year()}年${filterMonth}月`,
      }
    }
    if (filterYear) {
      return {
        dateFrom: filterYear.startOf('year').format('YYYY-MM-DD'),
        dateTo: filterYear.endOf('year').format('YYYY-MM-DD'),
        periodLabel: `${filterYear.year()}年度`,
      }
    }
    return { dateFrom: '', dateTo: '', periodLabel: '' }
  }, [filterYear, filterMonth])

  const loadDepartments = useCallback(async () => {
    try {
      const [departments, customDeptList] = await Promise.all([
        fetchTrainingDepartments(),
        fetchCustomTrainingDepartments(),
      ])
      const tabs = departments.map((d) => ({ key: d, label: d }))
      setDeptTabs(tabs)
      setCustomDepts(new Set(customDeptList))
      if (tabs.length > 0) {
        // 优先恢复上次选择的部门（刷新后停留在原部门）；部门已不存在则回退第一个
        const last = getLastDept()
        const deptNames = new Set(tabs.map((t) => t.key))
        setSelectedDept((prev) => {
          const target = deptNames.has(last) ? last : deptNames.has(prev) ? prev : tabs[0].key
          try {
            localStorage.setItem(LAST_DEPT_KEY, target)
          } catch { /* ignore */ }
          return target
        })
      }
    } catch {
      message.error('加载部门列表失败')
    }
  }, [message])

  const handleDeleteDept = useCallback(
    (deptName: string, e: React.MouseEvent) => {
      e.stopPropagation()
      modal.confirm({
        title: '删除自定义部门',
        content: `确认删除部门「${deptName}」？删除后该部门将不再显示在部门列表中。`,
        okText: '确认删除',
        okButtonProps: { danger: true },
        cancelText: '取消',
        onOk: async () => {
          try {
            await deleteCustomTrainingDepartment(deptName)
            message.success('删除成功')
            await loadDepartments()
          } catch (err) {
            message.error((err instanceof Error ? err.message : '') || '删除失败')
          }
        },
      })
    },
    [message, modal, loadDepartments]
  )

  const handleOpenAddModal = useCallback(async () => {
    setAddInputValue('')
    setAddModalOpen(true)
    // 加载映射配置中的部门列表（排除已存在的部门）
    try {
      const mappings = await fetchTrainingDeptMappings()
      const allDepts = new Set<string>()
      mappings.forEach((m) => {
        // 优先使用 target_name（映射后的名称），否则使用 source_name
        const deptName = m.target_name || m.source_name
        if (deptName) allDepts.add(deptName)
      })
      // 排除已在台账中的部门
      const existingDepts = new Set([
        ...customDepts,
        ...deptTabs.map((t) => t.label),
      ])
      setMappingDepts(Array.from(allDepts).filter((d) => !existingDepts.has(d)))
    } catch {
      setMappingDepts([])
    }
  }, [customDepts, deptTabs])

  const handleAddDept = useCallback(async () => {
    const name = addInputValue.trim()
    if (!name) {
      message.warning('请输入部门名称')
      return
    }
    // 前端预校验：检查是否与现有部门重复
    const allNames = new Set([
      ...customDepts,
      ...deptTabs.map((t) => t.label),
    ])
    if (allNames.has(name)) {
      message.error('该部门已存在')
      return
    }
    setAddLoading(true)
    try {
      await addCustomTrainingDepartment(name)
      message.success('添加成功')
      setAddModalOpen(false)
      setAddInputValue('')
      await loadDepartments()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '添加失败')
    } finally {
      setAddLoading(false)
    }
  }, [addInputValue, customDepts, deptTabs, message, loadDepartments])

  useEffect(() => {
    queueMicrotask(loadDepartments)
  }, [loadDepartments])

  const handleExport = useCallback(async () => {
    if (!selectedDept) {
      message.warning('请先选择部门')
      return
    }
    try {
      const sp = new URLSearchParams({ department: selectedDept })
      if (dateFrom) sp.set('date_from', dateFrom)
      if (dateTo) sp.set('date_to', dateTo)
      const url =
        viewTab === 'annual-stats'
          ? `/api/v1/hr/training-ledgers/export-by-dept?${sp.toString()}`
          : `/api/v1/hr/esg-training-records/export?${sp.toString()}`
      const res = await fetch(url, { cache: 'no-store' })
      if (!res.ok) throw new Error('导出失败')
      const blob = await res.blob()
      const downloadUrl = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = downloadUrl
      // 命名：年度培训统计表=年份+部门；ESG培训报表=导出月份-导出部门-ESG培训报表
      const filename =
        viewTab === 'annual-stats'
          ? `年度培训统计表_${selectedDept}${periodLabel ? `_${periodLabel}` : ''}.xlsx`
          : `${dayjs().format('YYYY年M月')}-${selectedDept}-ESG培训报表.xlsx`
      a.download = filename
      a.click()
      window.URL.revokeObjectURL(downloadUrl)
      message.success('导出成功')
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '导出失败')
    }
  }, [selectedDept, viewTab, dateFrom, dateTo, periodLabel, message])

  // ESG 报表直接导入；年度培训统计表走 AI 识别 Modal
  const handleEsgImport = useCallback(
    async (file: File) => {
      if (!selectedDept) {
        message.warning('请先选择部门')
        return false
      }
      try {
        const res = await importEsgRecordsByDept(file, selectedDept)
        message.success(res.message || '导入成功')
        setRefreshKey((k) => k + 1)
      } catch (e) {
        message.error((e instanceof Error ? e.message : '') || '导入失败')
      }
      return false
    },
    [selectedDept, message]
  )

  const handleSyncFromLedger = useCallback(() => {
    if (!selectedDept) {
      message.warning('请先选择部门')
      return
    }
    modal.confirm({
      title: '从台账同步 ESG 记录',
      content: `将按归属「${selectedDept}」部门的培训台账（与上方台账列表同口径）同步生成 ESG 培训报表记录；参训人员按姓名匹配员工档案，未匹配的跳过，已存在的记录自动跳过。确认继续？`,
      onOk: async () => {
        setSyncing(true)
        try {
          const res = await syncEsgFromLedger(selectedDept)
          message.success(res.message || '同步完成')
          setRefreshKey((k) => k + 1)
        } catch (e) {
          message.error((e instanceof Error ? e.message : '') || '同步失败')
        } finally {
          setSyncing(false)
        }
      },
    })
  }, [message, modal, selectedDept])

  const handlePrint = () => {
    if (!selectedDept) {
      message.warning('请先选择部门')
      return
    }
    setPrintRequest((n) => n + 1)
  }

  // 全部清除：二次确认后清空当前部门台账
  const handleClearAll = () => {
    if (!selectedDept) {
      message.warning('请先选择部门')
      return
    }
    modal.confirm({
      title: '全部清除',
      content: `即将清空部门「${selectedDept}」的全部培训台账记录。如有需要请先导出备份，清除后不可恢复。`,
      okText: '确认清除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          const res = await clearTrainingLedgersByDept(selectedDept)
          message.success(res.message || '清除成功')
          setRefreshKey((k) => k + 1)
        } catch (e) {
          message.error((e instanceof Error ? e.message : '') || '清除失败')
        }
      },
    })
  }

  // 选择部门并持久化（刷新后停留在原部门）
  const selectDept = useCallback((dept: string) => {
    setSelectedDept(dept)
    try {
      localStorage.setItem(LAST_DEPT_KEY, dept)
    } catch { /* ignore */ }
  }, [])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 no-print items-center">
        {deptTabs.map(tab => (
          <button
            key={tab.key}
            onClick={() => selectDept(tab.key)}
            className={`px-4 py-2 rounded-lg border text-sm transition-all flex items-center gap-1 ${
              selectedDept === tab.key
                ? 'border-blue-500 bg-blue-50 text-blue-600'
                : 'border-gray-200 bg-white text-gray-600 hover:border-blue-300'
            }`}
          >
            {tab.label}
            {customDepts.has(tab.key) && (
              <span
                onClick={(e) => handleDeleteDept(tab.key, e)}
                className="ml-1 opacity-50 hover:opacity-100 hover:text-red-500 cursor-pointer"
              >
                <CloseOutlined style={{ fontSize: 10 }} />
              </span>
            )}
          </button>
        ))}
        <button
          onClick={handleOpenAddModal}
          className="px-3 py-2 rounded-lg border border-dashed border-gray-300 text-sm text-gray-500 hover:border-blue-400 hover:text-blue-500 transition-all flex items-center gap-1"
        >
          <PlusOutlined /> 添加部门
        </button>
      </div>

      <Tabs
        activeKey={viewTab}
        onChange={(k) => setViewTab(k as any)}
        items={[
          { key: 'annual-stats', label: '年度培训统计表' },
          { key: 'esg-report', label: 'ESG培训报表' },
        ]}
        tabBarExtraContent={
          <div className="no-print flex flex-wrap items-center gap-2">
            <DatePicker
              picker="year"
              placeholder="全年"
              value={filterYear}
              onChange={(v) => setFilterYear(v)}
              allowClear
              style={{ width: 100 }}
            />
            <Select
              placeholder="全部月份"
              value={filterMonth || undefined}
              onChange={(v) => setFilterMonth(v || '')}
              allowClear
              options={MONTH_OPTIONS}
              style={{ width: 100 }}
              disabled={!filterYear}
            />
            <Button icon={<PrinterOutlined />} onClick={handlePrint}>打印</Button>
            {viewTab === 'annual-stats' ? (
              <>
                <Button
                  icon={<UploadOutlined />}
                  onClick={() => {
                    if (!selectedDept) {
                      message.warning('请先选择部门')
                      return
                    }
                    setImportOpen(true)
                  }}
                >
                  导入
                </Button>
                <Button danger icon={<DeleteOutlined />} onClick={handleClearAll}>
                  全部清除
                </Button>
              </>
            ) : (
              <>
                <Button icon={<SyncOutlined />} loading={syncing} onClick={handleSyncFromLedger}>
                  从台账同步
                </Button>
                <Upload beforeUpload={handleEsgImport} showUploadList={false} accept=".xlsx,.xls">
                  <Button icon={<UploadOutlined />}>导入</Button>
                </Upload>
              </>
            )}
            <Button icon={<DownloadOutlined />} onClick={handleExport}>导出</Button>
          </div>
        }
      />

      {selectedDept && (
        viewTab === 'annual-stats' ? (
          <AnnualTrainingStatsClient
            key={`annual-${refreshKey}`}
            department={selectedDept}
            dateFrom={dateFrom}
            dateTo={dateTo}
            periodLabel={periodLabel}
            printRequest={printRequest}
          />
        ) : (
          <EsgTrainingReportClient
            key={`esg-${refreshKey}`}
            department={selectedDept}
            dateFrom={dateFrom}
            dateTo={dateTo}
            periodLabel={periodLabel}
            printRequest={printRequest}
          />
        )
      )}

      <TrainingLedgerImportModal
        open={importOpen}
        department={selectedDept}
        onClose={() => setImportOpen(false)}
        onSuccess={() => {
          setRefreshKey((k) => k + 1)
          loadDepartments()
        }}
      />

      <Modal
        title="添加自定义部门"
        open={addModalOpen}
        onOk={handleAddDept}
        onCancel={() => setAddModalOpen(false)}
        confirmLoading={addLoading}
        okText="确认添加"
        cancelText="取消"
      >
        <div className="py-2">
          <AutoComplete
            value={addInputValue}
            onChange={setAddInputValue}
            options={mappingDepts.map((d) => ({ value: d }))}
            placeholder="请输入或选择部门名称（来自 HR 设置-培训部门映射配置）"
            style={{ width: '100%' }}
            allowClear
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleAddDept()
            }}
          />
          <div className="text-xs text-gray-400 mt-2">
            添加后，该部门将出现在所有培训页面的部门列表中。
          </div>
        </div>
      </Modal>
    </div>
  )
}
