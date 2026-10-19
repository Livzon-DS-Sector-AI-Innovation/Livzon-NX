import dayjs from 'dayjs'

export function resolveMonth(params: URLSearchParams) {
  const legacy = params.get('start_date')?.match(/^(\d{4})-(\d{2})-\d{2}$/)
  const year = Number(params.get('year') || legacy?.[1] || dayjs().year())
  const month = Number(params.get('month') || legacy?.[2] || dayjs().month() + 1)
  return { year: Number.isInteger(year) && year >= 2000 && year <= 2100 ? year : dayjs().year(), month: Number.isInteger(month) && month >= 1 && month <= 12 ? month : dayjs().month() + 1 }
}

export function monthPeriod(year: number, month: number) {
  const start = dayjs(`${year}-${String(month).padStart(2, '0')}-01`)
  return { start: start.format('YYYY-MM-DD'), end: start.endOf('month').format('YYYY-MM-DD'), previousStart: start.subtract(1, 'month').format('YYYY-MM-DD'), previousEnd: start.subtract(1, 'month').endOf('month').format('YYYY-MM-DD'), yearStart: start.subtract(1, 'year').format('YYYY-MM-DD'), yearEnd: start.subtract(1, 'year').endOf('month').format('YYYY-MM-DD') }
}
