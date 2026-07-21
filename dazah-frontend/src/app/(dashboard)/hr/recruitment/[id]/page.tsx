import { fetchCandidateById } from '@/actions/hr'
import CandidateDetailClient from '@/components/hr/CandidateDetailClient'

export const dynamic = 'force-dynamic'

interface CandidateDetailPageProps {
  params: Promise<{ id: string }>
}

export default async function CandidateDetailPage({ params }: CandidateDetailPageProps) {
  const { id } = await params
  const res = await fetchCandidateById(id)

  return <CandidateDetailClient candidate={res.data} />
}
