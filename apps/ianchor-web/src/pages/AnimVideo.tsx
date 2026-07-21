import { useState, useRef } from 'react'
import { generateScript, generateVideo, streamLogs, videoUrl } from '../api/client'

const VOICES = [
  'zh-CN-YunyangNeural (M News)', 'zh-CN-YunxiNeural (M Sunny)', 'zh-CN-XiaoxiaoNeural (F News)',
  'zh-CN-YunjianNeural (M Sports)', 'zh-CN-YunxiaNeural (M Cartoon)', 'zh-CN-XiaoyiNeural (F Cartoon)',
  'v2/zh_speaker_0 (Bark M0)', 'v2/zh_speaker_1 (Bark M1)', 'v2/zh_speaker_2 (Bark M2)',
  'v2/zh_speaker_3 (Bark F3)', 'v2/zh_speaker_4 (Bark F4)', 'v2/zh_speaker_5 (Bark M5)',
  'v2/zh_speaker_6 (Bark F6)', 'v2/zh_speaker_7 (Bark F7)', 'v2/zh_speaker_8 (Bark M8)', 'v2/zh_speaker_9 (Bark F9)',
]
const VIZ_MODES = [
  'card (PPT卡片)', 'sd (mflux文生图)', 'sd (flux文生图)', 'manim (数字动画)',
  'manim_comic (漫画分镜)', 'wan (本地AI视频)', 'wan_api (Replicate)', 'bailian (阿里百炼)', 'remotion (React动画)',
]

export default function AnimVideo() {
  const [topic, setTopic] = useState('')
  const [extra, setExtra] = useState('')
  const [useLLM, setUseLLM] = useState(true)
  const [llmProvider, setLlmProvider] = useState('云端 API')
  const [script, setScript] = useState('')
  const [voice, setVoice] = useState(VOICES[0])
  const [vizMode, setVizMode] = useState('manim (数字动画)')
  const [logs, setLogs] = useState('')
  const [videoSrc, setVideoSrc] = useState('')
  const [loading, setLoading] = useState(false)
  const logRef = useRef('')
  const appendLog = (t: string) => { logRef.current += t; setLogs(logRef.current) }

  const handleGenerateScript = async () => {
    try { const r = await generateScript(topic, extra, useLLM); if (r.script) setScript(r.script) } catch (e: any) { alert('失败: '+e.message) }
  }
  const handleGenerate = async () => {
    if (!script.trim()) return alert('请先生成或输入口播文案')
    setLoading(true); setLogs(''); setVideoSrc(''); logRef.current = ''
    try {
      const { job_id } = await generateVideo({ topic, extra, script_text: script, use_llm: useLLM, voice: voice.split(' ')[0], viz_mode: vizMode.split(' ')[0], sd_provider: 'mflux', image_path: '', animation_only: true })
      streamLogs(job_id, appendLog, () => { setVideoSrc(videoUrl(job_id)); setLoading(false) })
    } catch (e: any) { appendLog('ERROR: '+e.message); setLoading(false) }
  }

  return (
    <div className="app-container">
      <div className="page-content">
        <div className="page-layout">
          <div className="page-main">
            <div className="inner-row">
              <div className="col-left">
                <label className="g-label">📌 主题描述</label>
                <input className="g-input" value={topic} onChange={e => setTopic(e.target.value)} placeholder="如：宇宙大爆炸科普" />
                <label className="g-label mt12">📋 附加信息</label>
                <textarea className="g-textarea" value={extra} onChange={e => setExtra(e.target.value)} placeholder="如：从奇点到星系形成" rows={3} />
                <div className="llm-row mt12">
                  <div className="llm-top">
                    <label className="g-check"><input type="checkbox" checked={useLLM} onChange={e => setUseLLM(e.target.checked)} />🤖 调用 AI 生成文案</label>
                    <div className="pill-row" style={{ marginLeft: 'auto' }}>
                      <label className={`pill ${llmProvider==='云端 API'?'active':''}`}><input type="radio" name="llm" checked={llmProvider==='云端 API'} onChange={()=>setLlmProvider('云端 API')} style={{display:'none'}} />云端 API</label>
                      <label className={`pill ${llmProvider==='本地 Ollama'?'active':''}`}><input type="radio" name="llm" checked={llmProvider==='本地 Ollama'} onChange={()=>setLlmProvider('本地 Ollama')} style={{display:'none'}} />本地 Ollama</label>
                    </div>
                  </div>
                  <button className="g-btn" onClick={handleGenerateScript} style={{ alignSelf: 'flex-end' }}>✍️ 生成文案</button>
                </div>
                <label className="g-label mt12">📄 口播文案</label>
                <textarea className="g-textarea" value={script} onChange={e => setScript(e.target.value)} placeholder="点击上方按钮生成，或直接粘贴..." rows={6} style={{ minHeight: 120 }} />
              </div>
              <div className="col-mid">
                <label className="g-label">🎤 音色选择</label>
                <select className="g-select" value={voice} onChange={e => setVoice(e.target.value)}>
                  {VOICES.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
                <button className="g-btn mt8" style={{ width: '100%' }}>🔊 试听</button>
                <div className="audio-box mt12">🔊 试听音频</div>
                <label className="g-label mt12">🎨 动画模式</label>
                <select className="g-select" value={vizMode} onChange={e => setVizMode(e.target.value)}>
                  {VIZ_MODES.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
                <button className="g-btn g-btn-block mt24" onClick={handleGenerate} disabled={loading}>
                  {loading ? '⏳ 生成中...' : '🎬 生成动画视频'}
                </button>
                <label className="g-label mt12">🎬 视频预览</label>
                {videoSrc ? (
                  <video className="g-video" style={{ height: 280 }} src={videoSrc} controls />
                ) : (
                  <div style={{ height: 280, border: '1px solid #e5e7eb', borderRadius: 10, background: '#f9fafb', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9ca3af', fontSize: 13 }}>🎬 视频预览</div>
                )}
              </div>
            </div>
          </div>
          <div className="col-log">
            <label className="g-label">📋 运行日志</label>
            <textarea className="log-console" value={logs} readOnly />
          </div>
        </div>
      </div>
    </div>
  )
}
