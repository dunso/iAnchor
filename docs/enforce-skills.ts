/**
 * opencode plugin: 强制执行技能路由
 *
 * 分级校验:
 *   edit / write → 必须有 java-coding-standards + 至少一个其他 skill
 *   其他 gated 工具 → 至少一个有效 skill
 */
import type { Plugin } from "@opencode-ai/plugin"
import { readdirSync, existsSync } from "node:fs"
import { join } from "node:path"
import { homedir } from "node:os"

const SKILL_DIRS = [
  join(homedir(), ".agents", "skills"),
  join(homedir(), ".config", "opencode", "skills"),
]

function discoverSkills(): Set<string> {
  const skills = new Set<string>()
  for (const dir of SKILL_DIRS) {
    if (!existsSync(dir)) continue
    try {
      const entries = readdirSync(dir, { withFileTypes: true })
      for (const entry of entries) {
        if (entry.isDirectory()) {
          skills.add(entry.name)
        }
      }
    } catch { /* 权限问题跳过 */ }
  }
  return skills
}

const VALID_SKILLS = discoverSkills()

const GATED_TOOLS = ["bash", "edit", "glob", "grep", "question", "task", "todowrite", "webfetch", "write"]

const CODE_TOOLS = ["edit", "write"]

function loaded(skills: Set<string>, name: string): boolean {
  return skills.has(name) && VALID_SKILLS.has(name)
}

function missing(names: string[], skills: Set<string>): string[] {
  return names.filter((n) => !loaded(skills, n))
}

export default (async () => {
  const loadedSkills = new Set<string>()

  return {
    "tool.execute.after": async (input) => {
      if (input.tool === "skill") {
        const name = input.args?.name
        if (name) loadedSkills.add(name)
      }
    },

    "tool.execute.before": async (input) => {
      const tool = input.tool
      if (!GATED_TOOLS.includes(tool)) return
      if (VALID_SKILLS.size === 0) return

      const loadedNames = [...loadedSkills].filter((s) => VALID_SKILLS.has(s))

      // ======== 代码修改工具: 必须 java-coding-standards ========
      if (CODE_TOOLS.includes(tool)) {
        const need = missing(["java-coding-standards"], loadedSkills)
        if (need.length > 0) {
          throw new Error([
            `❌ ${tool} 必须加载 java-coding-standards`,
            `当前已加载: ${loadedNames.join(", ") || "(无)"}`,
            "请调用 skill 工具加载 java-coding-standards",
          ].join("\n"))
        }
        // 至少再有一个 context skill
        const ctxSkills = ["systematic-debugging", "brainstorming"]
        const hasCtx = ctxSkills.some((s) => loaded(s, loadedSkills))
        if (!hasCtx) {
          throw new Error([
            `❌ ${tool} 还需加载上下文 skill`,
            `当前已加载: ${loadedNames.join(", ") || "(无)"}`,
            "请调用 skill 工具加载:",
            "  - 修 bug → systematic-debugging",
            "  - 新功能 → brainstorming",
          ].join("\n"))
        }
        return
      }

      // ======== 其他工具: 至少一个有效 skill ========
      if (loadedNames.length === 0) {
        throw new Error([
          "❌ 技能路由违规: 必须加载至少一个 skill",
          "",
          `当前已加载: (无)`,
          "",
          "请先调用 skill 工具加载对应技能。",
          "  - 修 bug       → systematic-debugging",
          "  - 新功能/设计   → brainstorming",
          "  - 改代码        → java-coding-standards",
        ].join("\n"))
      }
    },
  }
}) satisfies Plugin
