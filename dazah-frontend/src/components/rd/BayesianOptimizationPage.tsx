'use client'

import { useState, useCallback } from 'react'
import { App,
  Card,
  Button,
  Upload,
  Table,
  Tag,
  Space,
  Typography,
  Select,
  InputNumber,
  Form,
  Divider,
  Input,
  Tabs,
  Checkbox
} from 'antd'
import type { UploadFile } from 'antd/es/upload'
import {
  UploadOutlined,
  DownloadOutlined,
  ExperimentOutlined,
  LoadingOutlined,
  PlusOutlined,
  DeleteOutlined,
  ThunderboltOutlined
} from '@ant-design/icons'
import { runEDBOOptimize, generateReactionScope } from '@/lib/api/research'

const { Title, Text } = Typography
const { Option } = Select

interface ObjectiveConfig {
  column: string
  mode: 'max' | 'min'
}

interface ResultRow {
  key: number
  [key: string]: string | number
}

interface ScopeComponent {
  key: string
  type: 'categorical' | 'numeric'
  values: string
  lower?: number
  upper?: number
  dataPoints?: number
}

export function BayesianOptimizationPage() {
  const { message } = App.useApp()
  const [file, setFile] = useState<File | null>(null)
  const [columns, setColumns] = useState<string[]>([])
  const [objectives, setObjectives] = useState<ObjectiveConfig[]>([
    { column: '', mode: 'max' },
  ])
  const [batchSize, setBatchSize] = useState(5)
  const [savePrediction, setSavePrediction] = useState(false)
  const [loading, setLoading] = useState(false)
  const [resultData, setResultData] = useState<ResultRow[]>([])
  const [resultColumns, setResultColumns] = useState<string[]>([])
  const [predictionData, setPredictionData] = useState<string | null>(null)
  const [predictionFilename, setPredictionFilename] = useState<string | null>(null)
  
  const [scopeComponents, setScopeComponents] = useState<ScopeComponent[]>([
    { key: '', type: 'categorical', values: '' },
  ])
  const [generatingScope, setGeneratingScope] = useState(false)
  const [scopePreview, setScopePreview] = useState<ResultRow[]>([])
  const [scopeColumns, setScopeColumns] = useState<string[]>([])
  const [activeTab, setActiveTab] = useState<string>('scope')
  const [scopeObjectives, setScopeObjectives] = useState<ObjectiveConfig[]>([])

  const parseCSVHeader = useCallback((file: File) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      let text = e.target?.result as string
      if (text.charCodeAt(0) === 0xFEFF) {
        text = text.slice(1)
      }
      
      const lines = text.split(/\r?\n/)
      if (lines.length === 0) {
        message.warning('CSV 文件为空')
        return
      }
      
      const headerLine = lines[0]
      const allCols = headerLine.split(',').map((c) => {
        let col = c.trim()
        if (col.startsWith('"') && col.endsWith('"')) {
          col = col.slice(1, -1)
        }
        return col
      })
      
      const detectedObjectives: ObjectiveConfig[] = []
      
      for (let colIdx = 0; colIdx < allCols.length; colIdx++) {
        const colName = allCols[colIdx]
        if (!colName) continue
        
        let hasPending = false
        for (let i = 1; i < Math.min(lines.length, 100); i++) {
          if (!lines[i].trim()) continue
          const values = lines[i].split(',')
          const cellValue = (values[colIdx] || '').trim().toUpperCase()
          if (cellValue === 'PENDING') {
            hasPending = true
            break
          }
        }
        
        if (hasPending) {
          detectedObjectives.push({ column: colName, mode: 'max' })
        }
      }
      
      const validCols = allCols.filter((c) => c.length > 0)
      setColumns(validCols)
      
      
      if (detectedObjectives.length > 0) {
        setObjectives(detectedObjectives)
        message.success(`已自动检测到 ${detectedObjectives.length} 个优化目标: ${detectedObjectives.map(o => o.column).join(', ')}`)
      } else {
        message.info(`未检测到 PENDING 值，请手动选择优化目标`)
      }
    }
    reader.onerror = () => {
      console.error('Error reading file')
      message.error('文件读取失败')
    }
    reader.readAsText(file, 'UTF-8')
  }, [message])


  const updateObjective = (index: number, field: keyof ObjectiveConfig, value: string) => {
    if (activeTab === 'scope') {
      const updated = [...scopeObjectives]
      updated[index] = { ...updated[index], [field]: value }
      setScopeObjectives(updated)
    } else {
      const updated = [...objectives]
      updated[index] = { ...updated[index], [field]: value }
      setObjectives(updated)
    }
  }

  const handleOptimize = async () => {
    if (!file) {
      message.error('请先上传 CSV 文件')
      return
    }
    
    const currentObjectives = activeTab === 'scope' ? scopeObjectives : objectives
    const validObjectives = currentObjectives.filter(o => o.column)
    if (validObjectives.length === 0) {
      message.error('请至少选择一个优化目标')
      return
    }
    
    setLoading(true)
    try {
      const result = await runEDBOOptimize(
        file,
        validObjectives.map(o => o.column),
        validObjectives.map(o => o.mode),
        batchSize,
        savePrediction
      )
      
      const csvText = result.csv_data
      const csvLines = csvText.split(/\r?\n/).filter(l => l.trim())
      const headers = csvLines[0].split(',').map(h => h.trim())
      
      const rows: ResultRow[] = csvLines.slice(1).map((line, idx) => {
        const values = line.split(',')
        const row: ResultRow = { key: idx }
        headers.forEach((h, i) => {
          const val = values[i]?.trim()
          row[h] = isNaN(Number(val)) ? val : Number(val)
        })
        return row
      })
      
      setResultData(rows)
      setResultColumns(headers)
      
      if (result.prediction_data) {
        setPredictionData(result.prediction_data)
        setPredictionFilename(result.prediction_filename || 'predictions.csv')
      }
      
      message.success(`优化完成，共 ${rows.length} 条结果`)
    } catch (error: any) {
      console.error('Optimization error:', error)
      message.error(error.message || '优化失败')
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = () => {
    if (resultData.length === 0) return
    const headers = resultColumns
    const csvContent = [
      headers.join(','),
      ...resultData.map(row => headers.map(h => row[h]).join(','))
    ].join('\n')
    
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = 'optimization_results.csv'
    link.click()
  }

  const handleDownloadPrediction = () => {
    if (!predictionData || !predictionFilename) return
    const blob = new Blob([predictionData], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = predictionFilename
    link.click()
  }

  const addScopeComponent = () => {
    setScopeComponents([...scopeComponents, { key: '', type: 'categorical', values: '' }])
  }

  const removeScopeComponent = (index: number) => {
    const updated = scopeComponents.filter((_, i) => i !== index)
    setScopeComponents(updated.length > 0 ? updated : [{ key: '', type: 'categorical', values: '' }])
  }

  const updateScopeComponent = (index: number, field: keyof ScopeComponent, value: any) => {
    const updated = [...scopeComponents]
    updated[index] = { ...updated[index], [field]: value }
    setScopeComponents(updated)
  }

  const handleGenerateScope = async () => {
    const validComponents = scopeComponents.filter(c => c.key)
    if (validComponents.length === 0) {
      message.error('请至少添加一个变量')
      return
    }
    
    const components: Record<string, (string | number)[]> = {}
    for (const comp of validComponents) {
      if (comp.type === 'categorical') {
        components[comp.key] = comp.values.split(',').map(v => v.trim()).filter(v => v)
      } else {
        if (comp.lower === undefined || comp.upper === undefined || !comp.dataPoints) {
          message.error(`变量 ${comp.key} 缺少范围或点数`)
          return
        }
        const step = (comp.upper - comp.lower) / (comp.dataPoints - 1)
        const values = Array.from({ length: comp.dataPoints }, (_, i) => comp.lower! + i * step)
        components[comp.key] = values
      }
    }
    
    setGeneratingScope(true)
    try {
      const objectives = scopeObjectives.filter(o => o.column).map(o => o.column)
      const result = await generateReactionScope(components, objectives, batchSize)
      
      // Check if optimization was completed
      if (result.optimization_completed && result.recommended_experiments) {
        // Use the optimized results
        const csvText = result.recommended_experiments
        const csvLines = csvText.split(/\r?\n/).filter(l => l.trim())
        const headers = csvLines[0].split(',').map(h => h.trim())
        
        const rows: ResultRow[] = csvLines.slice(1).map((line, idx) => {
          const values = line.split(',')
          const row: ResultRow = { key: idx }
          headers.forEach((h, i) => {
            const val = values[i]?.trim()
            row[h] = isNaN(Number(val)) ? val : Number(val)
          })
          return row
        })
        
        setResultData(rows)
        setResultColumns(headers)
        
        // Also set the file for potential re-optimization
        const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8;' })
        const csvFile = new File([blob], 'reaction_scope_optimized.csv', { type: 'text/csv' })
        setFile(csvFile)
        setColumns(headers)
        
        message.success(`反应范围已生成并优化完成`)
      } else {
        // Optimization failed or no objectives, just show scope
        const csvText = result.csv_data
        const csvLines = csvText.split(/\r?\n/).filter(l => l.trim())
        const headers = csvLines[0].split(',').map(h => h.trim())
        
        const rows: ResultRow[] = csvLines.slice(1, 21).map((line, idx) => {
          const values = line.split(',')
          const row: ResultRow = { key: idx }
          headers.forEach((h, i) => {
            const val = values[i]?.trim()
            row[h] = isNaN(Number(val)) ? val : Number(val)
          })
          return row
        })
        
        setScopePreview(rows)
        setScopeColumns(headers)
        
        const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8;' })
        const csvFile = new File([blob], 'reaction_scope.csv', { type: 'text/csv' })
        setFile(csvFile)
        setColumns(headers)
        
        if (result.optimization_error) {
          message.warning(`反应范围已生成，但优化失败: ${result.optimization_error}`)
        } else {
          message.success(`反应范围已生成，共 ${result.row_count} 个实验组合`)
        }
      }
    } catch (error: any) {
      console.error('Generate scope error:', error)
      message.error(error.message || '生成反应范围失败')
    } finally {
      setGeneratingScope(false)
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <Title level={2}>EDBO+ 贝叶斯优化</Title>
      <Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>
        基于实验设计贝叶斯优化（EDBO+）的多目标反应条件优化
      </Text>

      <Card title="1. 输入数据" style={{ marginBottom: 16 }}>
        <Tabs
          activeKey={activeTab}
          onChange={(key) => {
            setActiveTab(key)
            // Clear all results when switching tabs
            setScopePreview([])
            setScopeColumns([])
            setResultData([])
            setResultColumns([])
            setFile(null)
            setColumns([])
            setPredictionData(null)
            setPredictionFilename(null)
          }}
          items={[
            {
              key: 'scope',
              label: (
                <span>
                  <ThunderboltOutlined /> 生成反应范围
                </span>
              ),
              children: (
                <div>
                  <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
                    定义反应变量，自动生成所有可能的实验组合
                  </Text>
                  
                  {scopeComponents.map((comp, index) => (
                    <div key={index} style={{ marginBottom: 12 }}>
                      <Space align="start">
                        <Input
                          placeholder="变量名称"
                          value={comp.key}
                          onChange={(e) => updateScopeComponent(index, 'key', e.target.value)}
                          style={{ width: 150 }}
                        />
                        <Select
                          value={comp.type}
                          onChange={(val) => updateScopeComponent(index, 'type', val)}
                          style={{ width: 120 }}
                        >
                          <Option value="categorical">类别型</Option>
                          <Option value="numeric">数值型</Option>
                        </Select>
                        
                        {comp.type === 'categorical' ? (
                          <Input
                            placeholder="类别值（用英文逗号分隔）"
                            value={comp.values}
                            onChange={(e) => updateScopeComponent(index, 'values', e.target.value)}
                            style={{ width: 300 }}
                          />
                        ) : (
                          <Space>
                            <InputNumber
                              placeholder="下限"
                              value={comp.lower}
                              onChange={(val) => updateScopeComponent(index, 'lower', val)}
                              style={{ width: 100 }}
                            />
                            <InputNumber
                              placeholder="上限"
                              value={comp.upper}
                              onChange={(val) => updateScopeComponent(index, 'upper', val)}
                              style={{ width: 100 }}
                            />
                            <InputNumber
                              placeholder="数据点数"
                              value={comp.dataPoints}
                              min={2}
                              onChange={(val) => {
                                const updated = [...scopeComponents]
                                updated[index] = { ...updated[index], dataPoints: val ?? undefined }
                                setScopeComponents(updated)
                              }}
                              style={{ width: 100 }}
                            />
                          </Space>
                        )}
                        {scopeComponents.length > 1 && (
                          <Button
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                            onClick={() => removeScopeComponent(index)}
                          />
                        )}
                      </Space>
                    </div>
                  ))}
                  
                  <Button type="dashed" onClick={addScopeComponent} icon={<PlusOutlined />}>
                      添加变量
                    </Button>

                  {scopePreview.length > 0 && (
                    <>
                      <Divider />
                      <Text strong>预览 (前 20 行):</Text>
                      <Table
                        dataSource={scopePreview}
                        columns={scopeColumns.map((col) => ({
                          title: col,
                          dataIndex: col,
                          key: col
                        }))}
                        scroll={{ x: 'max-content' }}
                        pagination={false}
                        size="small"
                        style={{ marginTop: 8 }}
                      />
                      <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                        共 {scopePreview.length} 行预览，完整数据已加载用于优化
                      </Text>
                    </>
                  )}
                </div>
              )
            },
            {
              key: 'upload',
              label: (
                <span>
                  <UploadOutlined /> 上传 CSV
                </span>
              ),
              children: (
                <Upload.Dragger
                  accept=".csv"
                  maxCount={1}
                  beforeUpload={(file) => {
                    setFile(file)
                    setResultData([])
                    setResultColumns([])
                    parseCSVHeader(file)
                    message.success(`已上传: ${file.name}`)
                    return false
                  }}
                  onRemove={() => {
                    setFile(null)
                    setColumns([])
                    setResultData([])
                    setResultColumns([])
                    setScopePreview([])
                    setScopeColumns([])
                  }}
                >
                  <p className="ant-upload-drag-icon">
                    <UploadOutlined />
                  </p>
                  <p className="ant-upload-text">点击或拖拽 CSV 文件到此区域</p>
                  <p className="ant-upload-hint">
                    支持 .csv 格式，文件将包含反应条件的所有组合
                  </p>
                </Upload.Dragger>
              )
            },
          ]}
        />
        
        {columns.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <Text type="secondary">检测到 {columns.length} 列: </Text>
            <Space wrap>
              {columns.map((col) => (
                <Tag key={col} color="blue">{col}</Tag>
              ))}
            </Space>
          </div>
        )}
      </Card>

      <Card title="2. 配置优化目标" style={{ marginBottom: 16 }}>
        {activeTab === 'scope' ? (
          <>
            <div style={{ display: 'flex', marginBottom: 12, fontWeight: 'bold' }}>
              <span style={{ flex: 1, paddingLeft: 10 }}>目标名称</span>
              <span style={{ width: 100, textAlign: 'right', paddingRight: 10 }}>优化方向</span>
            </div>
            {scopeObjectives.map((obj, index) => (
              <div key={index} style={{ display: 'flex', marginBottom: 8, alignItems: 'center' }}>
                <Input
                  placeholder="目标名称"
                  value={obj.column}
                  onChange={(e) => {
                    const updated = [...scopeObjectives]
                    updated[index] = { ...updated[index], column: e.target.value }
                    setScopeObjectives(updated)
                  }}
                  style={{ flex: 1, marginRight: 8, paddingLeft: 10 }}
                />
                <Select
                  value={obj.mode}
                  onChange={(val) => {
                    const updated = [...scopeObjectives]
                    updated[index] = { ...updated[index], mode: val }
                    setScopeObjectives(updated)
                  }}
                  style={{ width: 100, marginRight: 8 }}
                >
                  <Option value="max">最大化</Option>
                  <Option value="min">最小化</Option>
                </Select>
                <Button
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => {
                    const updated = scopeObjectives.filter((_, i) => i !== index)
                    setScopeObjectives(updated)
                  }}
                />
              </div>
            ))}
            <Button 
              type="dashed" 
              onClick={() => setScopeObjectives([...scopeObjectives, { column: '', mode: 'max' }])}
              icon={<PlusOutlined />}
            >
              添加目标
            </Button>
            <Divider />
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ marginRight: 12 }}>通量大小:</Text>
              <InputNumber
                min={1}
                max={20}
                value={batchSize}
                onChange={(val) => setBatchSize(val ?? 5)}
                style={{ width: 100 }}
              />
              <Text type="secondary" style={{ marginLeft: 8 }}>
                表示同时进行的实验数量
              </Text>
            </div>
            <Button
              type="primary"
              icon={generatingScope ? <LoadingOutlined /> : <ThunderboltOutlined />}
              onClick={handleGenerateScope}
              loading={generatingScope}
              disabled={scopeObjectives.filter(o => o.column).length === 0}
            >
              生成反应范围
            </Button>
          </>
        ) : objectives.length > 0 ? (
          <>
            <div style={{ display: 'flex', marginBottom: 12, fontWeight: 'bold' }}>
              <span style={{ flex: 1, paddingLeft: 10 }}>目标名称</span>
              <span style={{ width: 100, textAlign: 'right', paddingRight: 10 }}>优化方向</span>
            </div>
            {objectives.map((obj, index) => (
              <div key={index} style={{ display: 'flex', marginBottom: 8 }}>
                <span style={{ flex: 1, paddingLeft: 10 }}>{obj.column}</span>
                <Select
                  value={obj.mode}
                  onChange={(val) => updateObjective(index, 'mode', val)}
                  style={{ width: 100 }}
                >
                  <Option value="max">最大化</Option>
                  <Option value="min">最小化</Option>
                </Select>
              </div>
            ))}
          </>
        ) : (
          <div style={{ textAlign: 'center', padding: '20px 0', color: '#999' }}>
            未检测到 PENDING 值，请确保 CSV 文件包含需要优化的目标列
          </div>
        )}
      </Card>

      {activeTab === 'upload' && (
        <Card style={{ marginBottom: 16 }}>
          <div style={{ marginBottom: 16 }}>
            <Text strong style={{ marginRight: 12 }}>通量大小:</Text>
            <InputNumber
              min={1}
              max={20}
              value={batchSize}
              onChange={(val) => setBatchSize(val ?? 5)}
              style={{ width: 100 }}
            />
            <Text type="secondary" style={{ marginLeft: 8 }}>
              表示同时进行的实验数量
            </Text>
          </div>
          <Button
            type="primary"
            size="large"
            icon={loading ? <LoadingOutlined /> : <ExperimentOutlined />}
            onClick={handleOptimize}
            loading={loading}
            disabled={!file || objectives.every((o) => !o.column)}
            block
          >
            {loading ? '正在优化中（可能需要 30-60 秒）...' : '运行贝叶斯优化'}
          </Button>
        </Card>
      )}

      {resultData.length > 0 && (
        <Card
          title={`结果 (${resultData.length} 条)`}
          extra={
            <Space>
              {predictionData && (
                <Button icon={<DownloadOutlined />} onClick={handleDownloadPrediction}>
                  下载预测文件
                </Button>
              )}
              <Button icon={<DownloadOutlined />} onClick={handleDownload}>
                下载结果 CSV
              </Button>
            </Space>
          }
        >
          <Table
            dataSource={resultData}
            columns={resultColumns.map((col) => ({
              title: col,
              dataIndex: col,
              key: col,
              sorter: (a, b) => {
                const va = a[col]
                const vb = b[col]
                if (typeof va === 'number' && typeof vb === 'number') return va - vb
                return String(va).localeCompare(String(vb))
              },
              render: (val) => {
                if (typeof val === 'number') return val.toFixed(4)
                return val
              }
            }))}
            scroll={{ x: 'max-content' }}
            pagination={{ pageSize: 20, showSizeChanger: true }}
            size="small"
          />
        </Card>
      )}
    </div>
  )
}
