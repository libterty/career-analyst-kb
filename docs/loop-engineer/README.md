# Loop Engineering — Career Analyst KB

**Author**: Albert
**Date**: 2026-07-09
**Branch**: feat/docs-migration

## 概述

根據 LangChain《The Art of Loop Engineering》的四層架構，分析 Career Analyst KB（YouTube 職涯知識庫 + VoltAgent）的現況與優化路徑。

> Agent 的威力不在模型本身，而在你替它設計了幾層「迴圈」。

## 四層 Loop 現況

| Loop | 名稱 | 現況 | 優先級 |
|------|------|------|--------|
| Loop 1 | Agent Loop | ✅ 已完成 | — |
| Loop 2 | Verification Loop | ❌ 未實作 | 🔴 高 |
| Loop 3 | Event-Driven Loop | ❌ 未實作 | 🟡 中 |
| Loop 4 | Hill Climbing Loop | ❌ 未實作 | 🟡 中 |

## 文件索引

- [design.md](./design.md) — 四層 Loop 設計文件（架構、決策、現況分析）
- [implement.md](./implement.md) — 實作計畫（Phase by Phase 任務清單）
