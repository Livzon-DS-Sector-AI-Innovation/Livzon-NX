'use client'

import { useState } from 'react'
import { App, Button, Radio, Input, Select, Modal } from 'antd'
import EmailFetchPanel from './recruitment/EmailFetchPanel'
import {
  SearchOutlined,
  PlusOutlined,
  ThunderboltOutlined,
  ImportOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchCandidates, type JobPostingVM } from '@/lib/api/client/hr'
import {
  createJobPosting,
  deleteCandidateAction,
  fetchCandidatesFromFeishu,
  batchAnalyzeCandidatesAction,
  createOnboardingFromInterviewAction,
  updateCandidateAction } from '@/actions/hr'
import CandidateListView from './CandidateListView'
import CandidateCardView from './CandidateCardView'
import { Candidate } from '@/types/hr'
import { usePermission } from '@/hooks/usePermission'

interface RecruitmentClientProps {
  initialJobs: JobPostingVM[]
}

interface CandidateQueryData {
  data?: Candidate[]
  meta?: { total?: number; page?: number; page_size?: number }
}

export default function RecruitmentClient({ initialJobs }: RecruitmentClientProps) {
  // 编辑权限：仅人力资源部（hr:write）可发布/同步/AI筛选，其他部门只读
  const { has } = usePermission()
  const canEditHr = has('hr:write')
  const { message } = App.useApp()
  const [viewMode, setViewMode] = useState<'list' | 'card'>('list')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [syncing, setSyncing] = useState(false)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [fitFilter, setFitFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [jobModalOpen, setJobModalOpen] = useState(false)
  const [jobFormTitle, setJobFormTitle] = useState('')
  const [jobFormDesc, setJobFormDesc] = useState('')
  const [jobFormReq, setJobFormReq] = useState('')
  const [jobFormSalary, setJobFormSalary] = useState('')
  const [jobFormLocation, setJobFormLocation] = useState('')
  const [jobFormSkills, setJobFormSkills] = useState('')
  const [jobCreating, setJobCreating] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)

  // ─── React Query ───
  const queryClient = useQueryClient()
  const { data: candidatesData, isLoading: loading, refetch } = useQuery({
    queryKey: ['candidates', searchKeyword, fitFilter, statusFilter, selectedJobId, page, pageSize],
    queryFn: () => fetchCandidates({
      keyword: searchKeyword || undefined,
      fit_level: fitFilter || undefined,
      interview_status: statusFilter || undefined,
      job_id: selectedJobId || undefined,
      page,
      page_size: pageSize }),
    staleTime: 30000,
  })

  // 面试状态更新 mutation（乐观更新）
  const updateStatusMutation = useMutation({
    mutationFn: ({ candidateId, newStatus }: { candidateId: string; newStatus: string }) =>
      updateCandidateAction(candidateId, { interview_status: newStatus }),
    onMutate: async ({ candidateId, newStatus }) => {
      // 取消正在进行的查询
      await queryClient.cancelQueries({ queryKey: ['candidates'] })
      // 保存之前的状态
      const previousData = queryClient.getQueryData<CandidateQueryData>(['candidates', searchKeyword, fitFilter, statusFilter, selectedJobId, page, pageSize])
      // 乐观更新
      queryClient.setQueryData<CandidateQueryData>(['candidates', searchKeyword, fitFilter, statusFilter, selectedJobId, page, pageSize], (old) => {
        if (!old?.data) return old
        return {
          ...old,
          data: old.data.map((c: Candidate) =>
            c.id === candidateId ? { ...c, interview_status: newStatus } : c
          ),
        }
      })
      return { previousData }
    },
    onError: (_err, _variables, context) => {
      // 失败回滚
      if (context?.previousData) {
        queryClient.setQueryData(['candidates', searchKeyword, fitFilter, statusFilter, selectedJobId, page, pageSize], context.previousData)
      }
    },
    onSettled: () => {
      // 最终同步（后台刷新，不阻塞 UI）
      queryClient.invalidateQueries({ queryKey: ['candidates'] })
    },
  })

  const candidates = candidatesData?.data || []
  const total = candidatesData?.meta?.total || 0

  const handlePageChange = (newPage: number, newPageSize: number) => {
    setPage(newPage)
    setPageSize(newPageSize)
  }

  const handleSync = async () => {
    setSyncing(true)
    try {
      const res = await fetchCandidatesFromFeishu()
      message.success(res.message)
      refetch()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '同步失败')
    } finally { setSyncing(false) }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteCandidateAction(id)
      message.success('删除成功')
      refetch()
    } catch (err) { message.error((err instanceof Error ? err.message : '') || '删除失败') }
  }

  const handleStatusChange = (candidateId: string, newStatus: string) => {
    updateStatusMutation.mutate(
      { candidateId, newStatus },
      {
        onSuccess: () => {
          message.success('面试状态已更新')
        },
        onError: (err: unknown) => {
          message.error((err instanceof Error ? err.message : '') || '更新失败')
        },
      }
    )
  }

  const [transferring, setTransferring] = useState(false)
  const handleTransfer = async (candidateId: string) => {
    if (transferring) return
    setTransferring(true)
    try {
      const res = await createOnboardingFromInterviewAction(candidateId)
      message.success(res.message || '转入职成功')
      refetch()
    } catch (err) { message.error((err instanceof Error ? err.message : '') || '转入职失败') }
    finally { setTransferring(false) }
  }

  const handleBatchAnalyze = async () => {
    if (!candidatesData?.data?.length) {
      message.warning('没有可分析的候选人')
      return
    }
    setAnalyzing(true)
    try {
      const ids = candidatesData.data.map((c) => c.id)
      const res = await batchAnalyzeCandidatesAction(ids)
      message.success(res.message || '批量分析完成')
      refetch()
    } catch (err) { message.error((err instanceof Error ? err.message : '') || '批量分析失败') }
    finally { setAnalyzing(false) }
  }

  const handleCreateJob = async () => {
    if (!jobFormTitle.trim()) { message.error('请输入职位名称'); return }
    setJobCreating(true)
    try {
      await createJobPosting({
        title: jobFormTitle,
        description: jobFormDesc || undefined,
        requirement: jobFormReq || undefined,
        salary_range: jobFormSalary || undefined,
        location: jobFormLocation || undefined,
        req_skills: jobFormSkills ? jobFormSkills.split(/[,，]/).map((s: string) => s.trim()).filter(Boolean) : undefined,
      })
      message.success('职位发布成功')
      setJobModalOpen(false)
      setJobFormTitle(''); setJobFormDesc(''); setJobFormReq('')
      setJobFormSalary(''); setJobFormLocation(''); setJobFormSkills('')
    } catch (err) { message.error((err instanceof Error ? err.message : '') || '发布职位失败') }
    finally { setJobCreating(false) }
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        {canEditHr ? (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setJobModalOpen(true)}>发布招聘信息</Button>
        ) : null}
        {canEditHr ? (
          <Button icon={<ImportOutlined />} onClick={handleSync} loading={syncing}>从飞书同步</Button>
        ) : null}
        {canEditHr ? (
          <Button icon={<ThunderboltOutlined />} onClick={handleBatchAnalyze} loading={analyzing}>AI 筛选</Button>
        ) : null}
        <div className="flex-1" />
        <Select
          placeholder="符合程度·全部"
          allowClear
          value={fitFilter || undefined}
          onChange={(v) => { setFitFilter(v || ''); setPage(1) }}
          style={{ width: 160 }}
          options={[{ value: '高', label: '高' }, { value: '中', label: '中' }, { value: '低', label: '低' }]}
        />
        <Select
          placeholder="面试状态·全部"
          allowClear
          value={statusFilter || undefined}
          onChange={(v) => { setStatusFilter(v || ''); setPage(1) }}
          style={{ width: 160 }}
          options={[
            { value: '待安排', label: '待安排' }, { value: '已安排', label: '已安排' },
            { value: '已完成', label: '已完成' }, { value: '通过', label: '通过' }, { value: '未通过', label: '未通过' },
          ]}
        />
        <Input
          placeholder="搜索姓名/职位"
          value={searchKeyword}
          onChange={(e) => { setSearchKeyword(e.target.value); setPage(1) }}
          prefix={<SearchOutlined />}
          style={{ width: 200 }}
          allowClear
        />
      </div>

      {/* Grid: left job list + right candidate table */}
      <div className="grid gap-4" style={{ gridTemplateColumns: '260px 1fr' }}>
        {/* Left: Job List */}
        <div className="bg-white rounded-xl border border-[#e5e3df] shadow-sm">
          <div className="px-4 py-3 border-b border-[#e5e3df] flex items-center justify-between">
            <span className="font-semibold text-sm">招聘职位</span>
            <span className="text-xs text-gray-400">{initialJobs.length} 个职位</span>
          </div>
          <div className="p-2 flex flex-col gap-1 max-h-[70vh] overflow-auto">
            {initialJobs.map((job) => {
              const cnt = job.candidate_count ?? 0
              const sel = selectedJobId === job.id
              return (
                <div
                  key={job.id}
                  onClick={() => setSelectedJobId(sel ? null : job.id)}
                  className={`p-2.5 rounded-lg cursor-pointer border transition-colors ${
                    sel ? 'border-[#2f6bff] bg-[#eaf1ff]' : 'border-[#e5e3df] bg-white hover:border-[#c9d3e0]'
                  }`}
                >
                  <div className="font-semibold text-sm">{job.title}</div>
                  <div className="text-xs text-gray-400 mt-0.5">{job.location || '-'} · {job.salary_range || '-'} · {cnt} 人应聘</div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Right: Candidate Table */}
        <div className="bg-white rounded-xl border border-[#e5e3df] shadow-sm">
          <div className="px-4 py-3 border-b border-[#e5e3df] flex items-center justify-between">
            <span className="font-semibold text-sm">候选人信息</span>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400">共 {total} 人</span>
              <Radio.Group value={viewMode} onChange={(e) => setViewMode(e.target.value)} optionType="button" buttonStyle="solid" size="small">
                <Radio.Button value="list">列表</Radio.Button>
                <Radio.Button value="card">卡片</Radio.Button>
              </Radio.Group>
            </div>
          </div>
          <div className="p-0" style={{ maxHeight: '64vh', overflow: 'auto' }}>
            {viewMode === 'list' ? (
              <CandidateListView
                candidates={candidates}
                total={total}
                page={page}
                pageSize={pageSize}
                loading={loading}
                onPageChange={handlePageChange}
                onDelete={handleDelete}
                onTransfer={handleTransfer}
                transferring={transferring}
                onRefresh={refetch}
                onStatusChange={handleStatusChange}
              />
            ) : (
              <div className="p-3">
                <CandidateCardView
                  candidates={candidates}
                  total={total}
                  page={page}
                  pageSize={pageSize}
                  loading={loading}
                  onPageChange={handlePageChange}
                  onDelete={handleDelete}
                />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom: Email Fetch Status */}
      <EmailFetchPanel />

      {/* Modals */}
      <Modal title="发布招聘信息" open={jobModalOpen} onCancel={() => setJobModalOpen(false)} onOk={handleCreateJob} confirmLoading={jobCreating} okText="发布" cancelText="取消">
        <div className="space-y-4 py-2">
          <div><label className="block text-sm mb-1 font-medium">职位名称 <span className="text-red-500">*</span></label><Input placeholder="如：高级前端工程师" value={jobFormTitle} onChange={(e) => setJobFormTitle(e.target.value)} /></div>
          <div><label className="block text-sm mb-1 font-medium">岗位描述</label><Input.TextArea placeholder="岗位职责…" value={jobFormDesc} onChange={(e) => setJobFormDesc(e.target.value)} rows={3} /></div>
          <div><label className="block text-sm mb-1 font-medium">任职要求</label><Input.TextArea placeholder="硬性条件与加分项…" value={jobFormReq} onChange={(e) => setJobFormReq(e.target.value)} rows={3} /></div>
          <div className="grid grid-cols-2 gap-4">
            <div><label className="block text-sm mb-1 font-medium">薪资范围</label><Input placeholder="20-35K·14薪" value={jobFormSalary} onChange={(e) => setJobFormSalary(e.target.value)} /></div>
            <div><label className="block text-sm mb-1 font-medium">工作地点</label><Input placeholder="深圳·南山" value={jobFormLocation} onChange={(e) => setJobFormLocation(e.target.value)} /></div>
          </div>
          <div><label className="block text-sm mb-1 font-medium">要求技能（逗号分隔，用于AI匹配）</label><Input placeholder="React, TypeScript, Node.js" value={jobFormSkills} onChange={(e) => setJobFormSkills(e.target.value)} /></div>
        </div>
      </Modal>
    </div>
  )
}
