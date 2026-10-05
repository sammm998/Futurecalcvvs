/* The question "which AI model reads this?", asked before an analysis starts. api.analyze asks it; the dialog in
 * the app frame (components/AiModelDialog) answers it. Kept free of imports so both can use it. */
export const AI_MODEL_KEY = "fc.aiModel";

type Ask = (count: number) => Promise<string | null>;
let asker: Ask | null = null;

export function registerAiModelAsker(fn: Ask | null) { asker = fn; }

export function lastAiModel(): string | null {
  try { return localStorage.getItem(AI_MODEL_KEY); } catch { return null; }
}

export function rememberAiModel(id: string) {
  try { localStorage.setItem(AI_MODEL_KEY, id); } catch { /* utan lagring frågas det varje gång */ }
}

/** The model the next analysis (or `count` analyses) is read with; null when the person closed the question. */
export async function askAiModel(count = 1): Promise<string | null> {
  if (!asker) return lastAiModel() ?? "none";
  return asker(count);
}
