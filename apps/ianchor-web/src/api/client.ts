const BASE = '/api'

export async function generateScript(topic: string, extra: string, useLLM: boolean) {
  const params = new URLSearchParams({ topic, extra, use_llm: String(useLLM) })
  const r = await fetch(`${BASE}/script?${params}`, { method: 'POST' })
  return r.json()
}

export async function generateVideo(params: {
  topic: string; extra: string; script_text: string;
  use_llm: boolean; voice: string; viz_mode: string;
  sd_provider: string; image_path: string; animation_only: boolean;
}) {
  const r = await fetch(`${BASE}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  return r.json() as Promise<{ job_id: string }>
}

export function streamLogs(jobId: string, onLog: (text: string) => void, onDone: () => void) {
  const es = new EventSource(`${BASE}/logs/${jobId}`)
  es.onmessage = (e) => {
    const data = JSON.parse(e.data)
    if (data.text) onLog(data.text)
    else onDone()
  }
  es.onerror = () => { es.close(); onDone() }
  return es
}

export function videoUrl(jobId: string) {
  return `${BASE}/video/${jobId}`
}
