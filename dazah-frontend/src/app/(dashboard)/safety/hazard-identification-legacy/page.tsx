'use client'

"use client"

'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Table,
  Button,
  Space,
  Input,
  Select,
  Modal,
  Form,
  Upload,
  Tag,
  Card,
  Row,
  Col,
  Typography,
  Tabs,
  App,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { UploadProps } from 'antd'
import {
  PlusOutlined,
  SearchOutlined,
  EyeOutlined,
  DeleteOutlined,
  EditOutlined,
  UploadOutlined,
  CheckCircleOutlined,
  LinkOutlined,
  FileTextOutlined,
} from '@ant-design/icons'
import {
  getHazardIdentifications,
  deleteHazardIdentification,
  getHazardRevisionRecords,
  createHazardRevisionRecord,
  updateHazardRevisionRecord,
  deleteHazardRevisionRecord,
  approveHazardRevision,
  uploadHazardRevisionDocument,
  linkRevisionToArchive,
  getHazardRevisionArchives,
  createHazardRevisionArchive,
  updateHazardRevisionArchive,
  deleteHazardRevisionArchive,
  getRevisions,
} from '@/actions/safety'
import type {
  HazardIdentification,
  HazardRevisionRecord,
  HazardRevisionRecordFormData,
  HazardRevisionArchive,
  HazardRevisionArchiveFormData,
  RegulationRevision,
} from '@/types/safety'
import {
  AI_NODE_PROGRESS_OPTIONS,
  OVERALL_STATUS_OPTIONS_HI,
  RISK_LEVEL_OPTIONS,
  IDENTIFICATION_TYPE_OPTIONS,
  REVIEW_OPINION_OPTIONS,
  ARCHIVE_STATUS_OPTIONS,
} from '@/types/safety'
import dayjs from 'dayjs'
import { useSafetyStore } from '@/stores/safety'

const { Text } = Typography
export default function HazardIdentificationLegacyPage() {
  const { message } = App.useApp()
  return (
    <div style={{ padding: 24 }}>
      <Text> hazard-identification-legacy 页面正在开发中...</Text>
    </div>
  )
}
