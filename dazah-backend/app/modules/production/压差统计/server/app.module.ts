import { APP_FILTER } from '@nestjs/core';
import { Module } from '@nestjs/common';
import { PlatformModule } from '@lark-apaas/fullstack-nestjs-core';

import { GlobalExceptionFilter } from './common/filters/exception.filter';
import { ViewModule } from './modules/view/view.module';
import { DashboardModule } from './modules/dashboard/dashboard.module';
import { PressureRecordsModule } from './modules/pressure-records/pressure-records.module';
import { PointMappingsModule } from './modules/point-mappings/point-mappings.module';
import { AuditModule } from './modules/audit/audit.module';
import { NotificationModule } from './modules/notification/notification.module';
import { OcrTaskModule } from './modules/ocr-task/ocr-task.module';
import { OcrModule } from './modules/ocr/ocr.module';

@Module({
  imports: [
    // 平台 Module，提供平台能力
    PlatformModule.forRoot(),
    // ====== @route-section: business-modules START ======
    DashboardModule,
    PressureRecordsModule,
    PointMappingsModule,
    AuditModule,
    NotificationModule,
    OcrTaskModule,
    OcrModule,
    // ====== @route-section: business-modules END ======

    // ⚠️ @route-order: last
    // ViewModule is the fallback route module, must be registered last.
    ViewModule,
  ],
  providers: [
    {
      provide: APP_FILTER,
      useClass: GlobalExceptionFilter,
    },
  ],
})
export class AppModule {}
