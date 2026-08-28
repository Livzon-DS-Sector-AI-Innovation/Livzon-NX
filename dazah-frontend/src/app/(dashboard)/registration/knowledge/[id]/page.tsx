import { fetchKnowledgeArticleDetailServer } from '@/lib/api/server/registration'
import { KnowledgeArticleDetail } from '@/components/registration'

export const dynamic = 'force-dynamic'

interface Props {
  params: Promise<{ id: string }>
}

export default async function ArticleDetailPage({ params }: Props) {
  const { id } = await params
  const article = await fetchKnowledgeArticleDetailServer(id)

  return <KnowledgeArticleDetail article={article} />
}
