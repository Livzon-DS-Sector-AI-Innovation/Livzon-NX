import { Controller, Post, Body } from '@nestjs/common';
import { OcrService } from './ocr.service';
import { Logger } from '@nestjs/common';
import type { PressureOcrResult } from './ocr.service';

interface OcrRequestBody {
  image: string;
  mimetype: string;
}

@Controller('api/ocr')
export class OcrController {
  private readonly logger = new Logger(OcrController.name);

  constructor(private readonly ocrService: OcrService) {}

  @Post()
  async recognize(
    @Body() body: OcrRequestBody,
  ): Promise<{ result: PressureOcrResult[] }> {
    if (!body.image) {
      throw new Error('未上传图片数据');
    }
    const buffer = Buffer.from(body.image, 'base64');
    this.logger.log(`收到OCR请求: ${body.mimetype}, ${buffer.length}字节`);
    const result = await this.ocrService.recognizeImage(buffer);
    this.logger.log(`OCR识别完成，共 ${result.length} 条记录`);
    return { result };
  }
}
