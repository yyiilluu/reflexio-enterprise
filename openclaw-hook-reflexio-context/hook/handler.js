import { execFile } from "node:child_process";
import { resolve, join, dirname } from "node:path";
import { writeFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SCRIPT_PATH = resolve(__dirname, "..", "scripts", "fetch_context.py");

export default async function reflexioContext(event) {
  if (event.type !== "agent" || event.action !== "bootstrap") return;

  const workspaceDir = event.context?.workspaceDir;
  if (!workspaceDir) return;

  const userId = process.env.REFLEXIO_USER_ID || "openclaw";

  console.error(`[reflexio-context] bootstrap hook fired, workspace=${workspaceDir}`);

  try {
    // Fetch general user preferences at session start
    const result = await runScript(SCRIPT_PATH, userId, "general user preferences and communication style");
    const hasContext = result && result.trim() && !result.includes("Error searching");

    const lines = [
      "# Reflexio Context",
      "",
    ];

    if (hasContext) {
      lines.push(
        "## User Preferences (fetched at session start)",
        "",
        result.trim(),
        "",
      );
    }

    // Couple reflexio fetch with memory recall
    lines.push(
      "## Per-Turn Reflexio Recall (MANDATORY)",
      "",
      "Whenever you use `memory_search` or `memory_get` to recall context, you MUST also run:",
      "```",
      `python3 ${SCRIPT_PATH} --user-id ${userId} --task-query "<the user's current request>"`,
      "```",
      "This fetches task-specific improvement suggestions from Reflexio.",
      "Incorporate both memory results AND reflexio suggestions into your response.",
      "If you skip memory recall for trivial messages (greetings, acks), also skip this.",
      "",
    );

    const content = lines.join("\n");

    // Write cache file
    const contextDir = join(workspaceDir, ".reflexio-cache");
    mkdirSync(contextDir, { recursive: true });
    const contextFile = join(contextDir, "REFLEXIO_CONTEXT.md");
    writeFileSync(contextFile, content, "utf-8");

    // Inject into bootstrap files
    if (Array.isArray(event.context.bootstrapFiles)) {
      event.context.bootstrapFiles.push({
        name: "REFLEXIO_CONTEXT.md",
        path: contextFile,
        content,
        source: "hook:reflexio-context",
      });
      console.error(`[reflexio-context] injected bootstrap file (${content.length} chars)`);
    }
  } catch (err) {
    console.error(`[reflexio-context] bootstrap failed: ${err.message}`);
  }
}

function runScript(scriptPath, userId, query) {
  return new Promise((resolve, reject) => {
    execFile("python3", [
      scriptPath,
      "--user-id", userId,
      "--task-query", query.slice(0, 500),
    ], {
      timeout: 15_000,
      env: { ...process.env },
    }, (err, stdout, stderr) => {
      if (err) return reject(err);
      resolve(stdout);
    });
  });
}
