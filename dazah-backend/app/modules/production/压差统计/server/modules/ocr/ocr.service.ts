import { Injectable, Logger } from '@nestjs/common';
import { createWorker, type Worker } from 'tesseract.js';

export interface PressureOcrResult {
  pointId: string;
  pressureValue: number;
  recordTime: string;
  recorder: string;
  timeSlot: string;
}

const POINT_ID_RE = /[Pp][Dd][-. ]?\d{1,3}[-. ]?\d{2,4}/;
const PURE_NUMBER_RE = /^\d{2,4}$/;
const TIME_RE = /\d{1,2}:\d{2}(?::\d{2})?/;
const HEADER_TIME_RE = /^(\d{1,2})\s*[:：.]\s*(\d{2})/;
const TIME_SLOT_KEYWORDS = [
  '班次', '时段', '时间', '次', '第',
  '早班', '中班', '晚班', '上午', '下午',
];

function formatPointId(raw: string): string {
  return raw.toUpperCase().replace(/[ ]/g, '-');
}

function isHeaderLine(text: string): boolean {
  let headerIndicators = 0;
  const parts = text.split(/\s+/);
  for (const part of parts) {
    if (
      HEADER_TIME_RE.test(part) ||
      TIME_SLOT_KEYWORDS.some((kw: string) => part.includes(kw))
    ) {
      headerIndicators++;
    }
  }
  return headerIndicators >= 2;
}

function extractTimeSlotLabels(text: string): string[] {
  const labels: string[] = [];
  const parts = text.split(/\s+/);
  for (const part of parts) {
    const match = part.match(HEADER_TIME_RE);
    if (match) {
      const h = match[1].padStart(2, '0');
      const m = match[2];
      labels.push(`${h}:${m}`);
    } else if (part.length > 0 && !POINT_ID_RE.test(part)) {
      const cleaned = part.replace(/[|│┃¦]/g, '').trim();
      if (cleaned.length >= 1 && cleaned.length <= 10) {
        labels.push(cleaned);
      }
    }
  }
  return labels;
}

function parseOcrText(text: string): PressureOcrResult[] {
  const lines = text.split('\n').map((l: string) => l.trim()).filter((l: string) => l.length > 0);
  if (lines.length === 0) return [];

  let timeSlotLabels: string[] = [];
  let dataStartIdx = 0;

  for (let i = 0; i < Math.min(lines.length, 3); i++) {
    if (isHeaderLine(lines[i])) {
      timeSlotLabels = extractTimeSlotLabels(lines[i]);
      dataStartIdx = i + 1;
      break;
    }
  }

  const records: PressureOcrResult[] = [];
  let pendingPointId = '';
  const pendingValues: number[] = [];
  let pendingTime = '';
  let pendingRecorder = '';

  const flushPending = () => {
    if (!pendingPointId) return;
    if (pendingValues.length > 0) {
      for (let i = 0; i < pendingValues.length; i++) {
        records.push({
          pointId: pendingPointId,
          pressureValue: pendingValues[i],
          recordTime: pendingTime,
          recorder: pendingRecorder,
          timeSlot: timeSlotLabels[i] ?? `第${i + 1}次`,
        });
      }
    } else {
      records.push({
        pointId: pendingPointId,
        pressureValue: 0,
        recordTime: pendingTime,
        recorder: pendingRecorder,
        timeSlot: '',
      });
    }
    pendingPointId = '';
    pendingValues.length = 0;
    pendingTime = '';
    pendingRecorder = '';
  };

  for (let i = dataStartIdx; i < lines.length; i++) {
    const text = lines[i];
    const pointMatch = text.match(POINT_ID_RE);

    if (pointMatch) {
      flushPending();
      pendingPointId = formatPointId(pointMatch[0]);

      const remaining = text.replace(pointMatch[0], '');
      const numbers = remaining.match(/\d{2,4}/g);
      if (numbers) {
        for (const n of numbers) {
          if (!POINT_ID_RE.test(n)) {
            const val = parseInt(n, 10);
            if (val > 0) pendingValues.push(val);
          }
        }
      }

      const timeMatch = text.match(TIME_RE);
      if (timeMatch) pendingTime = timeMatch[0];

      const cleaned = remaining
        .replace(/\d{2,4}/g, '')
        .replace(/[|│┃¦]/g, '')
        .trim();
      if (
        cleaned.length >= 2 &&
        cleaned.length <= 10 &&
        /[\u4e00-\u9fa5]/.test(cleaned)
      ) {
        pendingRecorder = cleaned;
      }
      continue;
    }

    if (pendingPointId && PURE_NUMBER_RE.test(text)) {
      pendingValues.push(parseInt(text, 10));
    }
  }

  flushPending();
  return records;
}

@Injectable()
export class OcrService {
  private readonly logger = new Logger(OcrService.name);

  async recognizeImage(buffer: Buffer): Promise<PressureOcrResult[]> {
    let worker: Worker | null = null;
    try {
      this.logger.log('正在初始化Tesseract OCR引擎...');
      worker = await createWorker('chi_sim+eng');
      this.logger.log('OCR引擎初始化完成，开始识别...');

      const { data } = await worker.recognize(buffer);
      this.logger.log(`OCR原始文本长度: ${data.text.length} 字符`);

      const records = parseOcrText(data.text);
      this.logger.log(`解析完成，共 ${records.length} 条记录`);
      return records;
    } catch (error) {
      this.logger.error(`OCR识别失败: ${JSON.stringify(error)}`);
      throw new Error(`OCR识别失败: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      if (worker) {
        await worker.terminate();
      }
    }
  }
}
