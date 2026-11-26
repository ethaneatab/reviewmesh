import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { saveSession, session } from './api'
import Login from './pages/Login'
import Queue from './pages/Queue'
import RecordPage from './pages/Record'
import Ring from './pages/Ring'
import Rollout from './pages/Rollout'
import Learn from './pages/Learn'
import Ops from './pages/Ops'

export default function App() {
  const s = session()
  const nav = useNavigate()
  return (
    <>
      <header className="topbar">
        <div className="brand">review<span>mesh</span></div>
        <nav>
          <NavLink to="/queue">审核队列</NavLink>
          <NavLink to="/ring">哈希环</NavLink>
          <NavLink to="/rollout">发布控制台</NavLink>
          <NavLink to="/ops">运维</NavLink>
          <NavLink to="/learn">教学</NavLink>
        </nav>
        <div className="who">
          {s ? (
            <>
              <span data-testid="who">{s.display_name}</span>
              <button onClick={() => { saveSession(null); nav('/login') }}>退出</button>
            </>
          ) : (
            <NavLink to="/login">登录</NavLink>
          )}
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/queue" replace />} />
          <Route path="/login" element={<Login />} />
          <Route path="/queue" element={<Queue />} />
          <Route path="/records/:id" element={<RecordPage />} />
          <Route path="/ring" element={<Ring />} />
          <Route path="/rollout" element={<Rollout />} />
          <Route path="/ops" element={<Ops />} />
          <Route path="/learn/*" element={<Learn />} />
        </Routes>
      </main>
    </>
  )
}
