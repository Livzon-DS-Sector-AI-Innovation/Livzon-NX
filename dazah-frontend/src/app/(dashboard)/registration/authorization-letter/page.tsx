import { fetchAuthorizationLettersServer, fetchProductsServer } from '@/actions/registration'
import AuthorizationLetterClient from '@/components/registration/AuthorizationLetterClient'

export const dynamic = 'force-dynamic'

export default async function AuthorizationLetterPage() {
  const [lettersRes, productsRes] = await Promise.all([
    fetchAuthorizationLettersServer({ page: 1, page_size: 20 }),
    fetchProductsServer(),
  ])

  return (
    <AuthorizationLetterClient
      initialLetters={lettersRes?.data || []}
      initialTotal={lettersRes?.meta?.total || 0}
      products={productsRes || []}
    />
  )
}
