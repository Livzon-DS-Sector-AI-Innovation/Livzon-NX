import React from 'react';
import { Route, Routes } from 'react-router-dom';

import Layout from './components/Layout';
import NotFound from './pages/NotFound/NotFound';
import HomePage from './pages/HomePage/HomePage';
import ManualInputPage from './pages/ManualInputPage/ManualInputPage';
import OcrInputPage from './pages/OcrInputPage/OcrInputPage';
import OcrResultPage from './pages/OcrInputPage/OcrResultPage';
import RecordsPage from './pages/RecordsPage/RecordsPage';
import PointManagementPage from './pages/PointManagementPage/PointManagementPage';
import AuditManagementPage from './pages/AuditManagementPage/AuditManagementPage';

const RoutesComponent = () => {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="manual-input" element={<ManualInputPage />} />
        <Route path="ocr-input" element={<OcrInputPage />} />
        <Route path="ocr-result/:taskId" element={<OcrResultPage />} />
        <Route path="records" element={<RecordsPage />} />
        <Route path="point-management" element={<PointManagementPage />} />
        <Route path="audit-management" element={<AuditManagementPage />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
};

export default RoutesComponent;
