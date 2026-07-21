'use client'

import { useState, useEffect, useMemo } from 'react'
import { Steps, Card, Button, Space, Tag, App, Tabs, Alert } from 'antd'
import { SaveOutlined, CheckCircleFilled, ClockCircleFilled } from '@ant-design/icons'
import { ModuleDOE } from './ModuleDOE'
import { ModuleImpurity } from './ModuleImpurity'
import { ModuleCrystalForm } from './ModuleCrystalForm'
import { ModuleQualityStandard } from './ModuleQualityStandard'
import { ModuleScaleUp } from './ModuleScaleUp'
import { ModuleLabConfirmation } from './ModuleLabConfirmation'
import { ModuleReport } from './ModuleReport'
import { updateOptimization } from '@/lib/api/rd'
import type {
  OptimizationModule,
  DOEExperiment,
  ImpurityStudy,
  CrystalFormStudy,
  QualityStandardSet,
  LabConfirmationStudy,
  ScaleUpStudy,
} from '@/types/rd'

interface ProcessOptimizationWorkflowPageProps {
  optimizationId: string
  optimizationName: string
  sourceRouteId?: string | null
  sourceRouteName?: string | null
  onComplete: () => void
  onBack: () => void
}

interface WorkflowState {
  currentStep: number
  activeParallelTab: string
  doeExperiment?: DOEExperiment
  impurityStudy?: ImpurityStudy
  crystalFormStudy?: CrystalFormStudy
  qualityStandardSet?: QualityStandardSet
  labConfirmationStudy?: LabConfirmationStudy
  scaleUpStudy?: ScaleUpStudy
  optimizationName: string
  sourceRouteId?: string | null
  sourceRouteName?: string | null
  updatedAt: string
}

// 并行阶段完成后才进入后续顺序步骤
const stepConfig: { key: string; title: string; description: string }[] = [
  { key: 'parallel_research', title: '并行研究', description: 'DOE实验设计 · 杂质研究 · 晶型研究' },
  { key: 'quality', title: '质量标准', description: '检测方法、杂质限度、放行标准' },
  { key: 'lab_confirmation', title: '小试确认', description: '小试工艺确认批，验证DOE参数可行性' },
  { key: 'scaleup', title: '公斤级放大', description: '放大方案、放大试验、与小试对比' },
  { key: 'report', title: '报告生成', description: '整合报告、下载、提交审核' },
]

export function ProcessOptimizationWorkflowPage({
  optimizationId,
  optimizationName,
  sourceRouteId,
  sourceRouteName,
  onComplete,
  onBack,
}: ProcessOptimizationWorkflowPageProps) {
  const { message } = App.useApp()

  const savedState = typeof window !== 'undefined'
    ? localStorage.getItem(`optimization-workflow-${optimizationId}`)
    : null

  const initialState: WorkflowState = savedState ? JSON.parse(savedState) : {
    currentStep: 0,
    activeParallelTab: 'doe',
    optimizationName,
  sourceRouteId,
    sourceRouteName,
    updatedAt: new Date().toISOString(),
  }

  const [currentStep, setCurrentStep] = useState(initialState.currentStep)
  const [activeParallelTab, setActiveParallelTab] = useState(initialState.activeParallelTab || 'doe')
  const [doeExperiment, setDoeExperiment] = useState<DOEExperiment | undefined>(initialState.doeExperiment)
  const [impurityStudy, setImpurityStudy] = useState<ImpurityStudy | undefined>(initialState.impurityStudy)
  const [crystalFormStudy, setCrystalFormStudy] = useState<CrystalFormStudy | undefined>(initialState.crystalFormStudy)
  const [qualityStandardSet, setQualityStandardSet] = useState<QualityStandardSet | undefined>(initialState.qualityStandardSet)
  const [labConfirmationStudy, setLabConfirmationStudy] = useState<LabConfirmationStudy | undefined>(initialState.labConfirmationStudy)
  const [scaleUpStudy, setScaleUpStudy] = useState<ScaleUpStudy | undefined>(initialState.scaleUpStudy)

  // 并行研究完成状态
  const parallelComplete = useMemo(() => ({
    doe: !!doeExperiment,
    impurity: !!impurityStudy,
    crystal: !!crystalFormStudy,
  }), [doeExperiment, impurityStudy, crystalFormStudy])

  const allParallelComplete = parallelComplete.doe && parallelComplete.impurity && parallelComplete.crystal

  const saveState = async () => {
    const moduleKeyMap: Record<number, OptimizationModule> = {
      0: allParallelComplete ? 'quality' : (activeParallelTab as OptimizationModule),
      1: 'quality',
      2: 'lab_confirmation',
      3: 'scaleup',
      4: 'report',
    }

    const updateData = {
      current_module: moduleKeyMap[currentStep] || 'doe',
      status: currentStep >= 4 ? 'completed' as const : 'in_progress' as const,
      doe_experiment: doeExperiment,
      impurity_study: impurityStudy,
      crystal_form_study: crystalFormStudy,
      quality_standard_set: qualityStandardSet,
      labConfirmationStudy,
      lab_confirmation_study: labConfirmationStudy,
      scale_up_study: scaleUpStudy,
    }

    try {
      await updateOptimization(optimizationId, updateData)
    } catch (e) {
      console.error('后端保存失败，使用本地备份', e)
    }

    const state: WorkflowState = {
      currentStep,
      activeParallelTab,
      doeExperiment,
      impurityStudy,
      crystalFormStudy,
      qualityStandardSet,
      labConfirmationStudy,
      scaleUpStudy,
      optimizationName,
  sourceRouteId,
      sourceRouteName,
      updatedAt: new Date().toISOString(),
    }
    localStorage.setItem(`optimization-workflow-${optimizationId}`, JSON.stringify(state))
  }

  useEffect(() => {
    const timer = setTimeout(() => {
      saveState()
    }, 2000)
    return () => clearTimeout(timer)
  }, [currentStep, activeParallelTab, doeExperiment, impurityStudy, crystalFormStudy, qualityStandardSet, labConfirmationStudy, scaleUpStudy])

  const handleSaveAndExit = () => {
    saveState()
    message.success('✓ 已保存！您可以随时回来继续')
    onBack()
  }

  // 并行模块完成回调 — 不自动跳转，仅标记完成
  const handleDOEComplete = (experiment: DOEExperiment) => {
    setDoeExperiment(experiment)
    message.success('✓ DOE实验设计已完成')
  }

  const handleImpurityComplete = (study: ImpurityStudy) => {
    setImpurityStudy(study)
    message.success('✓ 杂质研究已完成')
  }

  const handleCrystalFormComplete = (study: CrystalFormStudy) => {
    setCrystalFormStudy(study)
    message.success('✓ 晶型研究已完成')
  }

  // 并行研究全部完成 → 进入质量标准
  const handleProceedToQuality = () => {
    if (!allParallelComplete) {
      message.warning('请先完成所有并行研究模块（DOE、杂质、晶型）')
      return
    }
    setCurrentStep(1)
    message.success('并行研究全部完成！进入质量标准建立')
  }

  // 质量标准完成 → 进入小试确认
  const handleQualityComplete = (standards: QualityStandardSet) => {
    setQualityStandardSet(standards)
    setCurrentStep(2)
    message.success('质量标准建立完成！进入小试工艺确认')
  }

  // 小试确认完成 → 进入公斤级放大
  const handleLabConfirmationComplete = (study: LabConfirmationStudy) => {
    setLabConfirmationStudy(study)
    setCurrentStep(3)
    message.success('小试工艺确认完成！进入公斤级放大试验')
  }

  // 公斤级放大完成 → 进入报告生成
  const handleScaleUpComplete = (study: ScaleUpStudy) => {
    setScaleUpStudy(study)
    setCurrentStep(4)
    message.success('公斤级放大完成！进入报告生成')
  }
  // 报告完成
  const handleReportComplete = () => {
    localStorage.removeItem(`optimization-workflow-${optimizationId}`)
    onComplete()
  }

  // 并行模块 Tab 项
  const parallelTabItems = [
    {
      key: 'doe',
      label: (
        <span>
          {parallelComplete.doe ? <CheckCircleFilled style={{ color: '#52c41a', marginRight: 4 }} /> : <ClockCircleFilled style={{ color: '#faad14', marginRight: 4 }} />}
          DOE实验设计
        </span>
      ),
      children: (
        <ModuleDOE
          optimizationId={optimizationId}
          initialData={doeExperiment}
          onComplete={handleDOEComplete}
        />
      ),
    },
    {
      key: 'impurity',
      label: (
        <span>
          {parallelComplete.impurity ? <CheckCircleFilled style={{ color: '#52c41a', marginRight: 4 }} /> : <ClockCircleFilled style={{ color: '#faad14', marginRight: 4 }} />}
          杂质研究
        </span>
      ),
      children: (
        <ModuleImpurity
          sourceRouteId={sourceRouteId}
          optimizationId={optimizationId}
          doeExperiment={doeExperiment}
          initialData={impurityStudy}
          onComplete={handleImpurityComplete}
        />
      ),
    },
    {
      key: 'crystal',
      label: (
        <span>
          {parallelComplete.crystal ? <CheckCircleFilled style={{ color: '#52c41a', marginRight: 4 }} /> : <ClockCircleFilled style={{ color: '#faad14', marginRight: 4 }} />}
          晶型研究
        </span>
      ),
      children: (
        <ModuleCrystalForm
          optimizationId={optimizationId}
          initialData={crystalFormStudy}
          onComplete={handleCrystalFormComplete}
        />
      ),
    },
  ]

  // 底部导航
  const renderNavigation = () => {
    const canGoBack = currentStep > 0
    const isParallelStep = currentStep === 0

    return (
      <Card style={{ marginTop: 16 }}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space>
            <Button onClick={onBack}>← 返回列表</Button>
            {canGoBack && (
              <Button onClick={() => setCurrentStep(currentStep - 1)}>← 上一步</Button>
            )}
          </Space>
          <Space>
            {isParallelStep && (
              <>
                <Tag color={parallelComplete.doe ? 'green' : 'default'}>
                  {parallelComplete.doe ? '✓' : '○'} DOE
                </Tag>
                <Tag color={parallelComplete.impurity ? 'green' : 'default'}>
                  {parallelComplete.impurity ? '✓' : '○'} 杂质
                </Tag>
                <Tag color={parallelComplete.crystal ? 'green' : 'default'}>
                  {parallelComplete.crystal ? '✓' : '○'} 晶型
                </Tag>
              </>
            )}
            {isParallelStep && (
              <Button
                type="primary"
                onClick={handleProceedToQuality}
                disabled={!allParallelComplete}
              >
                进入质量标准 →
              </Button>
            )}
            <Button icon={<SaveOutlined />} onClick={handleSaveAndExit} type="dashed">
              💾 保存并退出
            </Button>
          </Space>
        </Space>
      </Card>
    )
  }

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

      {/* Step 0: 并行研究 */}
      {currentStep === 0 && (
        <>
          {!allParallelComplete && (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              title="并行研究阶段"
              description={`DOE实验设计、杂质研究、晶型研究可同时进行，完成全部三项后进入质量标准建立。已完成 ${Object.values(parallelComplete).filter(Boolean).length}/3`}
            />
          )}
          {allParallelComplete && (
            <Alert
              type="success"
              showIcon
              style={{ marginBottom: 16 }}
              title="✓ 并行研究全部完成"
              description="所有三项研究已完成，可以点击右下方「进入质量标准」继续。您也可以切换 Tab 查看或修改已有结果。"
            />
          )}
          <Card>
            <Tabs
              activeKey={activeParallelTab}
              onChange={setActiveParallelTab}
              items={parallelTabItems}
              size="large"
            />
          </Card>
        </>
      )}

      {/* Step 1: 质量标准 */}
      {currentStep === 1 && (
        <ModuleQualityStandard
          optimizationId={optimizationId}
          doeExperiment={doeExperiment}
          impurityStudy={impurityStudy}
          crystalFormStudy={crystalFormStudy}
          initialData={qualityStandardSet}
          onComplete={handleQualityComplete}
        />
      )}


      {/* Step 2: 小试确认 */}
      {currentStep === 2 && (
        <ModuleLabConfirmation
          optimizationId={optimizationId}
          doeExperiment={doeExperiment}
          qualityStandardSet={qualityStandardSet}
          initialData={labConfirmationStudy}
          onComplete={handleLabConfirmationComplete}
        />
      )}

      {/* Step 3: 公斤级放大 */}
      {currentStep === 3 && (
        <ModuleScaleUp
          optimizationId={optimizationId}
          doeExperiment={doeExperiment}
          labConfirmationStudy={labConfirmationStudy}
          initialData={scaleUpStudy}
          onComplete={handleScaleUpComplete}
        />
      )}

      {/* Step 4: 报告生成 */}
      {currentStep === 4 && (
        <ModuleReport
          optimizationId={optimizationId}
          optimizationName={optimizationName}
          doeExperiment={doeExperiment}
          impurityStudy={impurityStudy}
          crystalFormStudy={crystalFormStudy}
          qualityStandardSet={qualityStandardSet}
          labConfirmationStudy={labConfirmationStudy}
          scaleUpStudy={scaleUpStudy}
          onComplete={handleReportComplete}
        />
      )}

      {renderNavigation()}
    </div>
  )
}
