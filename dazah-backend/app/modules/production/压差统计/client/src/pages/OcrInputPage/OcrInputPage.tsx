import React, { useCallback, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Camera, ImageIcon, UploadCloud, Loader2, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { recognizePressureImage } from './ocr-service';

const IS_MOBILE = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
  navigator.userAgent,
);

type PagePhase = 'upload' | 'preview' | 'recognizing' | 'recognized';

const OcrInputPage: React.FC = () => {
  const navigate = useNavigate();
  const [phase, setPhase] = useState<PagePhase>('upload');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string>('');
  const [dragOver, setDragOver] = useState(false);
  const [ocrCount, setOcrCount] = useState<number>(0);


  const cameraInputRef = useRef<HTMLInputElement>(null);
  const albumInputRef = useRef<HTMLInputElement>(null);
  const pcInputRef = useRef<HTMLInputElement>(null);

  const runOcr = useCallback(async (file: File) => {
    try {
      const records = await recognizePressureImage(file);
      setOcrCount(records.length || 0);
      setPhase('recognized');
      toast.success(`识别完成，共 ${records.length} 条记录`);
    } catch (err: unknown) {
      const error = err as { message?: string };
      toast.error('识别失败：' + (error.message || '未知错误'));
      setPhase('preview');
    }
  }, []);

  const handleFileSelect = useCallback((file: File | null) => {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      toast.error('请选择图片文件');
      return;
    }
    setSelectedFile(file);
    setImagePreviewUrl(URL.createObjectURL(file));
    setPhase('preview');
  }, []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      handleFileSelect(e.target.files?.[0] ?? null);
      e.target.value = '';
    },
    [handleFileSelect],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      handleFileSelect(e.dataTransfer.files?.[0] ?? null);
    },
    [handleFileSelect],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => setDragOver(false), []);

  const handleRetake = useCallback(() => {
    if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl);
    setSelectedFile(null);
    setImagePreviewUrl('');
    setPhase('upload');
  }, [imagePreviewUrl]);

  const handleConfirmRecognize = useCallback(async () => {
    if (!selectedFile) return;
    setPhase('recognizing');
    runOcr(selectedFile);
  }, [selectedFile, runOcr]);

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <button
          type="button"
          onClick={() => navigate('/')}
          className="flex items-center justify-center w-9 h-9 rounded-lg hover:bg-accent transition-colors"
          aria-label="返回首页"
        >
          <ArrowLeft className="size-5 text-foreground" />
        </button>
        <h1 className="text-xl font-bold text-foreground">OCR识别录入</h1>
      </div>

      {phase === 'upload' && (
        <div className="space-y-4">
          {IS_MOBILE ? (
            <div className="grid grid-cols-2 gap-4">
              <Button
                type="button"
                variant="outline"
                className="min-h-12 flex-col gap-2 py-6"
                onClick={() => cameraInputRef.current?.click()}
              >
                <Camera className="size-6" />
                <span className="text-base">拍照</span>
              </Button>
              <Button
                type="button"
                variant="outline"
                className="min-h-12 flex-col gap-2 py-6"
                onClick={() => albumInputRef.current?.click()}
              >
                <ImageIcon className="size-6" />
                <span className="text-base">相册</span>
              </Button>
              <input
                ref={cameraInputRef}
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                onChange={handleInputChange}
              />
              <input
                ref={albumInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handleInputChange}
              />
            </div>
          ) : (
            <div
              className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${
                dragOver
                  ? 'border-primary bg-accent/50'
                  : 'border-border hover:border-primary/50'
              }`}
              onClick={() => pcInputRef.current?.click()}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
            >
              <UploadCloud className="size-10 mx-auto mb-3 text-muted-foreground" />
              <p className="text-base text-foreground mb-1">
                点击上传或拖拽图片到此处
              </p>
              <p className="text-sm text-muted-foreground">支持 JPG、PNG 格式</p>
              <input
                ref={pcInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handleInputChange}
              />
            </div>
          )}
        </div>
      )}

      {phase === 'preview' && selectedFile && (
        <div className="space-y-4">
          <div className="rounded-lg overflow-hidden bg-card border border-border">
            <img
              src={imagePreviewUrl}
              alt="预览图片"
              className="w-full max-h-[60vh] object-contain"
            />
          </div>
          <div className="flex gap-3">
            <Button
              type="button"
              variant="outline"
              className="flex-1 min-h-12 text-lg"
              onClick={handleRetake}
            >
              重新选择
            </Button>
            <Button
              type="button"
              className="flex-1 min-h-12 text-lg"
              onClick={handleConfirmRecognize}
            >
              开始识别
            </Button>
          </div>
        </div>
      )}

      {phase === 'recognizing' && (
        <div className="flex flex-col items-center justify-center py-20">
          <Loader2 className="size-10 text-primary animate-spin mb-4" />
          <p className="text-base text-foreground mb-1">正在识别中...</p>
          <p className="text-sm text-muted-foreground">OCR 引擎正在分析图片，请耐心等待</p>
        </div>
      )}

      {phase === 'recognized' && (
        <div className="flex flex-col items-center justify-center py-16">
          <CheckCircle2 className="size-12 text-emerald-500 mb-4" />
          <p className="text-base text-foreground mb-2">识别完成</p>
          <p className="text-sm text-muted-foreground mb-6">
            共识别到 {ocrCount} 条记录
          </p>
          <div className="flex gap-3">
            <Button variant="outline" className="min-h-12" onClick={() => navigate('/')}>
              返回首页
            </Button>
            <Button className="min-h-12" onClick={() => navigate('/records')}>
              查看记录
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default OcrInputPage;