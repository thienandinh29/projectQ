// The answer keys of the grammar items, read from the item bank so a test can answer right or wrong
// on purpose. A small line parser for the YAML the project writes (no YAML dependency).
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const BANK = resolve(__dirname, "../../../data/items/english-ielts.yaml");

function unquote(text: string): string {
  const t = text.trim();
  return /^(['"]).*\1$/.test(t) ? t.slice(1, -1).replace(/''/g, "'") : t;
}

export function answerKeys(path: string = BANK): Map<string, string> {
  const keys = new Map<string, string>();
  const lines = readFileSync(path, "utf-8").split("\n");
  let id = "";
  lines.forEach((line, i) => {
    const item = line.match(/^- id: (.+)$/);
    if (item) id = unquote(item[1]);
    const option = line.match(/^ {2}- text: (.+)$/);
    if (option && lines[i + 1]?.trim() === "correct: true")
      keys.set(id, unquote(option[1]));
  });
  return keys;
}
