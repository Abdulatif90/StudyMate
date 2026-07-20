import type { components } from "@/lib/api/schema";

type ResearchSource = components["schemas"]["ResearchSource"];

/** Display label for a research source: its title, falling back to the raw URL
 * when the backend returns an empty/blank title (e.g. a page with no `<title>`). */
export function researchSourceLabel(source: ResearchSource): string {
  const title = source.title.trim();
  return title.length > 0 ? title : source.url;
}
