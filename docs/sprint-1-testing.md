# Sprint 1 Testing Write-up

> 说明：本文档用于提交 Sprint 1 Testing 作业（按要求包含五个部分）。当前内容以**可提交的骨架**为主，后续可在各部分补充细节与截图/对比。

## Part 1 — Brief overview (简要概述)

我们的 Sprint 1 目标是把“下一学季选课规划”这条主路径打通：学生导入/解析 transcript → 选择过滤条件与偏好 → 获取 eligible course 列表 → 生成/预览 AI 推荐计划 → 将计划加入日历并导出。

仓库当前的整合主工程位于：
- 后端 API：`project/api`（Express + Prisma + SQLite + OpenAI）
- 前端 Web：`project/web`（Vite + React）

对应的 Sprint 1 失败测试（RED）已放在：
- 后端：`project/api/tests/sprint1/`
- 前端：`project/web/tests/sprint1/`

## Part 2 — Red-to-green narrative (从红到绿的叙述)

本部分用于讲述你们选择的一条测试如何从 **RED → GREEN**（以及必要时的重构），并说明实现策略与关键取舍。

建议选一个“接缝(seam)”测试作为叙述对象，例如：
- `project/api/tests/sprint1/api-db.integration.test.ts`（`/schedule/complete` 端点打通 DB 查询 + 返回 plans）

### 2.1 初始 RED（为什么失败）

- **现象**：运行测试返回非 200（例如 400），或返回体结构不符合预期。
- **原因**：尚未配置测试数据库/迁移/种子数据，或端点缺少必要的依赖注入与错误处理策略。

（TODO：补充一次真实的失败输出片段/解释）

### 2.2 让它变 GREEN（最小实现）

- **实现要点**（示例）：
  - 为测试环境准备独立的 SQLite `DATABASE_URL`（避免污染开发库）
  - 测试前执行 Prisma migrate/seed（或用事务/临时库）
  - 端点保证在空数据与错误情况下返回稳定的 JSON 结构

（TODO：补充你们实际的最小实现步骤与关键代码点）

### 2.3 重构（可选）

（TODO：如果有重构，说明重构动机与如何保持测试绿）

## Part 3 — Skill description (技能描述)

本部分用于描述你们在 Sprint 1 用到的“技能/能力”（课程要求的 Skill 叙述），例如：
- **后端**：会话/鉴权与安全（HttpOnly cookie、sameSite、过期与轮换）
- **数据库**：计划（Plan）与条目（PlanItem）持久化
- **AI**：输出结构校验（JSON schema / zod）、最大条目数、护栏（guardrails）
- **前端**：关键流程的 UX 保护（按钮禁用/错误提示/空状态）

当前 Sprint 1 相关的（RED）单元测试示例：
- Jiasheng（后端会话）：`project/api/tests/sprint1/jiasheng.auth.unit.test.ts`
- Joey（计划持久化）：`project/api/tests/sprint1/joey.plan-persistence.unit.test.ts`
- Jason（AI 输出形状）：`project/api/tests/sprint1/jason.ai-output-shape.unit.test.ts`
- Ismael（前端流程）：`project/web/tests/sprint1/ismael.intro-flow.unit.test.tsx`

（TODO：用 1–2 段话写清楚“这个技能是什么、解决了什么问题、如何验证成功”）

## Part 4 — AI critique with before/after diff (AI 评审 + 前后对比 diff)

本部分用于展示一次“AI 建议/代码生成”在你们项目中的改进过程，要求包含 **before/after diff**。

### 4.1 Critique（评审要点）

- **问题**（示例）：AI 返回内容虽然是 JSON，但字段缺失/类型不稳定/条目过多导致 UI 渲染失败。
- **改进**（示例）：在后端新增解析层 `parseAiPlansJson()`，对必填字段与最大条目数做校验/截断，并对异常做可观测的错误返回。

（TODO：补充你们真实的 critique 内容）

### 4.2 Before/After diff

（TODO：把你们真实修改的 diff 粘贴到这里。示例格式如下）

```diff
- // before: accept raw model output without strict validation
+ // after: validate JSON shape + required fields + cap items per plan
```

## Part 5 — Jolli screenshot (Jolli 截图)

（TODO：将 Jolli 的截图插入到这里，并确保仓库里能访问到图片文件）

建议做法：
- 把截图放到 `docs/assets/`（或 `docs/images/`）目录下
- 然后用相对路径引用，例如：`![](./assets/jolli.png)`

