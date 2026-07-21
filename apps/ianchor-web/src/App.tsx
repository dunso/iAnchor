import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import NavHeader from './components/NavHeader'
import TalkVideo from './pages/TalkVideo'
import AnimVideo from './pages/AnimVideo'

export default function App() {
  return (
    <BrowserRouter>
      <NavHeader />
      <Routes>
        <Route path="/talk" element={<TalkVideo />} />
        <Route path="/anim" element={<AnimVideo />} />
        <Route path="*" element={<Navigate to="/talk" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
