'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { revalidatePath } from 'next/cache'
import { AuthorizationLetterCreateInput } from '@/types/registration'

const API_BASE_URL = getServerApiBaseUrl()

async function actionFetch<T>(url: string, options?: RequestInit): Promise<T | null> {
  const response = await fetch(url, {
    ...options,
    headers: {
      // TODO: 添加认证头
      // Authorization: `Bearer ${await getServerToken()}`,
      ...options?.headers,
    },
  })
  if (!response.ok) {
    const errorBody = await response.text().catch(() => '')
    let errorMessage = `请求失败: ${response.status} ${response.statusText}`
    try {
      const errorJson = JSON.parse(errorBody)
      if (errorJson.message) errorMessage = errorJson.message
    } catch {}
    throw new Error(errorMessage)
  }
  const text = await response.text()
  if (!text) return null
  const json = JSON.parse(text)
  return json.data ?? json
}

export async function generateAuthorizationLetter(
  formData: FormData,
  data: AuthorizationLetterCreateInput
): Promise<{ success: boolean; message: string; data?: any }> {
  try {
    // 构建 multipart/form-data
    const submitData = new FormData()
    submitData.append('template', formData.get('template') as File)
    submitData.append('product_name', data.product_name)
    submitData.append('registration_number', data.registration_number)
    submitData.append('preparation_unit', data.preparation_unit)
    submitData.append('preparation_name', data.preparation_name)
    submitData.append('administration_route', data.administration_route)
    if (data.remarks) {
      submitData.append('remarks', data.remarks)
    }
    const replacements = formData.get('replacements')
    if (replacements) {
      submitData.append('replacements', replacements as string)
    }

    const response = await fetch(`${API_BASE_URL}/api/v1/registration/authorization-letters/generate`, {
      method: 'POST',
      body: submitData,
    })

    if (!response.ok) {
      const errorBody = await response.text().catch(() => '')
      let errorMessage = `请求失败: ${response.status} ${response.statusText}`
      try {
        const errorJson = JSON.parse(errorBody)
        if (errorJson.message) errorMessage = errorJson.message
      } catch {}
      throw new Error(errorMessage)
    }

    const json = await response.json()
    revalidatePath('/registration')
    return {
      success: true,
      message: json.message || '授权书生成成功',
      data: json.data,
    }
  } catch (error) {
    return {
      success: false,
      message: error instanceof Error ? error.message : '生成授权书失败',
    }
  }
}

export async function deleteAuthorizationLetter(id: string) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/registration/authorization-letters/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/registration')
  return result
}

export async function generateSupplementaryReply(
  formData: FormData,
  data: {
    drug_name?: string
    registration_number?: string
    acceptance_number?: string
    company_name?: string
    remarks?: string
  }
): Promise<{ success: boolean; message: string; data?: any }> {
  try {
    const submitData = new FormData()
    submitData.append('notice', formData.get('notice') as File)
    
    const template = formData.get('template')
    if (template) {
      submitData.append('template', template as File)
    }
    
    if (data.drug_name) submitData.append('drug_name', data.drug_name)
    if (data.registration_number) submitData.append('registration_number', data.registration_number)
    if (data.acceptance_number) submitData.append('acceptance_number', data.acceptance_number)
    if (data.company_name) submitData.append('company_name', data.company_name)
    if (data.remarks) submitData.append('remarks', data.remarks)

    const response = await fetch(`${API_BASE_URL}/api/v1/registration/supplementary-replies/generate`, {
      method: 'POST',
      body: submitData,
    })

    if (!response.ok) {
      const errorBody = await response.text().catch(() => '')
      let errorMessage = `请求失败: ${response.status} ${response.statusText}`
      try {
        const errorJson = JSON.parse(errorBody)
        if (errorJson.message) errorMessage = errorJson.message
      } catch {}
      throw new Error(errorMessage)
    }

    const json = await response.json()
    revalidatePath('/registration')
    return {
      success: true,
      message: json.message || '发补回复文档生成成功',
      data: json.data,
    }
  } catch (error) {
    return {
      success: false,
      message: error instanceof Error ? error.message : '生成发补回复文档失败',
    }
  }
}

export async function deleteSupplementaryReplyAction(id: string) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/registration/supplementary-replies/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/registration')
  return result
}

export async function generateReferenceStandard(
  formData: FormData,
  data: {
    drug_name: string
    reference_substance_name?: string
    batch_number?: string
    manufacturer?: string
    english_name?: string
    molecular_formula?: string
    molecular_weight?: string
    cas_number?: string
    content?: string
    moisture?: string
    rsd?: string
    expiration_date?: string
    storage_condition?: string
    remarks?: string
  }
): Promise<{ success: boolean; message: string; data?: any }> {
  try {
    const submitData = new FormData()
    submitData.append('coa', formData.get('coa') as File)
    submitData.append('drug_name', data.drug_name)
    
    if (data.reference_substance_name) submitData.append('reference_substance_name', data.reference_substance_name)
    if (data.batch_number) submitData.append('batch_number', data.batch_number)
    if (data.manufacturer) submitData.append('manufacturer', data.manufacturer)
    if (data.english_name) submitData.append('english_name', data.english_name)
    if (data.molecular_formula) submitData.append('molecular_formula', data.molecular_formula)
    if (data.molecular_weight) submitData.append('molecular_weight', data.molecular_weight)
    if (data.cas_number) submitData.append('cas_number', data.cas_number)
    if (data.content) submitData.append('content', data.content)
    if (data.moisture) submitData.append('moisture', data.moisture)
    if (data.rsd) submitData.append('rsd', data.rsd)
    if (data.expiration_date) submitData.append('expiration_date', data.expiration_date)
    if (data.storage_condition) submitData.append('storage_condition', data.storage_condition)
    if (data.remarks) submitData.append('remarks', data.remarks)

    const response = await fetch(`${API_BASE_URL}/api/v1/registration/reference-standards/generate`, {
      method: 'POST',
      body: submitData,
    })

    if (!response.ok) {
      const errorBody = await response.text().catch(() => '')
      let errorMessage = `请求失败: ${response.status} ${response.statusText}`
      try {
        const errorJson = JSON.parse(errorBody)
        if (errorJson.message) errorMessage = errorJson.message
      } catch {}
      throw new Error(errorMessage)
    }

    const json = await response.json()
    revalidatePath('/registration')
    return {
      success: true,
      message: json.message || '对照物质说明表生成成功',
      data: json.data,
    }
  } catch (error) {
    return {
      success: false,
      message: error instanceof Error ? error.message : '生成对照物质说明表失败',
    }
  }
}

export async function deleteReferenceStandardAction(id: string) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/registration/reference-standards/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/registration')
  return result
}

export async function fetchAuthorizationLettersServer(params: { page: number; page_size: number }) {
  const searchParams = new URLSearchParams({
    page: params.page.toString(),
    page_size: params.page_size.toString(),
  })
  const result = await actionFetch<any>(
    `${API_BASE_URL}/api/v1/registration/authorization-letters?${searchParams.toString()}`
  )
  return result
}

export async function fetchProductsServer() {
  const result = await actionFetch<any>(
    `${API_BASE_URL}/api/v1/registration/authorization-letters/products`
  )
  return result
}

export async function fetchReferenceStandardsServer(params: { page: number; page_size: number }) {
  const searchParams = new URLSearchParams({
    page: params.page.toString(),
    page_size: params.page_size.toString(),
  })
  const result = await actionFetch<any>(
    `${API_BASE_URL}/api/v1/registration/reference-standards?${searchParams.toString()}`
  )
  return result
}

export async function fetchSupplementaryRepliesServer(params: { page: number; page_size: number }) {
  const searchParams = new URLSearchParams({
    page: params.page.toString(),
    page_size: params.page_size.toString(),
  })
  const result = await actionFetch<any>(
    `${API_BASE_URL}/api/v1/registration/supplementary-replies?${searchParams.toString()}`
  )
  return result
}
