import type { LLMConfigFormData } from '@/actions/settings'

export interface LLMConfigFormValues extends LLMConfigFormData {
  use_temperature: boolean
}

export function getNewLLMConfigFormValues(): Partial<LLMConfigFormValues> {
  return {
    temperature: 0.1,
    use_temperature: false,
    timeout_seconds: 120,
    is_active: true,
  }
}

export function buildLLMConfigPayload(
  values: LLMConfigFormValues,
): LLMConfigFormData {
  const { use_temperature: useTemperature, ...payload } = values
  return {
    ...payload,
    temperature: useTemperature ? values.temperature : 0,
  }
}
