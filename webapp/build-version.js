import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// The version the app displays is the Python package's, bumped by
// scripts/verup.sh — never a second number the frontend keeps for itself.
const ABOUT = fileURLToPath(new URL("../src/echo_words/__about__.py", import.meta.url));

export function readAppVersion() {
  try {
    const match = /__version__\s*=\s*"([^"]+)"/u.exec(readFileSync(ABOUT, "utf8"));
    return match ? match[1] : "dev";
  } catch {
    return "dev";
  }
}
