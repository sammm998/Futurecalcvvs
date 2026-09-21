/* Academys API-klient.
 *
 * Egen fil i stället för en klump i den stora: utbildningen är ett eget delsystem med egna vägar, och det som
 * skiljer den från resten - att svaren aldrig innehåller facit - är lättare att lita på när alla anrop står
 * på samma ställe.
 */

async function call(path: string, init: RequestInit = {}): Promise<any> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  const tok = localStorage.getItem("vvs_token");
  if (tok) headers["Authorization"] = `Bearer ${tok}`;
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401) {
    localStorage.removeItem("vvs_token");
    window.location.href = "/login";
    throw new Error("Ej inloggad");
  }
  if (!res.ok) {
    let msg = res.statusText || `Fel ${res.status}`;
    try { const j = await res.json(); if (typeof j.detail === "string") msg = j.detail; } catch { /* inte JSON */ }
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

const post = (p: string, body?: unknown) =>
  call(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });

export const ac = {
  /* Katalogen utifrån. Öppen: den som väljer en utbildning har rätt att se vad den innehåller innan hen
     skaffar ett konto, och en sida som räknar kurserna själv räknar fel så fort någon lägger till en. */
  catalogue: () => call("/api/public/academy"),
  courses: () => call("/api/academy/courses"),
  course: (slug: string) => call(`/api/academy/courses/${slug}`),
  plan: (slug: string) => call(`/api/academy/plan/${slug}`),
  lesson: (id: string) => call(`/api/academy/lessons/${id}`),
  lessonDone: (id: string) => post(`/api/academy/lessons/${id}/klar`),
  attempt: (slug: string, given: unknown) => post(`/api/academy/exercises/${slug}/forsok`, { given }),
  quiz: (course: string, mod: string, n = 6) => call(`/api/academy/modules/${course}/${mod}/quiz?n=${n}`),
  quizSubmit: (course: string, mod: string, svar: unknown, order: unknown) =>
    post(`/api/academy/modules/${course}/${mod}/quiz`, { svar, order }),
  me: () => call("/api/academy/me"),
  examStart: (slug: string) => post(`/api/academy/exams/${slug}/start`),
  examGet: (id: string) => call(`/api/academy/exams/attempt/${id}`),
  examSave: (id: string, ref: string, given: unknown) =>
    call(`/api/academy/exams/attempt/${id}/svar`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ref, given }),
    }),
  examSubmit: (id: string) => post(`/api/academy/exams/attempt/${id}/lamna-in`),
  certificates: () => call("/api/academy/certificates"),
  verify: (code: string) => call(`/api/public/certificate/${encodeURIComponent(code)}`),
  adminTree: () => call("/api/admin/academy/tree"),
  adminPatch: (what: string, id: string, faltet: Record<string, unknown>) =>
    call(`/api/admin/academy/${what}/${id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ faltet }),
    }),
  adminSeed: () => post("/api/admin/academy/seed"),
};

/* ---------------------------------------------------------------- typerna gränssnittet räknar med */

export type Block =
  | { k: "p"; t: string } | { k: "h"; t: string } | { k: "ul"; t: string[] }
  | { k: "terms"; t: [string, string][] } | { k: "note"; t: string } | { k: "warn"; t: string }
  | { k: "formula"; t: string; why: string } | { k: "drawing"; plan: string; caption: string };

export type PlanData = {
  plan: string; title: string; m_per_unit: number; view: number[];
  walls: number[][][];
  runs: { id: string; sys: string; dn: number; label: string; d: string; m: number }[];
  symbols: { id: string; kind: string; x: number; y: number; name: string; rot: number }[];
  rooms: { name: string; x: number; y: number; w: number; h: number }[];
  names: Record<string, string>;
  highlight_sys?: string; highlight_dn?: number; pick?: string; focus?: string;
  options?: string[]; poster?: { key: string; label: string; unit: string }[];
};

export type ExerciseOut = {
  slug: string; kind: string; title: string; instructions: string; difficulty: number;
  data: Record<string, any>; points: number; tolerance_pct: number; hints: string[];
  max_attempts: number; reveal_after: number; attempts: number; best: number; passed: boolean;
};

export type AttemptOut = {
  score: number; passed: boolean; feedback: Record<string, any>;
  forsok: number; xp: number; xp_totalt: number; losning?: string; ledtrad?: string;
};
