import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../api'

export default function Login() {
  const [username, setUsername] = useState('rita')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const nav = useNavigate()
  return (
    <form
      className="card login"
      onSubmit={async (e) => {
        e.preventDefault()
        setErr('')
        try {
          await login(username, password)
          nav('/queue')
        } catch (x) {
          setErr((x as Error).message)
        }
      }}
    >
      <h1>审核员登录</h1>
      <label htmlFor="u">用户名</label>
      <input id="u" name="username" value={username} onChange={(e) => setUsername(e.target.value)} />
      <label htmlFor="p">密码</label>
      <input id="p" name="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <div className="row" style={{ marginTop: 14 }}>
        <button className="primary" type="submit">登录</button>
        {err && <span className="err">{err}</span>}
      </div>
      <p className="muted" style={{ fontSize: 12 }}>本地演示账号（RM_SEED_DEMO=1 时创建）：rita / sam / olive，密码是「用户名-demo」。</p>
    </form>
  )
}
