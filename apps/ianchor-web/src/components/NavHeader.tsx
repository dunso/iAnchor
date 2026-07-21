import { NavLink } from 'react-router-dom'

export default function NavHeader() {
  return (
    <div className="app-header">
      <span className="app-logo">🎬 iAnchor — AI 口播视频生成</span>
      <nav className="app-nav">
        <NavLink to="/talk" className={({ isActive }) => isActive ? 'active' : ''}>📺 口播视频</NavLink>
        <NavLink to="/anim" className={({ isActive }) => isActive ? 'active' : ''}>🎬 动画视频</NavLink>
      </nav>
    </div>
  )
}
