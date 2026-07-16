// Claude cites every claim inline as "(filename, chunk N)" (see backend/app/modules/
// ask/llm.py's system prompt). The filename is useful context; the internal chunk
// index isn't user-facing information, so it's dropped, keeping just "(filename)".
const CITATION_PATTERN = /\(([^()]*?),\s*chunk\s*\d+\)/gi;

export function simplifyCitations(text: string): string {
  return text.replace(CITATION_PATTERN, "($1)");
}
