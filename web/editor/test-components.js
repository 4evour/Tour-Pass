// 测试组件导入
const components = [
  // 命令模式
  'core/commands/Command',
  'core/commands/AddStopCommand',
  'core/commands/RemoveStopCommand',
  'core/commands/ReorderCommand',
  'core/commands/MoveBetweenDaysCommand',
  'core/commands/UpdateTimeCommand',
  
  // 状态管理
  'stores/historyStore',
  'stores/editorStore',
  
  // 服务
  'core/services/hotelService',
  'core/services/hotelAnchorService',
  'core/validation/rules',
  
  // Hooks
  'hooks/useMapSync',
  'hooks/useValidation',
  'hooks/useKeyboardShortcuts',
  'hooks/useResponsive',
  'hooks/useTheme',
  
  // 组件
  'components/Layout/EditorLayout',
  'components/Editor/DayEditor',
  'components/Editor/MultiDayTimeline',
  'components/Editor/SortableStop',
  'components/Editor/TimelineView',
  'components/Editor/HistoryPanel',
  'components/Map/IntegratedMap',
  'components/Map/POIMarker',
  'components/Map/RouteRenderer',
  'components/Hotel/HotelManager',
  'components/Hotel/HotelRecommend',
  'components/Hotel/HotelDetailCard',
  'components/Hotel/HotelAnchorManager',
  'components/Hotel/AreaRecommender',
  'components/Analytics/ScoreBreakdown',
  'components/Analytics/BudgetTracker',
  'components/Analytics/PDFExporter',
  'components/Analytics/SharePanel',
  'components/Collaboration/CollaboratorManager',
  'components/Collaboration/CommentSystem',
  'components/Collaboration/VersionManager',
  'components/Mobile/MobileNav',
  'components/Validation/ValidationPanel',
  'components/Shared/UndoRedoToolbar',
];

console.log('=== 组件导入测试 ===');
console.log(`共 ${components.length} 个模块需要验证`);

let passed = 0;
let failed = 0;

for (const comp of components) {
  try {
    // 检查文件是否存在
    const fs = require('fs');
    const path = require('path');
    const filePath = path.join(__dirname, `${comp}.ts`);
    const tsxPath = path.join(__dirname, `${comp}.tsx`);
    
    if (fs.existsSync(filePath) || fs.existsSync(tsxPath)) {
      passed++;
    } else {
      console.log(`❌ ${comp} - 文件不存在`);
      failed++;
    }
  } catch (e) {
    console.log(`❌ ${comp} - 错误: ${e.message}`);
    failed++;
  }
}

console.log(`\n=== 测试结果 ===`);
console.log(`✅ 通过: ${passed}`);
console.log(`❌ 失败: ${failed}`);
console.log(`总计: ${components.length}`);
