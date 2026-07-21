import { Module } from '@nestjs/common';
import { PointMappingsController } from './point-mappings.controller';
import { PointMappingsService } from './point-mappings.service';

@Module({
  controllers: [PointMappingsController],
  providers: [PointMappingsService],
  exports: [PointMappingsService],
})
export class PointMappingsModule {}
