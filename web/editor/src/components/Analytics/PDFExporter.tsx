import React from 'react';
import type { DayPlan, Poi } from '../../types';

interface PDFExporterProps {
  days: DayPlan[];
  city: string;
  defaultHotel: Poi | null;
}

export const PDFExporter: React.FC<PDFExporterProps> = ({ days, city, defaultHotel }) => {
  const handleExport = async () => {
    const content = generatePDFContent(days, city, defaultHotel);
    
    // 创建 Blob
    const blob = new Blob([content], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    
    // 打开新窗口打印
    const printWindow = window.open(url, '_blank');
    if (printWindow) {
      printWindow.onload = () => {
        printWindow.print();
      };
    }
    
    URL.revokeObjectURL(url);
  };
  
  return (
    <button
      onClick={handleExport}
      className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
    >
      导出 PDF
    </button>
  );
};

function generatePDFContent(days: DayPlan[], city: string, defaultHotel: Poi | null): string {
  return `
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>${city} 行程单</title>
  <style>
    body { font-family: 'Microsoft YaHei', sans-serif; padding: 20px; }
    h1 { color: #1a1a1a; border-bottom: 2px solid #3b82f6; padding-bottom: 10px; }
    h2 { color: #374151; margin-top: 30px; }
    .day { margin-bottom: 30px; page-break-inside: avoid; }
    .stop { display: flex; align-items: center; padding: 10px; border-left: 3px solid #3b82f6; margin: 10px 0; }
    .stop-number { width: 30px; height: 30px; background: #3b82f6; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 15px; }
    .stop-info h3 { margin: 0; color: #1a1a1a; }
    .stop-info p { margin: 5px 0 0; color: #6b7280; font-size: 14px; }
    .hotel { background: #f0fdf4; border-left-color: #22c55e; }
    .footer { margin-top: 50px; text-align: center; color: #9ca3af; font-size: 12px; }
  </style>
</head>
<body>
  <h1>${city} 行程单</h1>
  
  ${defaultHotel ? `
  <div class="stop hotel">
    <div class="stop-number">🏨</div>
    <div class="stop-info">
      <h3>入住酒店：${defaultHotel.name}</h3>
      <p>${defaultHotel.area || ''}</p>
    </div>
  </div>
  ` : ''}
  
  ${days.map((day, i) => `
    <div class="day">
      <h2>第${day.day}天</h2>
      ${day.stops.map((stop, j) => `
        <div class="stop">
          <div class="stop-number">${j + 1}</div>
          <div class="stop-info">
            <h3>${stop.poi.name}</h3>
            <p>
              ${stop.arrival > 0 ? formatTime(stop.arrival) : ''}
              ${stop.arrival > 0 && stop.departure > 0 ? ' - ' + formatTime(stop.departure) : ''}
              · ${stop.poi.visit_duration || 60}分钟
            </p>
            ${stop.poi.area ? `<p>${stop.poi.area}</p>` : ''}
          </div>
        </div>
      `).join('')}
    </div>
  `).join('')}
  
  <div class="footer">
    <p>由 Tour Pass 生成 · ${new Date().toLocaleDateString()}</p>
  </div>
</body>
</html>
  `;
}

function formatTime(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
}
