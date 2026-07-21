/**
 * 工艺优化报告模板系统
 * 
 * 提供标准化的报告生成模板，确保报告格式统一、内容完整
 */

import type {
  DOEExperiment,
  ImpurityStudy,
  CrystalFormStudy,
  QualityStandardSet,
  ScaleUpStudy,
  LabConfirmationStudy,
} from '@/types/rd'

export interface ReportMetadata {
  reportNo: string
  reportTime: string
  optimizationName: string
  projectName?: string
  routeName?: string
}

/**
 * 生成报告头部
 */
export function generateReportHeader(metadata: ReportMetadata): string {
  let md = `# 工艺优化报告\n\n`
  md += `**报告编号：** ${metadata.reportNo}\n`
  md += `**生成时间：** ${metadata.reportTime}\n`
  md += `**优化任务：** ${metadata.optimizationName}\n`
  if (metadata.projectName) {
    md += `**所属项目：** ${metadata.projectName}\n`
  }
  if (metadata.routeName) {
    md += `**来源路线：** ${metadata.routeName}\n`
  }
  md += `\n`
  return md
}

/**
 * 生成DOE实验报告章节
 */
export function generateDOESection(doeExperiment?: DOEExperiment): string {
  let md = `## 一、DOE实验设计与分析\n\n`
  
  if (!doeExperiment) {
    md += `未进行DOE实验\n\n`
    return md
  }

  md += `### 1.1 实验设计\n\n`
  md += `- 设计类型：${doeExperiment.design_type === 'orthogonal' ? '正交设计' : '响应面法'}\n`
  md += `- 因素数：${doeExperiment.factors.length}\n`
  md += `- 实验组数：${doeExperiment.runs.length}\n`
  md += `- 完成组数：${doeExperiment.runs.filter(r => r.status === 'completed').length}\n\n`

  md += `### 1.2 因素设置\n\n`
  md += `| 因素 | 符号 | 范围 | 单位 |\n`
  md += `|------|------|------|------|\n`
  doeExperiment.factors.forEach(f => {
    const bounds = f.levels as { lower: number; upper: number }
    md += `| ${f.name} | ${f.symbol} | ${bounds.lower}~${bounds.upper} | ${f.unit || '-'} |\n`
  })
  md += `\n`

  if (doeExperiment.analysis_result) {
    md += `### 1.3 优化结果\n\n`
    md += `- R² = ${doeExperiment.analysis_result.r_squared.toFixed(3)}\n`
    md += `- 调整R² = ${doeExperiment.analysis_result.adjusted_r_squared.toFixed(3)}\n`
    md += `- 显著因素：${doeExperiment.analysis_result.significant_factors.join('、') || '无'}\n\n`
    
    md += `**最优工艺参数：**\n\n`
    doeExperiment.factors.forEach(f => {
      const opt = doeExperiment.analysis_result!.optimal_conditions[f.symbol]
      if (opt != null) {
        md += `- ${f.name}(${f.symbol})：${opt} ${f.unit || ''}\n`
      }
    })
    md += `\n`

    // CPP评估
    if (doeExperiment.analysis_result.cpp_assessment) {
      md += `### 1.4 关键工艺参数（CPP）评估\n\n`
      md += `**关键工艺参数：** ${doeExperiment.analysis_result.cpp_assessment.critical_parameters.join('、')}\n\n`
      
      md += `**控制范围：**\n\n`
      Object.entries(doeExperiment.analysis_result.cpp_assessment.control_ranges).forEach(([symbol, range]) => {
        const factor = doeExperiment.factors.find(f => f.symbol === symbol)
        md += `- ${factor?.name || symbol}(${symbol})：${range.min.toFixed(2)} ~ ${range.max.toFixed(2)} ${range.unit || ''}\n`
      })
      md += `\n`
      
      md += `**评估说明：** ${doeExperiment.analysis_result.cpp_assessment.justification}\n\n`
    }
  }

  if (doeExperiment.conclusion) {
    md += `**结论：** ${doeExperiment.conclusion}\n\n`
  }

  return md
}

/**
 * 生成杂质研究报告章节
 */
export function generateImpuritySection(impurityStudy?: ImpurityStudy): string {
  let md = `## 二、杂质研究\n\n`
  
  if (!impurityStudy) {
    md += `未进行杂质研究\n\n`
    return md
  }

  md += `共识别 ${impurityStudy.impurities.length} 种杂质\n\n`
  md += `| 杂质名称 | 类别 | 来源 | 限度(ppm) | 风险 |\n`
  md += `|----------|------|------|-----------|------|\n`
  
  const catMap: Record<string, string> = { 
    process: '工艺杂质', 
    degradation: '降解杂质', 
    residual_solvent: '残留溶剂', 
    elemental: '元素杂质', 
    genotoxic: '基因毒性' 
  }
  
  impurityStudy.impurities.forEach(i => {
    md += `| ${i.name} | ${catMap[i.category] || i.category} | ${i.source} | ${i.limit_ppm || '-'} | ${i.risk_level} |\n`
  })
  md += `\n`
  
  if (impurityStudy.control_strategy_summary) {
    md += `**控制策略：** ${impurityStudy.control_strategy_summary}\n\n`
  }

  return md
}

/**
 * 生成晶型研究报告章节
 */
export function generateCrystalFormSection(crystalFormStudy?: CrystalFormStudy): string {
  let md = `## 三、晶型研究\n\n`
  
  if (!crystalFormStudy) {
    md += `未进行晶型研究\n\n`
    return md
  }

  md += `共筛选 ${crystalFormStudy.records.length} 种晶型/盐型\n\n`
  md += `| 晶型名称 | 类型 | 溶剂体系 | 结晶方法 | 推荐 |\n`
  md += `|----------|------|----------|----------|------|\n`
  
  const typeMap: Record<string, string> = { 
    polymorph: '多晶型', 
    hydrate: '水合物', 
    solvate: '溶剂化物', 
    salt: '盐型', 
    amorphous: '无定形' 
  }
  
  crystalFormStudy.records.forEach(r => {
    md += `| ${r.form_name} | ${typeMap[r.form_type] || r.form_type} | ${r.solvent_system} | ${r.crystallization_method} | ${r.is_preferred ? '✓' : ''} |\n`
  })
  md += `\n`
  
  if (crystalFormStudy.preferred_form) {
    md += `**推荐晶型：** ${crystalFormStudy.preferred_form.form_name}\n\n`
  }

  return md
}

/**
 * 生成质量标准报告章节
 */
export function generateQualityStandardSection(qualityStandardSet?: QualityStandardSet): string {
  let md = `## 四、质量标准\n\n`
  
  if (!qualityStandardSet) {
    md += `未建立质量标准\n\n`
    return md
  }

  md += `共制定 ${qualityStandardSet.standards.length} 项检测指标\n\n`
  md += `| 序号 | 检测项目 | 检测方法 | 标准 |\n`
  md += `|------|----------|----------|------|\n`
  
  qualityStandardSet.standards.forEach((s, i) => {
    md += `| ${i + 1} | ${s.test_item} | ${s.test_method} | ${s.specification} |\n`
  })
  md += `\n`
  
  if (qualityStandardSet.shelf_life_proposal) {
    md += `- **拟定有效期：** ${qualityStandardSet.shelf_life_proposal}\n`
  }
  if (qualityStandardSet.storage_condition) {
    md += `- **贮藏条件：** ${qualityStandardSet.storage_condition}\n`
  }
  if (qualityStandardSet.packaging) {
    md += `- **包装方式：** ${qualityStandardSet.packaging}\n`
  }
  md += `\n`

  return md
}

/**
 * 生成小试确认报告章节
 */
export function generateLabConfirmationSection(labConfirmationStudy?: LabConfirmationStudy): string {
  let md = `## 五、小试工艺确认\n\n`
  
  if (!labConfirmationStudy) {
    md += `未进行小试工艺确认\n\n`
    return md
  }

  md += `### 5.1 确认目的\n\n`
  md += `${labConfirmationStudy.purpose}\n\n`
  
  md += `### 5.2 确认批信息\n\n`
  md += `- 批号：${labConfirmationStudy.batch.batch_no}\n`
  md += `- 规模：${labConfirmationStudy.batch.scale_g} g\n`
  md += `- 日期：${labConfirmationStudy.batch.date}\n`
  md += `- 操作人：${labConfirmationStudy.batch.operator}\n`
  md += `- 设备：${labConfirmationStudy.batch.equipment}\n\n`
  
  md += `### 5.3 工艺参数\n\n`
  const params = labConfirmationStudy.batch.parameters
  if (params.temperature) md += `- 反应温度：${params.temperature}\n`
  if (params.time) md += `- 反应时间：${params.time}\n`
  if (params.ratio) md += `- 投料比例：${params.ratio}\n`
  if (params.other) md += `- 其他参数：${params.other}\n`
  md += `\n`
  
  md += `### 5.4 质量结果\n\n`
  md += `- 收率：${labConfirmationStudy.batch.yield_pct}%\n`
  md += `- 纯度：${labConfirmationStudy.batch.purity_pct}%\n`
  md += `- 杂质：${labConfirmationStudy.batch.impurities_pct}%\n`
  md += `- 外观：${labConfirmationStudy.batch.appearance}\n\n`
  
  md += `**确认结论：** ${labConfirmationStudy.conclusion}\n\n`

  return md
}

/**
 * 生成公斤级放大报告章节
 */
export function generateScaleUpSection(scaleUpStudy?: ScaleUpStudy): string {
  let md = `## 六、公斤级放大试验\n\n`
  
  if (!scaleUpStudy) {
    md += `未进行公斤级放大\n\n`
    return md
  }

  md += `- **目标规模：** ${scaleUpStudy.target_scale_kg} kg\n`
  md += `- **完成批数：** ${scaleUpStudy.batch ? 1 : 0}\n\n`
  
  if (scaleUpStudy.batch) {
    md += `| 批号 | 规模(kg) | 收率(%) | 纯度(%) | 状态 |\n`
    md += `|------|----------|---------|---------|------|\n`
    md += `| ${scaleUpStudy.batch.batch_no} | ${scaleUpStudy.batch.scale_kg} | ${scaleUpStudy.batch.yield_pct} | ${scaleUpStudy.batch.purity_pct} | ${scaleUpStudy.batch.status} |\n`
    md += `\n`
  }
  
  if (scaleUpStudy.comparison_summary) {
    md += `**与小试对比：** ${scaleUpStudy.comparison_summary}\n\n`
  }
  
  if (scaleUpStudy.conclusion) {
    md += `**结论：** ${scaleUpStudy.conclusion}\n\n`
  }

  return md
}

/**
 * 生成完整报告
 */
export function generateFullReport(
  metadata: ReportMetadata,
  data: {
    doeExperiment?: DOEExperiment
    impurityStudy?: ImpurityStudy
    crystalFormStudy?: CrystalFormStudy
    qualityStandardSet?: QualityStandardSet
    labConfirmationStudy?: LabConfirmationStudy
    scaleUpStudy?: ScaleUpStudy
  }
): string {
  let md = generateReportHeader(metadata)
  md += generateDOESection(data.doeExperiment)
  md += generateImpuritySection(data.impurityStudy)
  md += generateCrystalFormSection(data.crystalFormStudy)
  md += generateQualityStandardSection(data.qualityStandardSet)
  md += generateLabConfirmationSection(data.labConfirmationStudy)
  md += generateScaleUpSection(data.scaleUpStudy)
  
  md += `---\n\n`
  md += `**报告生成时间：** ${metadata.reportTime}\n`
  
  return md
}
