import { Module } from '@nestjs/common';
import { OcrTaskController } from './ocr-task.controller';
import { OcrTaskService } from './ocr-task.service';

@Module({
  controllers: [OcrTaskController],
  providers: [OcrTaskService],
  exports: [OcrTaskService],
})
export class OcrTaskModule {}
