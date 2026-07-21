import { Module } from '@nestjs/common';
import { PressureRecordsController } from './pressure-records.controller';
import { PressureRecordsService } from './pressure-records.service';

@Module({
  controllers: [PressureRecordsController],
  providers: [PressureRecordsService],
  exports: [PressureRecordsService],
})
export class PressureRecordsModule {}
