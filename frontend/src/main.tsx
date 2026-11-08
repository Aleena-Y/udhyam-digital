import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import AdminDashboard from './AdminDashboard.tsx'

const root = document.getElementById('root')!
createRoot(root).render(
  <StrictMode>
    {window.location.pathname === '/admin' ? <AdminDashboard /> : <App />}
  </StrictMode>,
)

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
  })
}
