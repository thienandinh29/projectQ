import type { KnowledgeGraph } from "./contracts";

export function safeSourceUrl(
  value: string | undefined,
  page?: number,
): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.username ||
      url.password
    )
      return null;
    if (
      page !== undefined &&
      Number.isSafeInteger(page) &&
      page > 0 &&
      /\.pdf$/i.test(url.pathname)
    )
      url.hash = `page=${page}`;
    return url.href;
  } catch {
    return null;
  }
}

export function validateFile(
  file: Pick<File, "name" | "size">,
  maxBytes: number | null,
): "format" | "size" | "unconfigured" | null {
  if (!/\.(pdf|docx)$/i.test(file.name)) return "format";
  if (maxBytes === null) return "unconfigured";
  if (file.size === 0 || file.size > maxBytes) return "size";
  return null;
}

export function isAcyclic(graph: KnowledgeGraph): boolean {
  const degrees = new Map(graph.nodes.map((node) => [node.slug, 0]));
  for (const edge of graph.edges)
    degrees.set(edge.to, (degrees.get(edge.to) ?? 0) + 1);
  const queue = [...degrees]
    .filter(([, degree]) => degree === 0)
    .map(([slug]) => slug);
  let visited = 0;
  for (let i = 0; i < queue.length; i++) {
    const slug = queue[i];
    visited++;
    for (const edge of graph.edges)
      if (edge.from === slug) {
        const remaining = (degrees.get(edge.to) ?? 0) - 1;
        degrees.set(edge.to, remaining);
        if (remaining === 0) queue.push(edge.to);
      }
  }
  return visited === graph.nodes.length;
}
