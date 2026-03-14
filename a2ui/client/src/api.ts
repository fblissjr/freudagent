/**
 * HTTP client for the FreudAgent A2UI backend.
 */

export interface ComposeResult {
  valid: boolean;
  messages?: any[];
  errors?: string[];
  provider?: string;
  model?: string;
  tokens?: { input: number; output: number };
  error?: string;
}

export interface ActionResult {
  success: boolean;
  messages?: any[];
  error?: string;
}

export async function compose(
  surface: string,
  params: Record<string, any> = {},
  provider: string = "echo",
  description?: string,
): Promise<ComposeResult> {
  const body: any = { surface, params, provider };
  if (description) body.description = description;

  const resp = await fetch("/api/compose", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return resp.json();
}

export async function sendAction(action: {
  name: string;
  context: Record<string, any>;
}): Promise<ActionResult> {
  const resp = await fetch("/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
  return resp.json();
}
