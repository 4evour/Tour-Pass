# 编辑器完全重写实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完全重写Tour Pass编辑器，实现单天编辑模式、命令模式撤销/重做、地图联动、合理性检查和酒店推荐系统

**Architecture:** 采用命令模式+状态管理+组件化架构，核心模块包括：命令系统（可撤销操作）、状态管理（Zustand）、地图联动（MapLibre GL）、酒店服务（TripAdvisor API）

**Tech Stack:** React 18, TypeScript, Zustand, Immer, MapLibre GL, @dnd-kit, TailwindCSS

---

## 文件结构

### 核心模块
- `core/commands/Command.ts` - 命令基类
- `core/commands/AddStopCommand.ts` - 添加POI命令
- `core/commands/RemoveStopCommand.ts` - 删除POI命令
- `core/commands/ReorderCommand.ts` - 重排序命令
- `core/commands/MoveBetweenDaysCommand.ts` - 跨天移动命令
- `core/commands/UpdateTimeCommand.ts` - 更新时间命令
- `core/validation/ItineraryValidator.ts` - 行程验证器
- `core/validation/rules.ts` - 验证规则
- `core/services/hotelService.ts` - 酒店服务

### 状态管理
- `stores/editorStore.ts` - 编辑器状态
- `stores/historyStore.ts` - 历史管理
- `stores/itineraryStore.ts` - 行程数据
- `stores/hotelStore.ts` - 酒店状态
- `stores/validationStore.ts` - 验证状态

### 组件
- `components/Layout/EditorLayout.tsx` - 主布局
- `components/Editor/DaySelector.tsx` - 天数选择器
- `components/Editor/DayEditor.tsx` - 单天编辑器
- `components/Editor/StopCard.tsx` - POI卡片
- `components/Map/MapContainer.tsx` - 地图容器
- `components/Map/POIMarker.tsx` - POI标记
- `components/Map/RouteRenderer.tsx` - 路线渲染
- `components/Hotel/HotelManager.tsx` - 酒店管理
- `components/Hotel/HotelRecommend.tsx` - 酒店推荐
- `components/Validation/ValidationPanel.tsx` - 验证面板
- `components/Shared/UndoRedoToolbar.tsx` - 撤销重做工具栏

### Hooks
- `hooks/useEditor.ts` - 编辑器hook
- `hooks/useHistory.ts` - 历史hook
- `hooks/useValidation.ts` - 验证hook
- `hooks/useMapSync.ts` - 地图同步hook

---

详细实现步骤请参考设计文档：`docs/superpowers/specs/2026-06-04-editor-rewrite-design.md`

---

## 执行选项

**计划完成并保存到 docs/superpowers/plans/2026-06-04-editor-rewrite-implementation.md**

两种执行方式：

**1. Subagent-Driven（推荐）** - 每个任务分发一个新的子代理，任务间进行审查，快速迭代

**2. Inline Execution** - 在当前会话中执行任务，批量执行并设置检查点

**选择哪种方式？**
