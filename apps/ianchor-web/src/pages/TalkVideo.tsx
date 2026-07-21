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

export default function TalkVideo() {
  const [topic, setTopic] = useState('')
  const [extra, setExtra] = useState('')
  const [useLLM, setUseLLM] = useState(true)
  const [llmProvider, setLlmProvider] = useState('云端 API')
  const [script, setScript] = useState('')
  const [voice, setVoice] = useState(VOICES[0])
  const [vizMode, setVizMode] = useState('card (PPT卡片)')
  const [avatarSource, setAvatarSource] = useState('上传图片')
  const [avatarProvider, setAvatarProvider] = useState('本地 mflux')
  const [imagePreview, setImagePreview] = useState('')
  const [avatarDesc, setAvatarDesc] = useState('')
  const [logs, setLogs] = useState('')
  const [videoSrc, setVideoSrc] = useState('')
  const [loading, setLoading] = useState(false)
  const logRef = useRef('')
  const fileRef = useRef<HTMLInputElement>(null)
  const appendLog = (t: string) => { logRef.current += t; setLogs(logRef.current) }
  const isAI = avatarSource === 'AI 生成'
  const imgLabel = isAI ? '\u{1F5BC} 形象预览' : '\u{1F5BC} 口播人像'

  const handleGenerateScript = async () => {
    try { const r = await generateScript(topic, extra, useLLM); if (r.script) setScript(r.script) } catch (e: any) { alert('失败: '+e.message) }
  }
  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (f) setImagePreview(URL.createObjectURL(f))
  }
  const handleGenerate = async () => {
    if (!script.trim()) return alert('请先生成或输入口播文案')
    if (!imagePreview && avatarSource==='上传图片') return alert('请上传口播人像')
    setLoading(true); setLogs(''); setVideoSrc(''); logRef.current = ''
    try {
      const { job_id } = await generateVideo({ topic, extra, script_text: script, use_llm: useLLM, voice: voice.split(' ')[0], viz_mode: vizMode.split(' ')[0], sd_provider: 'mflux', image_path: imagePreview, animation_only: false })
      streamLogs(job_id, appendLog, () => { setVideoSrc(videoUrl(job_id)); setLoading(false) })
    } catch (e: any) { appendLog('ERROR: '+e.message); setLoading(false) }
  }

  return (
    <div className="app-container">
      <div className="page-content">
        <div className="page-layout">
          <div className="page-main">
            <div className="inner-row">
              {/* COLUMN LEFT */}
              <div className="col-left">
                <label className="g-label">📌 主题描述</label>
                <input className="g-input" value={topic} onChange={e => setTopic(e.target.value)} placeholder="如：今日股市行情解读" />

                <label className="g-label mt12">📋 附加信息</label>
                <textarea className="g-textarea" value={extra} onChange={e => setExtra(e.target.value)} placeholder="如：沪指收涨1.5%报3350点" rows={3} />

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

                <div className="mt12" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <label className="g-label" style={{ margin: 0 }}>🧑 主播形象</label>
                  <div className="pill-row">
                    <label className={`pill ${!isAI?'active':''}`}><input type="radio" name="avatarSrc" checked={!isAI} onChange={()=>setAvatarSource('上传图片')} style={{display:'none'}} />上传图片</label>
                    <label className={`pill ${isAI?'active':''}`}><input type="radio" name="avatarSrc" checked={isAI} onChange={()=>setAvatarSource('AI 生成')} style={{display:'none'}} />AI 生成</label>
                  </div>
                  <div className="pill-row" style={{ display: isAI ? 'flex' : 'none' }}>
                    <span style={{ fontSize: 12, color: '#888', marginRight: 4, alignSelf: 'center' }}>⚙️ 生成方式</span>
                    <label className={`pill ${avatarProvider==='本地 mflux'?'active':''}`}><input type="radio" name="avatarProv" checked={avatarProvider==='本地 mflux'} onChange={()=>setAvatarProvider('本地 mflux')} style={{display:'none'}} />本地 mflux</label>
                    <label className={`pill ${avatarProvider==='云端 API'?'active':''}`}><input type="radio" name="avatarProv" checked={avatarProvider==='云端 API'} onChange={()=>setAvatarProvider('云端 API')} style={{display:'none'}} />云端 API</label>
                  </div>
                </div>

                <div className="mt8" style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  {/* Image area - always visible */}
                  {imagePreview ? (
                    <div style={{ flex: 1, height: 180, border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden', background: '#f9fafb' }}>
                      <img src={imagePreview} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    </div>
                  ) : (
                    <div onClick={() => fileRef.current?.click()} style={{ flex: 1, height: 180, border: '2px dashed #d1d5db', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#9ca3af', fontSize: 13, background: '#f9fafb' }}>{imgLabel}</div>
                  )}
                  <input ref={fileRef} type="file" accept="image/*" onChange={handleImageUpload} style={{ display: 'none' }} />
                  {/* AI generation panel - slides in next to image */}
                  <div style={{ display: isAI ? 'flex' : 'none', flexDirection: 'column', gap: 6, flex: 1 }}>
                    <label className="g-label" style={{ margin: 0 }}>🎭 形象描述</label>
                    <textarea className="g-textarea" value={avatarDesc} onChange={e => setAvatarDesc(e.target.value)} placeholder="留空由 AI 根据文案设计，如：年轻男性财经主播，深色西装" rows={6} />
                    <button className="g-btn">🎨 生成形象</button>
                  </div>
                </div>
              </div>

              {/* COLUMN MIDDLE */}
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
                  {loading ? '⏳ 生成中...' : '🚀 一键生成视频'}
                </button>

                <label className="g-label mt12">🎬 视频预览</label>
                {videoSrc ? (
                  <video className="g-video" style={{ height: 280 }} src={videoSrc} controls />
                ) : (
                  <div style={{ height: 280, border: '1px solid #e5e7eb', borderRadius: 10, background: '#f9fafb', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9ca3af', fontSize: 13 }}>
                    🎬 视频预览
                  </div>
                )}

                <div className="mt12">
                  <label className="g-label">📺 Wan 片段</label>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 4, marginTop: 4 }}>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* COLUMN LOG */}
          <div className="col-log">
            <label className="g-label">📋 运行日志</label>
            <textarea className="log-console" value={logs} readOnly />
          </div>
        </div>
      </div>
    </div>
  )
}
