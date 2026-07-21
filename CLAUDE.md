# iAnchor — Claude Code 项目规则

## 强制：每条回复末尾标注 Skill

**每条回复末尾**必须标注本条使用了哪些 skill，格式：

```
---
Skills: skill-name-a, skill-name-b
```

禁止无 skill 回复。即使没有主动加载 skill，也要指出。

## 核心规则

### 异常处理铁律
- **绝不吞异常**。所有 `except` 必须打日志 (`logger.debug/warning/error`)
- 禁止 `except: pass`、`except Exception: pass`、裸 `except:`
- 即使是不影响运行的 fallback，也要用 `logger.debug` 记录原因

### 日志铁律
- **所有子进程/异步任务必须有日志**。绝不能静默执行
- `subprocess.run`/`Popen` 要么不捕获输出（直接打到终端），要么捕获后逐行打 logger
- 禁止 `capture_output=True` 然后不打印 stdout/stderr
- 下载、生成、处理，每个阶段都要有进度日志
- **每个重要步骤必须打 logger.info**（开始、完成、PID、耗时）
- **每个 except 必须打 logger.error 或 logger.warning，带 exc_info=True**
- 禁止 `except Exception: pass` 或仅 `return False` 不记日志

### 先回答，再做事
- 用户的prompt，**先仅回答**，不要直接动手改代码
- 只有用户明确说"改"、"修"、"做"、"提交"等指令时，才执行操作
- 用户报错/异常时，先分析原因和理由，用户认可后才能改，不要急着改代码
- 用户的prompt，**先仅回答**，不要直接动手改代码
- 只有用户明确说"改"、"修"、"做"、"提交"等指令时，才执行操作

### 永远不要擅自重启 WebUI
- **绝不**自动执行 `bash stop_ui.sh` 或 `bash start_ui.sh`
- 用户可能正在跑长时间任务，重启会杀掉 pipeline

### 永远不要降级
用户选择了某个模式/选项后，必须按用户的选择执行。**绝不自动回退、降级或切换**到其他模式。

如果用户选的模式出错：
1. 诊断根因
2. 修复问题
3. 重试（最多 3 次）
4. 如果仍失败，**明确告诉用户失败原因**，让用户决定下一步

禁止的行为：
- ❌ Remotion 失败了换 card
- ❌ SD 失败了换 card
- ❌ Manim 失败了换 card
- ❌ 任何形式的静默回退

### Git 提交
- 用户没有明确说"提交"/"commit"/"push"时，**不允许**执行 git commit 或 git push
- 可以直接修改代码并重启 WebUI，但不要提交

### 异常处理铁律
- **绝不吞异常**。所有 `except` 必须打日志 (`logger.debug/warning/error`)
- 禁止 `except: pass`、`except Exception: pass`、裸 `except:`
- 即使是不影响运行的 fallback，也要用 `logger.debug` 记录原因

### Python 作用域铁律（反复犯，已致 3 次 UnboundLocalError）
- **禁止在 `if`/`try`/循环 等条件分支内 import**，然后把导入名在分支外使用
- 函数开头一次性 `import` 是安全的（执行流必然到达）
- `try: import foo except ImportError: foo = None` 且后续只用 `if foo:` 是安全的
- 写完代码后自检：分支内的 `import` 是否被分支外引用

## 代码质量铁律 — 反复问题总结

### 1. subprocess 必须 try/except
- 所有 `subprocess.run` / `Popen` 必须有 try/except
- 单个片段失败不能影响整体（如 ffmpeg 缩放/拼接嵌在循环里要 continue）
- 注意 `check=True` 时 `calledProcessError` 只是异常子类，`FileNotFoundError` 也要捕获

### 2. 文件写入必须 try/except
- `open(path, "w")` / `os.makedirs` / `os.replace` 都要包
- 临时配置文件用 `tempfile.mkdtemp()` 生成唯一路径，用完清理

### 3. 函数内条件 import 要在块外用
- 禁止 if/try/循环内 import，然后在块外使用
- 函数开头统一 import 是安全的

### 4. 模块级 import 要全
- `random`、`json`、`shutil`、`subprocess` 等常用模块如被使用必须有顶层 import
- 每次改完代码检查 import 是否齐全

### 5. 配置写入避免覆盖用户值
- 修改 config.yaml 时不要用包含整段的 oldString
- 只改具体行，保留用户自己填的值

### 6. Wan2.1 相关
- 1.3B 最大 81 帧 (5 秒)
- prompts 只支持英文
- 分组策略：按累计时长 ≥ 5s 切组，不要固定句数
- drawtext 特殊字符要转义 (`:`, `%`, `'`)
- batch 脚本每次重写，不要检查是否存在就跳过

### 7. 永远不要擅自替换实现
- 用户选了某个 provider/模式后，必须保留原有实现，新增选项而非替换
- mflux、FLUX、SD 是三个独立的出图后端，不能互相替换
- 加新功能用配置项控制，不要删旧代码

### 8. 永远不要降级
用户选择了某个模式/选项后，必须按用户的选择执行。**绝不自动回退、降级或切换**到其他模式。

如果用户选的模式出错：
1. 诊断根因
2. 修复问题
3. 重试（最多 3 次）
4. 如果仍失败，**明确告诉用户失败原因**，让用户决定下一步

禁止的行为：
- ❌ Remotion 失败了换 card
- ❌ SD 失败了换 card
- ❌ Manim 失败了换 card
- ❌ mflux 失败了换 FLUX
- ❌ FLUX 失败了换 mflux
- ❌ 任何形式的静默回退

### 8. 实现前先问
- 改动涉及多后端时，先确认用户要哪个方案
- 不要擅自改 config.yaml 覆盖用户值

---

# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- If you write 200 lines and it could be 50, rewrite it.

## 3. Surgical Changes

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

## 4. Goal-Driven Execution

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

---

**These guidelines are working if:** fewer unnecessary changes, fewer rewrites, and clarifying questions come before implementation rather than after mistakes.
