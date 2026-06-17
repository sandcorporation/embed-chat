import { useState, useEffect, useRef } from 'react'
import ChatWidget from './components/ChatWidget'

function App() {
  const params = new URLSearchParams(window.location.search)
  const token = params.get('token')

  if (!token) {
    return (
      <div style={{ padding: '20px', color: '#e53e3e' }}>
        EmbedToken이 필요합니다.
      </div>
    )
  }

  return <ChatWidget embedToken={token} />
}

export default App
