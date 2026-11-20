# VLA / 世界模型 / 具身 Agent 文献综述笔记

> 目的：为论文选题摸底。回答三件事——(1) 领域解决什么问题；(2) 主流方法分几类；(3) 作者明确写出的未解决问题。
> 整理日期：2026-11-10。所有观点均来自论文原文，出处见各节。

---

## 一、VLA（Vision-Language-Action）模型

主要来源：
- arXiv 2511.05936 — "10 Open Challenges Steering the Future of Vision-Language-Action Models"（2025-11）
- arXiv 2508.15201 — Survey of VLA Models for Embodied Manipulation
- arXiv 2510.07077 — VLA Models for Robotics: A Review Towards Real-World Applications

### 1.1 解决的问题

把「图像观测 + 语言指令 + 本体状态」直接映射成机器人动作序列。目标是用 VLM 的常识和泛化能力，替代"每个任务单独训一个策略"的传统范式，让**一个模型听懂指令做多种操作任务**。

### 1.2 主流方法流派

| 流派 | 代表 | 做法 | 优缺点（原文所述） |
|---|---|---|---|
| 离散动作 token 化 | RT-2、OpenVLA、FAST+ | 动作分箱（如 256 bins）编码成 token 塞入 LLM 词表，自回归生成；FAST+ 用 DCT + BPE 压缩动作序列 | 收敛快、复用 LLM 训练管线；但推理慢（3–5 Hz）、高频控制不可靠、不适合双臂 |
| 连续动作专家 | π0 / π0.5、OpenVLA-OFT | VLM 隐状态条件化一个小的 diffusion / flow-matching 动作专家，输出连续动作 | 高频、灵巧；但扩散类策略训练收敛的计算成本高 |
| 混合派 | π0.5 等 | 先离散自回归预训练，再嫁接动作专家后训练；knowledge insulation 保护 VLM 语义知识不被冲掉 | 结合两者优点，收敛更快，是目前主线 |
| 分层 / 编排派 | VoLoAgent、Yang et al. 2025 异构框架 | 上层 LLM/VLM 做规划和验证，下层 VLA 当技能执行器 | 长程任务更稳；架构复杂，两层接口设计是难点 |

原文要点：离散派"慢但收敛快"，连续派"快但训贵"，两者互补——**结构选型本身是开放问题**。

### 1.3 作者明确写出的未解决问题（10 Open Challenges 原文逐条）

1. **深度/3D 感知缺失**：除 MolmoAct、SpatialVLA 外都不显式使用深度；靠多帧推断不可靠，且现有方案也只在训练阶段用深度。
2. **推理弱、长程退化**：Emma-X、CoT-VLA、MolmoAct 加了推理链仍 imperfect；horizon 越长成功率越低。
3. **数据质量**：原文点明 `"variance and noise in the collected data"`——来自本体差异、**相机位置角度**、采集者认知行为不一致。→ 对应我们实际踩过的遥操作抖动、相机移位问题。
4. **评估难**：真机评测不可扩展；SimplerEnv 等仿真评测与真机相关性差（光照/材质/PD 参数都差）。
5. **跨本体动作泛化**：action heterogeneity，换构型就失效。
6. **资源效率**：机载算力跑不动大模型，小模型性能明显掉；thin-client 方案受网络延迟限制。
7. **全身协调**：移动 + 操作耦合的高维搜索空间；MPC 精确但调参难、学习法泛化差，混合框架是未来方向但尚无定论。
8. **安全保证**：几乎只有一篇 RL 式安全对齐初步工作，guardrail/fail-safe 体系缺失。
9. **Agentic 框架中的 VLA**：原文 `"yet to be thoroughly explored"`，且 `"determining the appropriate level of agency and autonomy"` 是开放问题。→ 正中"监控器决定何时接管"的想法。
10. **人机协调**：通信单向（人→机），机器人无法反问、解释、汇报意图（CoT-VLA 输出目标图像、Emma-X 输出理由是初步尝试）。

### 1.4 原文指出的应对趋势（§3）

分层规划、空间理解增强感知、通用动作表征、世界动力学建模、生成式数据合成、后训练（post-training）。

---

## 二、世界模型（World Models，机器人操作方向）

主要来源：
- arXiv 2606.00113 — "World Models for Robotic Manipulation: A Survey"
- arXiv 2511.02097 — "A Step Toward World Models: A Survey on Robotic Manipulation"

### 2.1 解决的问题

给机器人一个内部模拟器：**预测"执行这个动作之后世界会变成什么样"**。用途：动作前想象推演（规划）、合成训练数据、候选动作评估、执行结果验证——补 VLA"只模仿不理解因果"的短板。

### 2.2 流派（原文按"预测什么表示"分 5 族）

| 表示族 | 内容 | 代表 |
|---|---|---|
| 图像/视频预测 | action-conditioned 视频生成 | UniPi 系、GR 系内嵌视频模型 |
| 隐空间动力学 | 在 latent 空间学转移，紧凑高效 | DreamerV3、TD-MPC2、DINO-WM（DINOv2 嵌入上跑 MPC） |
| 运动场 / scene flow | 预测像素或点云级运动 | — |
| 3D/4D 场景结构 | 显式几何动态表示 | — |
| 物理信息模型 | 可微物理、先验约束 | — |

功能上分两派：**集成式**（预测与动作生成一体，如 VLA 内生预测）vs **显式规划器**（模型只管预测，MPC/搜索负责决策）。
基础设施角色：合成经验生成、候选过滤、搜索评估、学习环境、**结果验证**。

### 2.3 作者写出的未解决问题

- **接触建模**：生成的画面视觉合理但违反接触物理（hallucination：物体穿透、永久消失）。
- **保真度 ≠ 动作有用性**：`"predictive fidelity and action utility do not always coincide"`——重建好看不代表能用来控制。
- **动作对齐**：预测的视觉未来与实际动作效果对不上。
- **闭环 benchmark 缺失**：开环重建指标好不说明闭环控制有效，缺乏统一评估协议。
- **定义分裂**：不同社区（MBRL / 视频预测 / 几何 / VLA）对"world model"理解不一致，文献碎片化。

---

## 三、具身 Agent（LLM/VLM 驱动的机器人自主系统）

主要来源：
- arXiv 2508.05294 — "Towards Embodied Agentic AI: Review and Classification of LLM- and VLM-Driven Robot Autonomy and Interaction"
- arXiv 2510.23357 — LLM-based task planning for service robots 综述
- PMC12402697 — Agentic LLM-based robotic systems 综述

### 3.1 解决的问题

**长程任务的分解与执行**：一句话目标 → 拆成子步骤 → 调用技能/工具执行 → 出错恢复。与 VLA 的分工：VLA 管"单个技能怎么做"，agent 管"先做什么后做什么、做错了怎么办"。

### 3.2 流派（原文 §III 按集成方式分 5 类）

| 类别 | 做法 | 代表 |
|---|---|---|
| Protocol integration | LLM 当一次性翻译器（语言 → ROS 命令 / 代码） | ros2ai、MCP server、code-as-policies |
| Interface integration | 工具结果反馈进循环，多轮调用 | ROSA、RAI、BUMBLE、OpenMind |
| Orchestration-oriented | LLM/VLM 当 planner / 资源协调器 | planner agent 类 |
| Embedded / direct | 模型直接出动作（= VLA 端到端派） | VLA 系列 |
| Agentic frameworks | 多层组合：接口 agent + 协调 agent + 执行子系统 | 混合系统（原文评语：尚不成熟，多数工作只做单层） |

### 3.3 作者写出的未解决问题

- **实时性 vs 安全**：LLM 推理延迟 + 幻觉 → 物理安全风险；推理效率是实时规划的通用瓶颈。
- **记忆最不成熟**：原文 `"least mature capability"`——大多 agent 只在会话窗口内工作，无持久语义索引记忆，跨任务复用经验做不到。
- **异构数据流 / 跨本体**：不同传感器频率、不同机器人形态下 agent 层难统一抽象。
- **长程物理不确定性**：动作耗时可变、可能失败，需要"continuous situational awareness, progress monitoring, and adaptive recovery"（原文直接点名）。
- **评估指标缺失**：自主性越高越难评估；仅查目标达成会漏掉"动作多余/效率差"等问题。
- **grounding / 幻觉**：LLM 缺真实物理常识，可能产出不合逻辑的动作计划。
- **多 agent VLA 系统**：基本空白（信任、安全、可验证的工作流生成都缺）。

---

## 四、三领域交叉出的空白点（选题候选）

把三份"未解决清单"叠在一起，交集处是没人做满的格子：

1. **执行监控 + 接管时机的学习**（VLA §2.9 "appropriate level of agency" + agent 文献点名 "progress monitoring and adaptive recovery"）——用小网络/世界模型判断何时该触发 agent 接管或重试。文献明确列为空白。
2. **数据噪声/抖动对策略的影响与缓解**（VLA §2.3 原文点名的数据 variance/noise 痛点）——手头已有实测：示范加速度 0.166 vs rollout 0.422。
3. **推理时观测规范化**（VLA §2.4 评估失真 + canonicalization 思路）——SimplerEnv 只在仿真端做分布对齐，**推理端规范化没人系统做过**。
4. **世界模型当执行验证器**（WM 的 "outcome verification" 角色 + agent 的接管判定）——用预测器替代简单分类器做失败预警。

## 五、论文体裁定位备忘

- 单点概念基本都有人占过 → 走**系统实证 / 平台特异性 / 组合式贡献**路线。
- 可行的故事形态：「低成本 VLA 机器人在环境漂移/数据噪声下的即插即用恢复方案：系统评估 + 轻量实现」。
- 现成资产：SO-101 真机、π0.5 微调管线、48 条示范 + 6 条失败 rollout、agent 框架（`agent_loop.py` 的 `RobotFeedbackVerifier` 接口）、ManiSkill 仿真环境。
