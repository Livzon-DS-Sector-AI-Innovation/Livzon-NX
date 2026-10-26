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
