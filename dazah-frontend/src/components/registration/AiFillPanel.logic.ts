export function getAiFillErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

export function countFilledResults(
  results: readonly { status: string }[],
): number {
  return results.filter((result) => result.status === 'filled').length
}

export function getTableColumnCount(value: unknown): number {
  return Array.isArray(value) && Array.isArray(value[0]) ? value[0].length : 0
}
