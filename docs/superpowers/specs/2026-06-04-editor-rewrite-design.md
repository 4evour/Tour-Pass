# 编辑器完全重写设计方案

## 一、设计目标

### 核心痛点
1. 前端逻辑问题：不能对单天行程进行精确修改，每次修改都自动更新页面，无法直观看出更改的内容
2. 不能跨天规划行程
3. 无法准确选择酒店，缺少酒店锚点系统
4. 更改时无法直观看出来更改的景点叫名字，只有一些圆点
5. 更改之后行程合理耗时与否也没有检查，没有提示

### 设计目标
- ✅ 支持单天编辑模式
- ✅ 命令模式支持撤销/重做
- ✅ 地图联动实时更新
- ✅ 合理性检查提示
- ✅ 酒店锚点系统
- ✅ POI名称显示

## 二、技术栈选择

| 模块 | 技术选择 | 理由 |
|------|----------|------|
| 前端框架 | React 18 + TypeScript | 保持现有技术栈 |
| 状态管理 | Zustand + Immer | 简洁、易用、支持不可变更新 |
| 地图库 | MapLibre GL | 开源免费、功能强大 |
| 拖拽库 | @dnd-kit | 现代、性能好、触摸支持 |
| UI组件 | TailwindCSS + Headless UI | 灵活、无样式冲突 |
| 酒店API | TripAdvisor Scraper API | 免费1000请求/月 |

## 三、核心架构设计

### 3.1 命令模式（Command Pattern）

`	ypescript
// 所有编辑操作都是可撤销的命令
interface Command {
  type: string;
  execute(): void;
  undo(): void;
  description: string; // 用于显示"已修改"标识
}

// 示例：添加POI命令
class AddStopCommand implements Command {
  type = 'ADD_STOP';
  description: string;
  
  constructor(
    private day: number,
    private poi: Poi,
    private index: number
  ) {
    this.description = 添加 \ 到第\天;
  }
  
  execute() {
    // 执行添加
  }
  
  undo() {
    // 撤销添加
  }
}
`

### 3.2 状态管理架构

`	ypescript
// stores/editorStore.ts - 编辑器状态
interface EditorState {
  mode: 'global' | 'day';
  currentDay: number | null;
  isEditing: boolean;
  changedItems: Map<string, string>; // itemId -> description
  
  // 操作
  enterDayEditMode: (day: number) => void;
  exitDayEditMode: () => void;
  markChanged: (itemId: string, description: string) => void;
  clearChanges: () => void;
}

// stores/historyStore.ts - 历史管理
interface HistoryState {
  undoStack: Command[];
  redoStack: Command[];
  
  execute: (command: Command) => void;
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;
}

// stores/itineraryStore.ts - 行程数据
interface ItineraryState {
  city: string;
  days: DayPlan[];
  routes: RouteSegment[];
  
  // 只保留数据操作
  setDays: (days: DayPlan[]) => void;
  getDay: (day: number) => DayPlan;
}

// stores/hotelStore.ts - 酒店状态
interface HotelState {
  defaultHotel: Poi | null;
  dayHotels: Map<number, Poi>;
  recommendations: HotelRecommendation[];
  isLoading: boolean;
  
  setDefaultHotel: (hotel: Poi) => void;
  setDayHotel: (day: number, hotel: Poi | null) => void;
  fetchRecommendations: (city: string) => Promise<void>;
}

// stores/validationStore.ts - 验证状态
interface ValidationState {
  issues: Map<number, Issue[]>; // day -> issues
  summary: string;
  
  validateDay: (day: number) => void;
  validateAll: () => void;
  clearValidation: () => void;
}
`

### 3.3 组件架构

`
web/editor/src/
├── core/                        # 核心逻辑
│   ├── commands/               # 命令实现
│   │   ├── Command.ts
│   │   ├── AddStopCommand.ts
│   │   ├── RemoveStopCommand.ts
│   │   ├── ReorderCommand.ts
│   │   ├── MoveBetweenDaysCommand.ts
│   │   └── UpdateTimeCommand.ts
│   ├── validation/             # 合理性检查
│   │   ├── ItineraryValidator.ts
│   │   └── rules.ts
│   └── services/               # 外部服务
│       ├── hotelService.ts     # TripAdvisor API
│       └── routeService.ts     # 路线计算
│
├── stores/                      # 状态管理
│   ├── editorStore.ts
│   ├── historyStore.ts
│   ├── itineraryStore.ts
│   ├── hotelStore.ts
│   ├── mapStore.ts
│   └── validationStore.ts
│
├── components/                  # UI组件
│   ├── Layout/                 # 布局组件
│   │   ├── EditorLayout.tsx    # 主布局
│   │   ├── Sidebar.tsx         # 侧边栏
│   │   └── Toolbar.tsx         # 工具栏
│   │
│   ├── Editor/                 # 编辑器组件
│   │   ├── DaySelector.tsx     # 天数选择器
│   │   ├── DayEditor.tsx       # 单天编辑器
│   │   ├── StopCard.tsx        # POI卡片
│   │   └── TimeEditor.tsx      # 时间编辑器
│   │
│   ├── Map/                    # 地图组件
│   │   ├── MapContainer.tsx    # 地图容器
│   │   ├── RouteRenderer.tsx   # 路线渲染
│   │   ├── POIMarker.tsx       # POI标记（显示名称）
│   │   └── HotelMarker.tsx     # 酒店标记
│   │
│   ├── Hotel/                  # 酒店组件
│   │   ├── HotelManager.tsx    # 酒店管理
│   │   ├── HotelPicker.tsx     # 酒店选择器
│   │   ├── HotelRecommend.tsx  # 酒店推荐
│   │   └── HotelCard.tsx       # 酒店卡片
│   │
│   ├── Validation/             # 验证组件
│   │   ├── ValidationPanel.tsx # 验证面板
│   │   └── IssueCard.tsx       # 问题卡片
│   │
│   └── Shared/                 # 共享组件
│       ├── UndoRedoToolbar.tsx # 撤销/重做
│       ├── ChangeIndicator.tsx # 修改标识
│       └── ConflictAlert.tsx   # 冲突警告
│
├── hooks/                       # 自定义hooks
│   ├── useEditor.ts
│   ├── useHistory.ts
│   ├── useValidation.ts
│   ├── useMapSync.ts
│   └── useHotelRecommend.ts
│
└── App.tsx                      # 主入口
`

## 四、核心交互流程

### 4.1 单天编辑模式

`
用户点击某天
    ↓
进入单天编辑模式
    ↓
地图只显示当天路线
    ↓
侧边栏显示当天POI列表
    ↓
用户编辑（拖拽、删除、添加）
    ↓
命令模式记录操作
    ↓
地图实时更新
    ↓
合理性检查自动运行
    ↓
用户点击"保存"或"退出"
    ↓
退出单天编辑模式
`

### 4.2 酒店锚点流程

`
用户创建行程
    ↓
设置全局默认酒店
    ↓
系统推荐酒店（TripAdvisor API）
    ↓
用户选择酒店
    ↓
每天自动计算：酒店 → POI1 → ... → POIn → 酒店
    ↓
用户可覆盖某天酒店
    ↓
重新计算当天路线
`

### 4.3 撤销/重做流程

`
用户执行操作（如添加POI）
    ↓
创建命令对象
    ↓
执行命令
    ↓
压入撤销栈
    ↓
清空重做栈
    ↓
更新UI
    ↓
用户按Ctrl+Z
    ↓
从撤销栈弹出命令
    ↓
执行undo()
    ↓
压入重做栈
    ↓
更新UI
`

## 五、地图交互设计

### 5.1 POI标记显示

`	ypescript
// POI标记显示名称，不只是圆点
const POIMarker = ({ stop, index }) => {
  return (
    <Marker position={[stop.lng, stop.lat]}>
      <div className="poi-marker">
        <div className="marker-number">{index + 1}</div>
        <div className="marker-name">{stop.poi.name}</div>
        <div className="marker-time">
          {formatTime(stop.arrival)} - {formatTime(stop.departure)}
        </div>
      </div>
    </Marker>
  );
};
`

### 5.2 路线渲染

`	ypescript
// 路线实时更新
const RouteRenderer = ({ routes, currentDay, mode }) => {
  const visibleRoutes = useMemo(() => {
    if (mode === 'day' && currentDay !== null) {
      return routes.filter(r => r.day === currentDay);
    }
    return routes;
  }, [routes, currentDay, mode]);
  
  return (
    <>
      {visibleRoutes.map((route, i) => (
        <Line
          key={i}
          coordinates={route.pathCoords}
          color={route.day === currentDay ? '#3b82f6' : '#94a3b8'}
          width={route.day === currentDay ? 4 : 2}
        />
      ))}
    </>
  );
};
`

## 六、合理性检查规则

`	ypescript
// core/validation/rules.ts
const validationRules = [
  {
    name: 'time-conflict',
    check: (day: DayPlan) => {
      // 检查相邻POI时间是否重叠
    },
    message: '时间冲突：{poi1}和{poi2}时间重叠'
  },
  {
    name: 'travel-time',
    check: (day: DayPlan) => {
      // 检查通勤时间是否充足
    },
    message: '通勤时间不足：从{poi1}到{poi2}需要{minutes}分钟'
  },
  {
    name: 'opening-hours',
    check: (day: DayPlan) => {
      // 检查是否在开放时间内
    },
    message: '开放时间冲突：{poi}在{time}不开放'
  },
  {
    name: 'total-duration',
    check: (day: DayPlan) => {
      // 检查总耗时是否合理（8-12小时）
    },
    message: '行程过紧：总耗时{hours}小时，建议减少景点'
  }
];
`

## 七、酒店推荐系统

`	ypescript
// core/services/hotelService.ts
class HotelService {
  private apiKey = 'REDACTED_HOTEL_API_KEY';
  private baseUrl = 'https://tripadvisor-scraper-api.omkar.cloud/tripadvisor';
  
  async searchHotels(city: string): Promise<Hotel[]> {
    const response = await fetch(
      \/hotels/search?query=\,
      { headers: { 'API-Key': this.apiKey } }
    );
    const data = await response.json();
    return data.results.map(this.transformHotel);
  }
  
  async getHotelDetails(entityId: string): Promise<HotelDetail> {
    const response = await fetch(
      \/hotels/detail?entity_id=\,
      { headers: { 'API-Key': this.apiKey } }
    );
    return this.transformDetail(await response.json());
  }
  
  // 推荐入住区域
  async getRecommendedAreas(city: string): Promise<Area[]> {
    // 基于景点分布推荐入住区域
    // 如：市中心、景区附近、交通枢纽附近
  }
  
  // 按价格区间筛选
  filterByPriceRange(hotels: Hotel[], range: 'budget' | 'comfort' | 'luxury'): Hotel[] {
    const priceMap = {
      budget: { min: 0, max: 300 },
      comfort: { min: 300, max: 800 },
      luxury: { min: 800, max: Infinity }
    };
    return hotels.filter(h => 
      h.price >= priceMap[range].min && 
      h.price <= priceMap[range].max
    );
  }
}
`

## 八、开发计划

| 阶段 | 任务 | 时间 |
|------|------|------|
| **第1周** | 核心架构搭建 | 5天 |
| | - 命令模式实现 | 1天 |
| | - 状态管理重构 | 1天 |
| | - 基础组件搭建 | 2天 |
| | - 地图集成 | 1天 |
| **第2周** | 编辑器功能 | 5天 |
| | - 单天编辑模式 | 2天 |
| | - 拖拽排序 | 1天 |
| | - 撤销/重做 | 1天 |
| | - POI名称显示 | 1天 |
| **第3周** | 酒店系统 | 5天 |
| | - TripAdvisor API集成 | 1天 |
| | - 酒店推荐功能 | 2天 |
| | - 酒店锚点逻辑 | 2天 |
| **第4周** | 验证与优化 | 5天 |
| | - 合理性检查 | 2天 |
| | - UI优化 | 2天 |
| | - 测试与修复 | 1天 |
| **第5-6周** | 测试与发布 | 10天 |
| | - 集成测试 | 3天 |
| | - 用户测试 | 3天 |
| | - Bug修复 | 4天 |

## 九、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 重写期间无法发布新功能 | 中 | 分阶段发布，核心功能优先 |
| 可能引入新的bug | 高 | 充分测试，保留旧版本回滚 |
| 需要重新测试所有功能 | 中 | 自动化测试覆盖 |
| TripAdvisor API限流 | 低 | 本地缓存，批量请求 |

## 十、成功标准

1. ✅ 支持单天编辑模式，编辑时不跳转全部行程
2. ✅ 支持撤销/重做（Ctrl+Z / Ctrl+Y）
3. ✅ 地图实时联动，编辑时路线立即更新
4. ✅ POI标记显示名称，不只是圆点
5. ✅ 合理性检查自动运行，提示时间冲突
6. ✅ 酒店锚点系统，每天从酒店出发回到酒店
7. ✅ 酒店推荐功能，支持价格区间筛选
8. ✅ 性能不劣于现有版本
