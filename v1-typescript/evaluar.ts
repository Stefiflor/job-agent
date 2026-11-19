import { readFile, writeFile } from "node:fs/promises";
import { query } from "@anthropic-ai/claude-agent-sdk";

const LIMITE = Number(process.argv[2] ?? 3);  // cuántas evaluar (default 3)
const MAX_CHARS_DESC = 8000;                   // recorta descripciones largas

const cv = await readFile("private/cv-en.md", "utf8");
const criterios = JSON.parse(await readFile("private/criterios.json", "utf8"));
const candidatas = JSON.parse(await readFile("private/candidatas.json", "utf8"));

const schema = {
  type: "object",
  properties: {
    encaje: { type: "integer", minimum: 0, maximum: 100 },
    veredicto: { type: "string", enum: ["aplicar", "dudoso", "descartar"] },
    tipoPuesto: {
      type: "string",
      enum: ["ingeniería AI/LLM", "full stack / frontend", "entrenamiento de IA / gig", "otro (ventas, research, etc.)"],
    },
    elegibleUbicacion: { type: "string", enum: ["sí", "no", "no claro"] },
    salarioDetectado: { type: "string" },
    cumple: { type: "array", items: { type: "string" } },
    falta: { type: "array", items: { type: "string" } },
    redFlags: { type: "array", items: { type: "string" } },
    resumen: { type: "string" },
  },
  required: ["encaje", "veredicto", "tipoPuesto", "elegibleUbicacion", "salarioDetectado", "cumple", "falta", "redFlags", "resumen"],
};

const systemPrompt = `Sos un asesor de carrera técnico y exigente. Evaluás si una oferta remota encaja con el CV y los criterios de una candidata.
Reglas:
- Usá solo el CV, los criterios y la oferta. No inventes requisitos ni datos.
- Sé estricto: 80+ solo si cumple la mayoría de los requisitos excluyentes.
- Su inglés es B2: marcá como red flag si la oferta exige inglés nativo o C2.
- Si es trabajo de entrenamiento/evaluación de modelos (anotación, RLHF, "AI tutor") y no un puesto de ingeniería, clasificalo como "entrenamiento de IA / gig".
- Si el salario no está en los datos estructurados pero aparece en el texto, extraelo en salarioDetectado; si no hay, poné "sin dato".
- "resumen": 1-2 oraciones. Todo en español.`;

const total = Math.min(LIMITE, candidatas.length);
const resultados = [];

for (const [i, c] of candidatas.slice(0, total).entries()) {
  console.log(`(${i + 1}/${total}) ${c.titulo} | ${c.empresa}`);

  const prompt = `## CV
${cv}

## Criterios
${JSON.stringify(criterios, null, 2)}

## Oferta
Título: ${c.titulo}
Empresa: ${c.empresa}
Tipo: ${c.tipo}
Seniority: ${(c.seniority ?? []).join(", ")}
Salario (datos estructurados): ${c.salarioOriginal}${c.porHora ? " (por hora: verificá horas semanales en el texto)" : ""}
Países permitidos que coinciden con la candidata: ${c.paisesValidos.join(", ")}

Descripción:
${c.descripcion.slice(0, MAX_CHARS_DESC)}`;

  let evaluacion: any = null;
  for await (const m of query({
    prompt,
    options: { systemPrompt, allowedTools: [], outputFormat: { type: "json_schema", schema } },
  })) {
    if (m.type === "result") {
      if (m.subtype === "success" && (m as any).structured_output) evaluacion = (m as any).structured_output;
      else console.warn(`  ⚠️ falló: ${m.subtype}`);
    }
  }

  if (evaluacion) {
    const { descripcion, ...resto } = c;
    resultados.push({ ...resto, evaluacion });
    console.log(`  → ${evaluacion.veredicto} (${evaluacion.encaje}/100) · ${evaluacion.tipoPuesto} · ${evaluacion.resumen}`);
  }
}

resultados.sort((a, b) => b.evaluacion.encaje - a.evaluacion.encaje);
await writeFile("private/evaluadas.json", JSON.stringify(resultados, null, 2));
console.log(`\nGuardadas ${resultados.length} evaluaciones → private/evaluadas.json`);
