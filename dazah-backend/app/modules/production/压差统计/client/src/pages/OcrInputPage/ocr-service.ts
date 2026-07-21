import { ocrImageFile } from '@/api';
import { logger } from '@lark-apaas/client-toolkit/logger';

export interface PressureOcrResult {
  pointId: string;
  pressureValue: number;
  recordTime: string;
  recorder: string;
  timeSlot: string;
}

export async function recognizePressureImage(
  file: File,
): Promise<PressureOcrResult[]> {
  try {
    const data = await ocrImageFile(file);
    if (!data.result || data.result.length === 0) {
      throw new Error('识别结果为空');
    }
    return data.result as unknown as PressureOcrResult[];
  } catch (err: unknown) {
    const error = err as { message?: string };
    logger.error('OCR识别失败', err);
    throw new Error(error.message || '识别失败');
  }
}
