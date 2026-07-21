/**
 * 杂质自动识别引擎
 * 基于工艺路线、反应条件、DOE 数据推导可能的杂质
 */

import type { Impurity, ImpurityCategory, ICHM7Class, ICHSolventClass, ControlMethod } from '@/types/rd'
import type { RouteDevelopment, ExperimentPlan, ExperimentRecord } from '@/types/rd'
import type { DOEExperiment, DOEFactor } from '@/types/rd'

// 常见溶剂及其 ICH 分类
const SOLVENT_DATABASE: Record<string, { class: ICHSolventClass; limit_ppm: number; risk: 'low' | 'medium' | 'high' }> = {
  '二氯甲烷': { class: 'class2', limit_ppm: 600, risk: 'medium' },
  'dcm': { class: 'class2', limit_ppm: 600, risk: 'medium' },
  '氯仿': { class: 'class2', limit_ppm: 60, risk: 'high' },
  '甲醇': { class: 'class2', limit_ppm: 3000, risk: 'medium' },
  '乙醇': { class: 'class3', limit_ppm: 5000, risk: 'low' },
  '异丙醇': { class: 'class3', limit_ppm: 5000, risk: 'low' },
  '丙酮': { class: 'class3', limit_ppm: 5000, risk: 'low' },
  '乙酸乙酯': { class: 'class3', limit_ppm: 5000, risk: 'low' },
  '甲苯': { class: 'class2', limit_ppm: 890, risk: 'medium' },
  '苯': { class: 'class1', limit_ppm: 2, risk: 'high' },
  '正己烷': { class: 'class2', limit_ppm: 290, risk: 'medium' },
  '吡啶': { class: 'class2', limit_ppm: 200, risk: 'medium' },
  'dmf': { class: 'class2', limit_ppm: 880, risk: 'medium' },
  '二甲基甲酰胺': { class: 'class2', limit_ppm: 880, risk: 'medium' },
  'thf': { class: 'class2', limit_ppm: 720, risk: 'medium' },
  '四氢呋喃': { class: 'class2', limit_ppm: 720, risk: 'medium' },
  '乙腈': { class: 'class2', limit_ppm: 410, risk: 'medium' },
  '水': { class: 'class3', limit_ppm: 10000, risk: 'low' },
}

// 常见试剂及其残留风险
const REAGENT_DATABASE: Record<string, { risk: 'low' | 'medium' | 'high'; category: ImpurityCategory }> = {
  'socl2': { risk: 'high', category: 'genotoxic' },
  '二氯亚砜': { risk: 'high', category: 'genotoxic' },
  'oxalyl chloride': { risk: 'high', category: 'genotoxic' },
  '草酰氯': { risk: 'high', category: 'genotoxic' },
  'pocl3': { risk: 'high', category: 'genotoxic' },
  '三氯氧磷': { risk: 'high', category: 'genotoxic' },
  'methanesulfonyl chloride': { risk: 'medium', category: 'genotoxic' },
  '甲磺酰氯': { risk: 'medium', category: 'genotoxic' },
  'tosyl chloride': { risk: 'medium', category: 'genotoxic' },
  '对甲苯磺酰氯': { risk: 'medium', category: 'genotoxic' },
  'pd/c': { risk: 'low', category: 'elemental' },
  '钯碳': { risk: 'low', category: 'elemental' },
  'pd(oh)2': { risk: 'low', category: 'elemental' },
  '氢氧化钯': { risk: 'low', category: 'elemental' },
  'lis': { risk: 'low', category: 'elemental' },
  '正丁基锂': { risk: 'medium', category: 'process' },
  'nailh4': { risk: 'medium', category: 'process' },
  '氢化铝锂': { risk: 'medium', category: 'process' },
  'nah': { risk: 'medium', category: 'process' },
  '氢化钠': { risk: 'medium', category: 'process' },
}

// 反应类型与可能的副产物
const REACTION_BYPRODUCTS: Record<string, { name: string; source: string; risk: 'low' | 'medium' | 'high' }[]> = {
  '酰胺化': [
    { name: '未反应酸', source: '酰胺化反应不完全', risk: 'low' },
    { name: '未反应胺', source: '酰胺化反应不完全', risk: 'low' },
    { name: '酯副产物', source: '酸与溶剂反应', risk: 'medium' },
  ],
  '酯化': [
    { name: '未反应酸', source: '酯化反应不完全', risk: 'low' },
    { name: '未反应醇', source: '酯化反应不完全', risk: 'low' },
    { name: '醚副产物', source: '醇脱水副反应', risk: 'medium' },
  ],
  '取代': [
    { name: '脱卤副产物', source: '取代反应不完全', risk: 'medium' },
    { name: '多取代产物', source: '过度反应', risk: 'medium' },
  ],
  '氧化': [
    { name: '过度氧化产物', source: '氧化反应控制不当', risk: 'high' },
    { name: '环氧化物', source: '氧化副反应', risk: 'high' },
  ],
  '还原': [
    { name: '过度还原产物', source: '还原反应控制不当', risk: 'medium' },
    { name: '部分还原中间体', source: '还原不完全', risk: 'low' },
  ],
  '水解': [
    { name: '开环产物', source: '水解副反应', risk: 'medium' },
    { name: '降解产物', source: '过度水解', risk: 'medium' },
  ],
}

interface ImpurityIdentificationInput {
  route?: RouteDevelopment
  doeExperiment?: DOEExperiment
}

/**
 * 从溶剂名称中提取标准名称
 */
function normalizeSolventName(solvent: string): string | null {
  const lower = solvent.toLowerCase().trim()
  if (SOLVENT_DATABASE[lower]) return lower
  if (SOLVENT_DATABASE[solvent]) return solvent
  
  // 尝试部分匹配
  for (const key of Object.keys(SOLVENT_DATABASE)) {
    if (lower.includes(key) || key.includes(lower)) {
      return key
    }
  }
  return null
}

/**
 * 从试剂名称中提取标准名称
 */
function normalizeReagentName(reagent: string): string | null {
  const lower = reagent.toLowerCase().trim()
  if (REAGENT_DATABASE[lower]) return lower
  if (REAGENT_DATABASE[reagent]) return reagent
  
  // 尝试部分匹配
  for (const key of Object.keys(REAGENT_DATABASE)) {
    if (lower.includes(key) || key.includes(lower)) {
      return key
    }
  }
  return null
}

/**
 * 从反应条件中提取溶剂
 */
function extractSolventsFromConditions(conditions: string): string[] {
  const solvents: string[] = []
  const solventKeywords = ['溶剂', 'solvent', '萃取', '洗涤', '重结晶', '溶解']
  
  for (const keyword of solventKeywords) {
    if (conditions.toLowerCase().includes(keyword)) {
      // 尝试提取溶剂名称
      for (const solvent of Object.keys(SOLVENT_DATABASE)) {
        if (conditions.toLowerCase().includes(solvent)) {
          solvents.push(solvent)
        }
      }
    }
  }
  
  // 直接匹配已知溶剂
  for (const solvent of Object.keys(SOLVENT_DATABASE)) {
    if (conditions.toLowerCase().includes(solvent) && !solvents.includes(solvent)) {
      solvents.push(solvent)
    }
  }
  
  return [...new Set(solvents)]
}

/**
 * 从反应步骤描述中推断反应类型
 */
function inferReactionType(description: string): string[] {
  const types: string[] = []
  const lower = description.toLowerCase()
  
  if (lower.includes('酰胺') || lower.includes('amide') || lower.includes('缩合')) {
    types.push('酰胺化')
  }
  if (lower.includes('酯') || lower.includes('ester')) {
    types.push('酯化')
  }
  if (lower.includes('取代') || lower.includes('卤化') || lower.includes('烷基化')) {
    types.push('取代')
  }
  if (lower.includes('氧化') || lower.includes('oxidation')) {
    types.push('氧化')
  }
  if (lower.includes('还原') || lower.includes('reduction') || lower.includes('加氢')) {
    types.push('还原')
  }
  if (lower.includes('水解') || lower.includes('hydrolysis')) {
    types.push('水解')
  }
  
  return types
}

/**
 * 从工艺路线识别残留溶剂
 */
function identifyResidualSolvents(route: RouteDevelopment): Impurity[] {
  const impurities: Impurity[] = []
  const identifiedSolvents = new Set<string>()
  
  // 从实验方案中提取溶剂
  for (const plan of route.experiment_plans || []) {
    for (const step of plan.steps || []) {
      const solvents = extractSolventsFromConditions(step.conditions)
      for (const solvent of solvents) {
        const normalized = normalizeSolventName(solvent)
        if (normalized && !identifiedSolvents.has(normalized)) {
          identifiedSolvents.add(normalized)
          const info = SOLVENT_DATABASE[normalized]
          impurities.push({
            id: `imp-solvent-${impurities.length + 1}`,
            name: normalized,
            category: 'residual_solvent',
            source: '反应溶剂残留',
            ich_solvent_class: info.class,
            limit_ppm: info.limit_ppm,
            typical_level_pct: 0.01,
            control_method: 'release_test',
            detection_method: 'GC',
            risk_level: info.risk,
          })
        }
      }
      
      // 从试剂列表中提取溶剂
      for (const reagent of step.reagents || []) {
        const normalized = normalizeSolventName(reagent)
        if (normalized && !identifiedSolvents.has(normalized)) {
          identifiedSolvents.add(normalized)
          const info = SOLVENT_DATABASE[normalized]
          impurities.push({
            id: `imp-solvent-${impurities.length + 1}`,
            name: normalized,
            category: 'residual_solvent',
            source: '试剂/溶剂残留',
            ich_solvent_class: info.class,
            limit_ppm: info.limit_ppm,
            typical_level_pct: 0.01,
            control_method: 'release_test',
            detection_method: 'GC',
            risk_level: info.risk,
          })
        }
      }
    }
  }
  
  return impurities
}

/**
 * 从工艺路线识别工艺杂质
 */
function identifyProcessImpurities(route: RouteDevelopment): Impurity[] {
  const impurities: Impurity[] = []
  const identifiedReagents = new Set<string>()
  
  // 从实验方案中提取高风险试剂
  for (const plan of route.experiment_plans || []) {
    for (const step of plan.steps || []) {
      for (const reagent of step.reagents || []) {
        const normalized = normalizeReagentName(reagent)
        if (normalized && !identifiedReagents.has(normalized)) {
          identifiedReagents.add(normalized)
          const info = REAGENT_DATABASE[normalized]
          if (info.risk === 'high' || info.risk === 'medium') {
            impurities.push({
              id: `imp-reagent-${impurities.length + 1}`,
              name: `${normalized}残留`,
              category: info.category,
              source: `${normalized}未完全消耗`,
              limit_ppm: info.category === 'genotoxic' ? 1.5 : 500,
              typical_level_pct: 0.005,
              control_method: info.category === 'genotoxic' ? 'both' : 'release_test',
              detection_method: info.category === 'genotoxic' ? 'LC-MS' : 'HPLC',
              risk_level: info.risk,
              ich_m7_class: info.category === 'genotoxic' ? 'class2' : undefined,
            })
          }
        }
      }
    }
  }
  
  return impurities
}

/**
 * 从反应类型推导副产物
 */
function identifyByproducts(route: RouteDevelopment): Impurity[] {
  const impurities: Impurity[] = []
  const identifiedByproducts = new Set<string>()
  
  for (const plan of route.experiment_plans || []) {
    for (const step of plan.steps || []) {
      const reactionTypes = inferReactionType(step.description)
      
      for (const type of reactionTypes) {
        const byproducts = REACTION_BYPRODUCTS[type] || []
        for (const bp of byproducts) {
          if (!identifiedByproducts.has(bp.name)) {
            identifiedByproducts.add(bp.name)
            impurities.push({
              id: `imp-byproduct-${impurities.length + 1}`,
              name: bp.name,
              category: 'process',
              source: bp.source,
              typical_level_pct: 0.05,
              limit_ppm: bp.risk === 'high' ? 1000 : 3000,
              control_method: 'process_control',
              detection_method: 'HPLC',
              risk_level: bp.risk,
            })
          }
        }
      }
    }
  }
  
  return impurities
}

/**
 * 从历史实验记录中提取已报告的杂质
 */
function identifyFromExperimentRecords(route: RouteDevelopment): Impurity[] {
  const impurities: Impurity[] = []
  const identified = new Set<string>()
  
  for (const exp of route.experiments || []) {
    if (exp.impurities && exp.impurities.trim()) {
      // 简单解析杂质描述（假设格式为 "杂质名: 百分比" 或逗号分隔）
      const parts = exp.impurities.split(/[,，;；]/).map(s => s.trim()).filter(Boolean)
      
      for (const part of parts) {
        const match = part.match(/(.+?)[：:]\s*([\d.]+)\s*%?/)
        if (match) {
          const name = match[1].trim()
          const level = parseFloat(match[2])
          
          if (!identified.has(name)) {
            identified.add(name)
            impurities.push({
              id: `imp-exp-${impurities.length + 1}`,
              name,
              category: 'process',
              source: '历史实验记录',
              typical_level_pct: level,
              limit_ppm: level > 0.1 ? 3000 : 1000,
              control_method: 'process_control',
              detection_method: 'HPLC',
              risk_level: level > 0.1 ? 'high' : level > 0.05 ? 'medium' : 'low',
            })
          }
        }
      }
    }
  }
  
  return impurities
}

/**
 * 从 DOE 因素推导潜在杂质
 */
function identifyFromDOE(doe: DOEExperiment): Impurity[] {
  const impurities: Impurity[] = []
  
  // 如果 DOE 中有温度、时间等因素，可能产生降解产物
  const hasTemperature = doe.factors.some(f => 
    f.name.toLowerCase().includes('温度') || 
    f.name.toLowerCase().includes('temperature')
  )
  
  const hasTime = doe.factors.some(f => 
    f.name.toLowerCase().includes('时间') || 
    f.name.toLowerCase().includes('time')
  )
  
  if (hasTemperature || hasTime) {
    impurities.push({
      id: 'imp-degradation-1',
      name: '热降解产物',
      category: 'degradation',
      source: '高温或长时间反应导致降解',
      typical_level_pct: 0.02,
      limit_ppm: 2000,
      control_method: 'process_control',
      detection_method: 'HPLC',
      risk_level: 'medium',
    })
  }
  
  return impurities
}

/**
 * 主函数：自动识别杂质
 */
export function identifyImpurities(input: ImpurityIdentificationInput): Impurity[] {
  const allImpurities: Impurity[] = []
  
  // 从工艺路线识别
  if (input.route) {
    allImpurities.push(...identifyResidualSolvents(input.route))
    allImpurities.push(...identifyProcessImpurities(input.route))
    allImpurities.push(...identifyByproducts(input.route))
    allImpurities.push(...identifyFromExperimentRecords(input.route))
  }
  
  // 从 DOE 识别
  if (input.doeExperiment) {
    allImpurities.push(...identifyFromDOE(input.doeExperiment))
  }
  
  // 去重（按名称）
  const uniqueImpurities = new Map<string, Impurity>()
  for (const imp of allImpurities) {
    const key = imp.name.toLowerCase()
    if (!uniqueImpurities.has(key)) {
      uniqueImpurities.set(key, imp)
    }
  }
  
  return Array.from(uniqueImpurities.values())
}

/**
 * 生成识别报告
 */
export function generateIdentificationReport(impurities: Impurity[]): string {
  const byCategory: Record<string, number> = {}
  const byRisk: Record<string, number> = {}
  
  for (const imp of impurities) {
    byCategory[imp.category] = (byCategory[imp.category] || 0) + 1
    byRisk[imp.risk_level] = (byRisk[imp.risk_level] || 0) + 1
  }
  
  const categoryLabels: Record<string, string> = {
    process: '工艺杂质',
    degradation: '降解杂质',
    residual_solvent: '残留溶剂',
    elemental: '元素杂质',
    genotoxic: '基因毒性杂质',
  }
  
  const riskLabels: Record<string, string> = {
    low: '低风险',
    medium: '中风险',
    high: '高风险',
  }
  
  let report = `自动识别完成，共识别 ${impurities.length} 种潜在杂质：\n\n`
  
  report += '按分类统计：\n'
  for (const [cat, count] of Object.entries(byCategory)) {
    report += `  - ${categoryLabels[cat] || cat}: ${count} 种\n`
  }
  
  report += '\n按风险等级：\n'
  for (const [risk, count] of Object.entries(byRisk)) {
    report += `  - ${riskLabels[risk] || risk}: ${count} 种\n`
  }
  
  return report
}
