import { redirect } from 'next/navigation'

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams
  const query = new URLSearchParams()
  for (const key of ['year', 'month', 'dataset']) {
    const value = params[key]
    if (typeof value === 'string') query.set(key, value)
  }
  if (typeof params.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(params.date)) {
    query.set('year', params.date.slice(0, 4)); query.set('month', String(Number(params.date.slice(5, 7))))
  }
  redirect(`/energy/reports${query.size ? `?${query}` : ''}`)
}
