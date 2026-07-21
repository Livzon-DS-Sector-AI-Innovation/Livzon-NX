'use client'

import { useState, useEffect } from 'react'
import { Steps, Card, Button, Space, Tag, App } from 'antd'
import { SaveOutlined } from '@ant-design/icons'
import { ModuleResearch } from './ModuleResearch'
import { ModuleTrial } from './ModuleTrial'
import { ModuleAssessment } from './ModuleAssessment'
import { ModuleConfirmation } from './ModuleConfirmation'
import type { WorkflowModule, CandidateRoute, ExperimentRecord, DimensionAssessment, ExperimentPlan, RouteStatus } from '@/types/rd'
import { fetchRouteById, updateRoute } from '@/lib/api/rd'

interface RouteWorkflowPageProps {
  routeId: string
  routeName: string
  literatureSource?: string
  literatureFile?: File | null
  onComplete: () => void
  onBack: () => void
}

interface WorkflowState {
  currentStep: number
  selectedRouteIds: string[]
  selectedRoutes: CandidateRoute[]
  experimentPlans: ExperimentPlan[]
  allExperiments: ExperimentRecord[]
  assessment: DimensionAssessment | null
  literatureSource: string
  updatedAt: string
}

const stepConfig: { key: WorkflowModule; title: string; description: string }[] = [
  { key: 'research', title: '文献解析+实验方案', description: 'LLM解析文献，生成方案' },
  { key: 'trial', title: '实验数据录入', description: '录入实验结果' },
  { key: 'assessment', title: '四维度评估', description: '动态权重评估' },
  { key: 'confirmation', title: '路线确认+报告生成', description: '自动生成报告' },
]

export function RouteWorkflowPage({ routeId, routeName, literatureSource = '', literatureFile, onComplete, onBack }: RouteWorkflowPageProps) {
  const { message } = App.useApp()
  
  // 从后端或 localStorage 恢复状态
  const savedState = typeof window !== 'undefined' 
    ? localStorage.getItem(`workflow-${routeId}`)
    : null
  
  const initialState: WorkflowState = savedState ? JSON.parse(savedState) : {
    currentStep: 0,
    selectedRouteIds: [],
    selectedRoutes: [],
    experimentPlans: [],
    allExperiments: [],
    assessment: null,
    literatureSource,
    updatedAt: new Date().toISOString(),
  }

  const [currentStep, setCurrentStep] = useState(initialState.currentStep)
  const [selectedRouteIds, setSelectedRouteIds] = useState<string[]>(initialState.selectedRouteIds)
  const [selectedRoutes, setSelectedRoutes] = useState<CandidateRoute[]>(initialState.selectedRoutes)
  const [experimentPlans, setExperimentPlans] = useState<ExperimentPlan[]>(initialState.experimentPlans)
  const [currentTrialRoute, setCurrentTrialRoute] = useState<CandidateRoute | null>(
    initialState.selectedRoutes.length > 0 ? initialState.selectedRoutes[0] : null
  )
  const [trialRouteIndex, setTrialRouteIndex] = useState(0)
  const [allExperiments, setAllExperiments] = useState<ExperimentRecord[]>(initialState.allExperiments)
  const [assessment, setAssessment] = useState<DimensionAssessment | null>(initialState.assessment)

  // 保存状态到后端 + localStorage 备份
  const saveState = async () => {
    const updateData = {
      current_module: stepConfig[currentStep]?.key || 'research',
      status: (currentStep >= 3 ? 'completed' : 'in_progress') as RouteStatus,
      selected_route_ids: selectedRouteIds,
      candidate_routes: selectedRoutes,
      experiment_plans: experimentPlans,
      assessment: assessment ?? undefined,
    }
    
    // 保存到后端
    try {
      await updateRoute(routeId, updateData)
    } catch (e) {
      console.error('后端保存失败，使用本地备份', e)
    }
    
    // localStorage 作为离线备份
    const state: WorkflowState = {
      currentStep,
      selectedRouteIds,
      selectedRoutes,
      experimentPlans,
      allExperiments,
      assessment,
      literatureSource,
      updatedAt: new Date().toISOString(),
    }
    localStorage.setItem(`workflow-${routeId}`, JSON.stringify(state))
  }

  // 自动保存（防抖）
  useEffect(() => {
    const timer = setTimeout(() => {
      saveState()
    }, 2000) // 2秒防抖
    return () => clearTimeout(timer)
  }, [currentStep, selectedRouteIds, selectedRoutes, experimentPlans, allExperiments, assessment])

  // 从后端加载最新数据
  useEffect(() => {
    const loadFromBackend = async () => {
      try {
        const route = await fetchRouteById(routeId)
        if (route) {
          // Sync selected routes
          if (route.candidate_routes && route.candidate_routes.length > 0) {
            setSelectedRoutes(route.candidate_routes)
            if (route.selected_route_ids) {
              setSelectedRouteIds(route.selected_route_ids)
            }
          }
          if (route.experiment_plans && route.experiment_plans.length > 0) {
            setExperimentPlans(route.experiment_plans)
          }
          if (route.assessment) {
            setAssessment(route.assessment)
          }
          // Set current step based on current_module
          if (route.current_module) {
            const stepIndex = stepConfig.findIndex(s => s.key === route.current_module)
            if (stepIndex >= 0) {
              setCurrentStep(stepIndex)
            }
          }
        }
      } catch (e) {
        console.error('从后端加载失败', e)
      }
    }
    loadFromBackend()
  }, [routeId])

  // 保存并退出
  const handleSaveAndExit = () => {
    saveState()
    message.success('✓ 已保存！您可以随时回来继续')
    onBack()
  }

  // Module 1 完成
  const handleResearchComplete = (data: {
    literatureSource: string
    candidateRoutes: CandidateRoute[]
    selectedRouteIds: string[]
    experimentPlans: ExperimentPlan[]
  }) => {
    const selected = data.candidateRoutes.filter(r => data.selectedRouteIds.includes(r.id))
    setSelectedRoutes(selected)
    setSelectedRouteIds(data.selectedRouteIds)
    setExperimentPlans(data.experimentPlans)
    
    if (selected.length > 0) {
      setCurrentTrialRoute(selected[0])
      setTrialRouteIndex(0)
    }
    setCurrentStep(1)
    message.success('方案已确认！实验完成后，请回来录入实验数据')
  }

  // Module 1 保存并退出
  const handleResearchSaveAndExit = (data: {
    candidateRoutes: CandidateRoute[]
    selectedRouteIds: string[]
    experimentPlans: ExperimentPlan[]
  }) => {
    const selected = data.candidateRoutes.filter(r => data.selectedRouteIds.includes(r.id))
    setSelectedRoutes(selected)
    setSelectedRouteIds(data.selectedRouteIds)
    setExperimentPlans(data.experimentPlans)
    
    setTimeout(() => {
      onBack()
    }, 500)
  }

  // Module 2 完成
  const handleTrialComplete = (exps: ExperimentRecord[]) => {
    const newExperiments = [...allExperiments, ...exps]
    setAllExperiments(newExperiments)

    const nextIndex = trialRouteIndex + 1
    if (nextIndex < selectedRoutes.length) {
      setCurrentTrialRoute(selectedRoutes[nextIndex])
      setTrialRouteIndex(nextIndex)
      return
    }

    setCurrentStep(2)
  }

  // Module 3 完成
  const handleAssessmentComplete = (assess: DimensionAssessment) => {
    setAssessment(assess)
    setCurrentStep(3)
  }

  // Module 4 完成
  const handleConfirmationComplete = () => {
    // 清除保存的状态
    localStorage.removeItem(`workflow-${routeId}`)
    onComplete()
  }

  const currentRouteName = currentTrialRoute
    ? `${currentTrialRoute.name}（${trialRouteIndex + 1}/${selectedRoutes.length}）`
    : routeName

  const bestRoute = selectedRoutes.length > 0 ? selectedRoutes[0] : null

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Steps
          current={currentStep}
          items={stepConfig.map((s) => ({
            title: s.title,
            content: s.description,
          }))}
          style={{ maxWidth: 800, margin: '0 auto' }}
        />
      </Card>

      {currentStep === 0 && (
        <ModuleResearch 
          routeId={routeId} 
          literatureSource={literatureSource}
          literatureFile={literatureFile}
          initialData={currentStep === 0 && selectedRoutes.length > 0 ? {
            candidateRoutes: selectedRoutes,
            selectedRouteIds,
            experimentPlans,
          } : undefined}
          onComplete={handleResearchComplete} 
          onSaveAndExit={handleResearchSaveAndExit}
        />
      )}
      {currentStep === 1 && currentTrialRoute && (
        <ModuleTrial
          key={currentTrialRoute.id}
          routeId={routeId}
          selectedRouteName={currentRouteName}
          experimentPlan={experimentPlans.find(p => p.route_id === currentTrialRoute.id)}
          onComplete={handleTrialComplete}
        />
      )}
      {currentStep === 2 && (
        <ModuleAssessment
          routeId={routeId}
          selectedRouteName={`已尝试${selectedRoutes.length}条路线`}
          experiments={allExperiments}
          onComplete={handleAssessmentComplete}
        />
      )}
      {currentStep === 3 && assessment && (
        <ModuleConfirmation
          routeId={routeId}
          selectedRouteName={bestRoute?.name || routeName}
          assessmentScore={assessment.weighted_total}
          assessment={assessment}
          experiments={allExperiments}
          selectedRoutes={selectedRoutes}
          literatureSource={literatureSource}
          onComplete={handleConfirmationComplete}
        />
      )}

      <Card style={{ marginTop: 16 }}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space>
            <Button onClick={onBack}>← 返回列表</Button>
            {currentStep > 0 && currentStep < 3 && (
              <Button onClick={() => setCurrentStep(currentStep - 1)}>← 上一步</Button>
            )}
          </Space>
          <Space>
            <Tag color="blue">当前：{stepConfig[currentStep]?.title}</Tag>
            {currentStep === 1 && (
              <Tag>路线进度：{trialRouteIndex + 1}/{selectedRoutes.length}</Tag>
            )}
            {currentStep >= 2 && (
              <Tag color="green">实验记录：{allExperiments.length}条</Tag>
            )}
            <Button 
              icon={<SaveOutlined />} 
              onClick={handleSaveAndExit}
              type="dashed"
            >
              💾 保存并退出
            </Button>
          </Space>
        </Space>
      </Card>
    </div>
  )
}
