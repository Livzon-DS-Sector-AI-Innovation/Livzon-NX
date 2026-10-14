import type { DOEFactor, DOEResponse, DOERun } from '@/types/rd'

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

export function completeMeasuredRuns(factors: DOEFactor[], responses: DOEResponse[], runs: DOERun[]): DOERun[] {
  if (!factors.length || !responses.length) return []
  return runs.filter((run) => run.status === 'completed'
    && factors.every((factor) => factor.type === 'numeric'
      ? finite(run.factor_values[factor.symbol])
      : typeof run.factor_values[factor.symbol] === 'string' && String(run.factor_values[factor.symbol]).trim().length > 0)
    && responses.every((response) => finite(run.response_values[response.name])))
}

/** Plot recorded observations only; never interpolate or infer an optimum. */
export function buildMeasuredDOEOption(factors: DOEFactor[], responses: DOEResponse[], runs: DOERun[], responseName?: string) {
  const numeric = factors.filter((factor) => factor.type === 'numeric').slice(0, 2)
  const response = responses.find((item) => item.name === responseName) ?? responses[0]
  if (numeric.length !== 2 || !response) return null
  const [x, y] = numeric
  const data = runs.filter((run) => run.status === 'completed'
    && finite(run.factor_values[x.symbol]) && finite(run.factor_values[y.symbol])
    && finite(run.response_values[response.name]))
    .map((run) => ({ name: `实验 ${run.run_no}`, value: [run.factor_values[x.symbol], run.factor_values[y.symbol], run.response_values[response.name]] }))
  if (!data.length) return null
  const label = (name: string, unit?: string) => unit ? `${name}（${unit}）` : name
  return {
    tooltip: { formatter: '{b}: {c}' },
    xAxis3D: { type: 'value', name: label(x.name, x.unit) },
    yAxis3D: { type: 'value', name: label(y.name, y.unit) },
    zAxis3D: { type: 'value', name: label(response.name, response.unit) },
    grid3D: { viewControl: { projection: 'perspective' } },
    series: [{ name: '实测实验点', type: 'scatter3D', symbolSize: 12, itemStyle: { color: '#5645d4' }, data }],
  }
}
