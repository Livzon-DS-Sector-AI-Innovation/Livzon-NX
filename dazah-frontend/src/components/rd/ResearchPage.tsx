'use client'

import { useCallback, useEffect } from 'react'
import { Button } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { ProjectTable } from './ProjectTable'
import { ProjectDrawer } from './ProjectDrawer'
import { useResearchStore } from '@/stores/rd'
import { fetchResearchProjects } from '@/lib/api/research'
import { ResearchProject } from '@/types/rd'

interface ResearchPageProps {
  initialProjects: ResearchProject[]
  initialTotal: number
}

export function ResearchPage({ initialProjects, initialTotal }: ResearchPageProps) {
  const {
    setProjects,
    setTotal,
    setLoading,
    loading,
    page,
    pageSize,
    stageFilter,
    statusFilter,
    keyword,
    openDrawer,
  } = useResearchStore()

  useEffect(() => {
    setProjects(initialProjects)
    setTotal(initialTotal)
  }, [initialProjects, initialTotal, setProjects, setTotal])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const result = await fetchResearchProjects({
        page,
        page_size: pageSize,
        stage: stageFilter || undefined,
        status: statusFilter || undefined,
        keyword: keyword || undefined,
      })
      setProjects(result.items)
      setTotal(result.total)
    } catch (error) {
      console.warn('加载研发项目数据失败:', error)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, stageFilter, statusFilter, keyword, setProjects, setTotal, setLoading])

  useEffect(() => {
    loadData()
  }, [loadData])

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>研发项目</h1>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openDrawer()}>
          新建项目
        </Button>
      </div>
      <ProjectTable loading={loading} onRefresh={loadData} />
      <ProjectDrawer onRefresh={loadData} />
    </div>
  )
}
