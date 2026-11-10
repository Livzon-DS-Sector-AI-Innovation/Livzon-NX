export function reviewDetails(provenance: unknown) {
  if (!provenance || typeof provenance !== 'object' || !('review' in provenance) || !Array.isArray(provenance.review)) return []
  return provenance.review.flatMap((entry: unknown) => {
    if (!entry || typeof entry !== 'object' || !('reason' in entry) || typeof entry.reason !== 'string') return []
    return [{ reason: entry.reason,
      source: 'source' in entry && typeof entry.source === 'string' ? entry.source : '',
      reportedValue: 'reported_value' in entry && typeof entry.reported_value === 'string' ? entry.reported_value : null,
    }]
  })
}

export function sourceComparisonDetails(provenance: unknown) {
  if (!provenance || typeof provenance !== 'object' || !('source_comparison' in provenance)) return null
  const entry = provenance.source_comparison
  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return null
  const decimal = (value: unknown): value is string => typeof value === 'string' && /^[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value) && Number.isFinite(Number(value))
  if (!('reported_value' in entry) || !decimal(entry.reported_value)
    || !('difference' in entry) || (entry.difference !== null && !decimal(entry.difference))
    || !('calculation_status' in entry) || typeof entry.calculation_status !== 'string'
    || !('source' in entry) || typeof entry.source !== 'string') return null
  return { reportedValue: entry.reported_value, difference: entry.difference, calculationStatus: entry.calculation_status, source: entry.source }
}
