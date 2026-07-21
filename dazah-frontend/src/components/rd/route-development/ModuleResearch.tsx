'use client'

import { useState, useEffect, useRef } from 'react'
import { Card, Button, Space, Tag, Collapse, App, Alert, Progress, Spin, Tabs, Table, Descriptions, Divider, Upload } from 'antd'
import { CheckCircleOutlined, SaveOutlined, ExperimentOutlined, ShoppingCartOutlined, SafetyOutlined, FileTextOutlined, DownloadOutlined, EditOutlined, UploadOutlined } from '@ant-design/icons'
import type { CandidateRoute, ExperimentPlan } from '@/types/rd'
import { updateRoute } from '@/lib/api/rd'

interface ModuleResearchProps {
  routeId: string
  literatureSource?: string
  literatureFile?: File | null
  initialData?: {
    candidateRoutes: CandidateRoute[]
    selectedRouteIds: string[]
    experimentPlans: ExperimentPlan[]
  }
  onComplete: (data: {
    literatureSource: string
    candidateRoutes: CandidateRoute[]
    selectedRouteIds: string[]
    experimentPlans: ExperimentPlan[]
  }) => void
  onSaveAndExit?: (data: {
    candidateRoutes: CandidateRoute[]
    selectedRouteIds: string[]
    experimentPlans: ExperimentPlan[]
  }) => void
}

export function ModuleResearch({ routeId, literatureSource = '', literatureFile, initialData, onComplete, onSaveAndExit }: ModuleResearchProps) {
  const { message } = App.useApp()
  // 只有在没有初始数据且有文件需要解析时，才显示解析界面
  const [isParsing, setIsParsing] = useState(!initialData && !!literatureFile)
  const [parseProgress, setParseProgress] = useState(0)
  const [candidateRoutes, setCandidateRoutes] = useState<CandidateRoute[]>(initialData?.candidateRoutes || [])
  const [selectedRouteIds, setSelectedRouteIds] = useState<string[]>(initialData?.selectedRouteIds || [])
  const [experimentPlans, setExperimentPlans] = useState<ExperimentPlan[]>(initialData?.experimentPlans || [])
  const [parseComplete, setParseComplete] = useState(!!initialData)
  const [activeTab, setActiveTab] = useState('routes')
  const [parseError, setParseError] = useState<string | null>(null)
  const [parseStatus, setParseStatus] = useState<string>('')
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const timerRef = useRef<NodeJS.Timeout | null>(null)
  const startTimeRef = useRef<number>(0)
  const [, forceUpdate] = useState(0)  // 强制更新

  // 独立的计时器 useEffect
  useEffect(() => {
    if (!isParsing) {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
      return
    }
    
    startTimeRef.current = Date.now()
    timerRef.current = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTimeRef.current) / 1000)
      setElapsedSeconds(elapsed)
    }, 100)
    
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
      }
    }
  }, [isParsing])

  // 如果没有初始数据，调用后端 API 解析（SSE 流式响应）
  useEffect(() => {
    if (initialData || !literatureFile) return
    
    const parseLiterature = async () => {
      setIsParsing(true)
      setParseProgress(0)
      setParseError(null)
      setParseStatus('正在准备...')
      setElapsedSeconds(0)
      
      try {
        const formData = new FormData()
        formData.append('file', literatureFile)
        
        const response = await fetch('/api/v1/research/literature/analyze', {
          method: 'POST',
          body: formData,
        })
        
        if (!response.ok) {
          throw new Error(`API 请求失败: ${response.status}`)
        }
        
        if (!response.body) {
          throw new Error('响应体为空')
        }
        
        // 读取 SSE 流
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          
          buffer += decoder.decode(value, { stream: true })
          
          // 解析 SSE 事件
          const lines = buffer.split('\n')
          buffer = lines.pop() || '' // 保留未完成的行
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                
                // 更新进度和状态
                if (data.progress !== undefined) {
                  setParseProgress(data.progress)
                }
                if (data.message) {
                  setParseStatus(data.message)
                }
                
                // 处理错误
                if (data.status === 'error') {
                  setParseError(data.error || '解析失败')
                  setIsParsing(false)
                  setParseComplete(true)
                  message.error(data.error || '解析失败')
                  return
                }
                
                // 处理完成
                if (data.status === 'complete' && data.data) {
                  const result = data.data
                  
                  // 检查是否有错误
                  if (result.error) {
                    setParseError(result.error)
                    setIsParsing(false)
                    setParseComplete(true)
                    message.warning(`解析完成，但存在问题: ${result.error}`)
                    return
                  }
                  
                  const routes = result.candidate_routes || []
                  const plans = result.experiment_plans || []
                  
                  if (routes.length === 0) {
                    setParseError('未能从文献中提取到合成路线，请检查文献内容是否包含合成路线描述')
                    setIsParsing(false)
                    setParseComplete(true)
                    message.warning('未能提取到合成路线')
                    return
                  }
                  
                  setCandidateRoutes(routes)
                  setExperimentPlans(plans)
                  setIsParsing(false)
                  setParseComplete(true)
                  setParseStatus('解析完成')
                  
                  const recommendedIds = routes.filter((r: CandidateRoute) => r.is_recommended).map((r: CandidateRoute) => r.id)
                  setSelectedRouteIds(recommendedIds)
                  
                  // 保存 AI 解析结果到后端
                  try {
                    await updateRoute(routeId, {
                      candidate_routes: routes,
                      experiment_plans: plans,
                      selected_route_ids: recommendedIds,
                      status: 'in_progress',
                    })
                  } catch (e) {
                    console.error('保存解析结果失败', e)
                  }
                  
                  const totalTime = Math.floor((Date.now() - startTimeRef.current) / 1000)
                  message.success(`解析完成！耗时 ${totalTime} 秒，提取到 ${routes.length} 条路线，已生成 ${plans.length} 个实验方案`)
                  return
                }
              } catch (e) {
                console.error('解析 SSE 数据失败:', e)
              }
            }
          }
        }
        
      } catch (error) {
        console.error('文献解析失败:', error)
        setParseError(error instanceof Error ? error.message : '解析失败')
        setIsParsing(false)
        setParseComplete(true)
        message.error('文献解析失败，请检查 AI 配置或稍后重试')
      }
    }
    
    parseLiterature()
  }, [initialData, literatureFile, message])

  const handleSelectRoute = (routeId: string) => {
    setSelectedRouteIds(prev =>
      prev.includes(routeId)
        ? prev.filter(id => id !== routeId)
        : [...prev, routeId]
    )
  }

  const handleConfirm = () => {
    if (selectedRouteIds.length === 0) {
      message.warning('请至少选择一条路线')
      return
    }
    onComplete({
      literatureSource,
      candidateRoutes,
      selectedRouteIds,
      experimentPlans,
    })
    message.success('方案已确认，进入下一步')
  }

  const handleSaveAndExit = () => {
    if (onSaveAndExit) {
      onSaveAndExit({
        candidateRoutes,
        selectedRouteIds,
        experimentPlans,
      })
      message.success('已保存当前进度')
    }
  }

  // 解析中界面
  if (isParsing) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <Spin size="large" />
        <div style={{ marginTop: 24, fontSize: 16, color: '#666' }}>
          {parseStatus || 'AI 正在解析文献，提取合成路线...'}
        </div>
        <Progress 
          percent={parseProgress} 
          status="active" 
          style={{ maxWidth: 400, margin: '24px auto' }}
        />
        <div style={{ color: '#999', fontSize: 13 }}>
          {parseProgress < 30 ? '正在读取和提取文件内容...' :
           parseProgress < 50 ? '文件提取完成，准备 AI 分析...' :
           parseProgress < 90 ? 'AI 正在分析文献，识别合成路线、反应条件和物料信息...' :
           'AI 分析完成，正在整理结果...'}
        </div>
        <div style={{ marginTop: 12, fontSize: 14, color: '#1890ff', fontWeight: 500 }}>
          ⏱ AI 运行时长：{elapsedSeconds} 秒
        </div>
      </div>
    )
  }

  // 如果没有初始数据且没有文件，显示上传文件界面
  if (!initialData && !literatureFile && candidateRoutes.length === 0) {
    return (
      <div style={{ padding: 40 }}>
        <Alert
          title="需要上传文献文件"
          description="请返回上一步上传文献文件，或重新开始工作流"
          type="warning"
          showIcon
          style={{ marginBottom: 24 }}
        />
        <div style={{ textAlign: 'center' }}>
          <Button type="primary" onClick={() => window.history.back()}>
            返回上传文件
          </Button>
        </div>
      </div>
    )
  }

  // 解析错误界面
  if (parseError && candidateRoutes.length === 0) {
    return (
      <div style={{ padding: 40 }}>
        <Alert
          title="文献解析失败"
          description={parseError}
          type="error"
          showIcon
          style={{ marginBottom: 24 }}
        />
        <div style={{ textAlign: 'center' }}>
          <Space>
            <Button onClick={() => window.location.reload()}>
              重新上传
            </Button>
            {onSaveAndExit && (
              <Button type="primary" onClick={handleSaveAndExit}>
                保存并退出
              </Button>
            )}
          </Space>
        </div>
      </div>
    )
  }

  return (
    <div>
      {parseError && (
        <Alert
          title="解析警告"
          description={parseError}
          type="warning"
          showIcon
          closable
          style={{ marginBottom: 16 }}
        />
      )}
      
      <Card 
        title={<span><ExperimentOutlined /> 文献解析结果</span>}
        extra={
          <Tag color="blue">
            共 {candidateRoutes.length} 条路线
          </Tag>
        }
      >
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'routes',
              label: (
                <span>
                  <FileTextOutlined /> 候选路线 ({candidateRoutes.length})
                </span>
              ),
              children: (
                <div>
                  <Alert
                    title="请评估并选择要实验验证的路线"
                    description="系统已根据文献提取了所有合成路线，请根据反应安全性、放大可行性、质量可控性和成本经济性四个维度进行评估，选择 1-3 条路线进入实验验证阶段。"
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                  />
                  
                  <Collapse
                    accordion
                    items={candidateRoutes.map(route => ({
                      key: route.id,
                      label: (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, width: '100%' }}>
                          <input
                            type="checkbox"
                            checked={selectedRouteIds.includes(route.id)}
                            onChange={(e) => {
                              e.stopPropagation()
                              handleSelectRoute(route.id)
                            }}
                            onClick={(e) => e.stopPropagation()}
                            style={{ width: 18, height: 18 }}
                          />
                          <span style={{ fontWeight: 500, fontSize: 15 }}>{route.name}</span>
                          {route.is_recommended && (
                            <Tag color="green" style={{ marginLeft: 8 }}>推荐</Tag>
                          )}
                          <Tag color="blue">{route.steps} 步</Tag>
                          <Tag color="orange">总收率 {route.total_yield}%</Tag>
                        </div>
                      ),
                      children: (
                        <div style={{ padding: '8px 0' }}>
                          <Descriptions bordered size="small" column={2}>
                            <Descriptions.Item label="路线描述" span={2}>{route.description}</Descriptions.Item>
                            <Descriptions.Item label="起始物料">
                              {route.starting_materials.map((m, i) => (
                                <Tag key={i} style={{ marginBottom: 4 }}>{m}</Tag>
                              ))}
                            </Descriptions.Item>
                            <Descriptions.Item label="关键步骤">{route.key_step}</Descriptions.Item>
                            <Descriptions.Item label="文献页码">{route['文献页码'] || '-'}</Descriptions.Item>
                            <Descriptions.Item label="反应条件">{route['反应条件'] || '-'}</Descriptions.Item>
                            <Descriptions.Item label="优势" span={2}>
                              {route.advantages.map((a, i) => (
                                <Tag key={i} color="green" style={{ marginBottom: 4 }}>{a}</Tag>
                              ))}
                            </Descriptions.Item>
                            <Descriptions.Item label="风险" span={2}>
                              {route.risks.map((r, i) => (
                                <Tag key={i} color="red" style={{ marginBottom: 4 }}>{r}</Tag>
                              ))}
                            </Descriptions.Item>
                          </Descriptions>
                        </div>
                      ),
                    }))}
                  />
                </div>
              ),
            },
            {
              key: 'plans',
              label: (
                <span>
                  <ExperimentOutlined /> 实验方案 ({experimentPlans.length})
                </span>
              ),
              children: (
                <div>
                  <Alert
                    title="实验方案已根据候选路线自动生成"
                    description="每个实验方案包含详细的操作步骤、所需物料、设备需求、分析方法和安全注意事项。可以下载方案文档用于实验操作。"
                    type="success"
                    showIcon
                    style={{ marginBottom: 16 }}
                  />
                  
                  <Space orientation="vertical" style={{ width: '100%' }} size="large">
                    {experimentPlans.map((plan, idx) => (
                      <Card 
                        key={idx}
                        title={plan.route_name}
                        size="small"
                        extra={
                          <Space>
                            <Button 
                              size="small" 
                              icon={<DownloadOutlined />}
                              onClick={() => {
                                let md = `# ${plan.route_name} 实验方案\n\n`
                                md += `**预计周期：** ${plan.estimated_duration}\n\n`
                                md += `## 实验步骤\n\n`
                                plan.steps.forEach(step => {
                                  md += `### 步骤${step.step_no}：${step.description}\n\n`
                                  md += `- **试剂：** ${step.reagents.join('、')}\n`
                                  md += `- **条件：** ${step.conditions}\n`
                                  md += `- **预计收率：** ${step.expected_yield}%\n`
                                  md += `- **耗时：** ${step.duration}\n`
                                  if (step.notes) md += `- **备注：** ${step.notes}\n`
                                  md += `\n`
                                })
                                md += `## 分析方法\n\n`
                                md += `| 方法 | 目的 | 详情 | 设备 |\n`
                                md += `|------|------|------|------|\n`
                                plan.analysis_methods.forEach(m => {
                                  md += `| ${m.name} | ${m.purpose} | ${m.method} | ${m.equipment} |\n`
                                })
                                md += `\n## 物料清单\n\n`
                                md += `| 物料 | 数量 | 纯度 | 供应商 | 到货周期 |\n`
                                md += `|------|------|------|--------|----------|\n`
                                plan.materials.forEach(m => {
                                  md += `| ${m.name} | ${m.quantity} | ${m.purity || '-'} | ${m.supplier || '-'} | ${m.lead_time || '-'} |\n`
                                })
                                md += `\n## 设备需求\n\n`
                                plan.equipment.forEach(e => { md += `- ${e}\n` })
                                md += `\n## 安全注意事项\n\n`
                                plan.safety_notes.forEach(n => { md += `- ${n}\n` })
                                
                                const blob = new Blob([md], { type: 'text/markdown' })
                                const url = URL.createObjectURL(blob)
                                const a = document.createElement('a')
                                a.href = url
                                a.download = `${plan.route_name}_实验方案.md`
                                a.click()
                                URL.revokeObjectURL(url)
                                message.success('方案已下载')
                              }}
                            >
                              下载
                            </Button>
                            <Button 
                              size="small" 
                              icon={<EditOutlined />}
                              onClick={() => message.info('编辑功能开发中...')}
                            >
                              编辑
                            </Button>
                          </Space>
                        }
                      >
                        <div>
                          <Descriptions bordered size="small" column={2} style={{ marginBottom: 16 }}>
                            <Descriptions.Item label="预计周期">{plan.estimated_duration}</Descriptions.Item>
                            <Descriptions.Item label="步骤数">{plan.steps.length} 步</Descriptions.Item>
                            <Descriptions.Item label="设备需求" span={2}>
                              {plan.equipment.map((eq, i) => (
                                <Tag key={i} style={{ marginBottom: 4 }}>{eq}</Tag>
                              ))}
                            </Descriptions.Item>
                            <Descriptions.Item label="安全注意事项" span={2}>
                              <ul style={{ margin: 0, paddingLeft: 20 }}>
                                {plan.safety_notes.map((note, i) => (
                                  <li key={i} style={{ color: '#ff4d4f' }}>{note}</li>
                                ))}
                              </ul>
                            </Descriptions.Item>
                          </Descriptions>

                          {/* 实验步骤 */}
                          <Card title="实验步骤" size="small" style={{ marginBottom: 16 }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                              {plan.steps.map((step, i) => (
                                <Card key={i} size="small" style={{ backgroundColor: '#fafafa' }}>
                                  <div style={{ fontWeight: 500, marginBottom: 8 }}>
                                    步骤 {step.step_no}：{step.description}
                                  </div>
                                  <Descriptions size="small" column={2} bordered>
                                    <Descriptions.Item label="试剂">
                                      {step.reagents.map((r, j) => (
                                        <Tag key={j} color="blue" style={{ marginBottom: 2 }}>{r}</Tag>
                                      ))}
                                    </Descriptions.Item>
                                    <Descriptions.Item label="反应条件">{step.conditions}</Descriptions.Item>
                                    <Descriptions.Item label="预计收率">{step.expected_yield}%</Descriptions.Item>
                                    <Descriptions.Item label="耗时">{step.duration}</Descriptions.Item>
                                    {step.notes && (
                                      <Descriptions.Item label="备注" span={2}>{step.notes}</Descriptions.Item>
                                    )}
                                  </Descriptions>
                                </Card>
                              ))}
                            </div>
                          </Card>

                          {/* 分析方法 */}
                          {plan.analysis_methods && plan.analysis_methods.length > 0 && (
                            <Card title="分析方法" size="small" style={{ marginBottom: 16 }}>
                              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                  <tr style={{ backgroundColor: '#fafafa' }}>
                                    <th style={{ padding: 8, border: '1px solid #f0f0f0', textAlign: 'left' }}>方法</th>
                                    <th style={{ padding: 8, border: '1px solid #f0f0f0', textAlign: 'left' }}>目的</th>
                                    <th style={{ padding: 8, border: '1px solid #f0f0f0', textAlign: 'left' }}>详情</th>
                                    <th style={{ padding: 8, border: '1px solid #f0f0f0', textAlign: 'left' }}>设备</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {plan.analysis_methods.map((method, i) => (
                                    <tr key={i}>
                                      <td style={{ padding: 8, border: '1px solid #f0f0f0' }}>{method.name}</td>
                                      <td style={{ padding: 8, border: '1px solid #f0f0f0' }}>{method.purpose}</td>
                                      <td style={{ padding: 8, border: '1px solid #f0f0f0' }}>{method.method}</td>
                                      <td style={{ padding: 8, border: '1px solid #f0f0f0' }}>{method.equipment}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </Card>
                          )}

                          {/* 物料清单 */}
                          {plan.materials && plan.materials.length > 0 && (
                            <Card title="物料清单" size="small">
                              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                  <tr style={{ backgroundColor: '#fafafa' }}>
                                    <th style={{ padding: 8, border: '1px solid #f0f0f0', textAlign: 'left' }}>物料</th>
                                    <th style={{ padding: 8, border: '1px solid #f0f0f0', textAlign: 'left' }}>CAS号</th>
                                    <th style={{ padding: 8, border: '1px solid #f0f0f0', textAlign: 'left' }}>数量</th>
                                    <th style={{ padding: 8, border: '1px solid #f0f0f0', textAlign: 'left' }}>纯度</th>
                                    <th style={{ padding: 8, border: '1px solid #f0f0f0', textAlign: 'left' }}>供应商</th>
                                    <th style={{ padding: 8, border: '1px solid #f0f0f0', textAlign: 'left' }}>到货周期</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {plan.materials.map((material, i) => (
                                    <tr key={i}>
                                      <td style={{ padding: 8, border: '1px solid #f0f0f0' }}>{material.name}</td>
                                      <td style={{ padding: 8, border: '1px solid #f0f0f0' }}>{material.cas_number || '-'}</td>
                                      <td style={{ padding: 8, border: '1px solid #f0f0f0' }}>{material.quantity}</td>
                                      <td style={{ padding: 8, border: '1px solid #f0f0f0' }}>{material.purity || '-'}</td>
                                      <td style={{ padding: 8, border: '1px solid #f0f0f0' }}>{material.supplier || '-'}</td>
                                      <td style={{ padding: 8, border: '1px solid #f0f0f0' }}>{material.lead_time || '-'}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </Card>
                          )}
                        </div>
                      </Card>
                    ))}
                  </Space>
                </div>
              ),
            },
          ]}
        />

        <Divider />

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <Tag color="blue">已选择 {selectedRouteIds.length} 条路线</Tag>
            {selectedRouteIds.length > 0 && (
              <span style={{ color: '#666', fontSize: 13, marginLeft: 8 }}>
                {candidateRoutes.filter(r => selectedRouteIds.includes(r.id)).map(r => r.name).join('、')}
              </span>
            )}
          </div>
          <Space>
            {onSaveAndExit && (
              <Button 
                icon={<SaveOutlined />} 
                onClick={handleSaveAndExit}
                size="large"
                disabled={selectedRouteIds.length === 0}
              >
                💾 保存并退出（稍后继续）
              </Button>
            )}
            <Button
              type="primary"
              icon={<CheckCircleOutlined />}
              onClick={handleConfirm}
              size="large"
              disabled={selectedRouteIds.length === 0}
            >
              ✓ 方案确认，开始做实验 →
            </Button>
          </Space>
        </div>
      </Card>
    </div>
  )
}
