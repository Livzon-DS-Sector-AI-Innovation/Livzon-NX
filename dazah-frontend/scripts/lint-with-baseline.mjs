import { readFile } from "node:fs/promises";
import { ESLint } from "eslint";

const baselineUrl = new URL("../eslint-warning-baseline.json", import.meta.url);
const baseline = JSON.parse(await readFile(baselineUrl, "utf8"));
const eslint = new ESLint();
const results = await eslint.lintFiles(["."]);
const formatter = await eslint.loadFormatter("stylish");
const formatted = formatter.format(results);

if (formatted) {
  process.stdout.write(formatted);
}

const warningCounts = new Map();
let warningTotal = 0;
let errorTotal = 0;

for (const result of results) {
  for (const message of result.messages) {
    if (message.severity === 2) {
      errorTotal += 1;
      continue;
    }
    if (message.severity !== 1) {
      continue;
    }

    warningTotal += 1;
    const ruleId = message.ruleId ?? "<unclassified>";
    warningCounts.set(ruleId, (warningCounts.get(ruleId) ?? 0) + 1);
  }
}

const increases = [];
for (const [ruleId, count] of warningCounts) {
  const allowed = baseline.rules[ruleId] ?? 0;
  if (count > allowed) {
    increases.push(`${ruleId}: ${count} > ${allowed}`);
  }
}

if (warningTotal > baseline.total) {
  increases.push(`total: ${warningTotal} > ${baseline.total}`);
}

process.stdout.write(
  `\nESLint warning baseline: ${warningTotal}/${baseline.total}; errors: ${errorTotal}\n`,
);

if (increases.length > 0) {
  process.stderr.write(
    `New ESLint warnings are not allowed:\n${increases
      .map((item) => `- ${item}`)
      .join("\n")}\n`,
  );
}

process.exitCode = errorTotal > 0 || increases.length > 0 ? 1 : 0;
