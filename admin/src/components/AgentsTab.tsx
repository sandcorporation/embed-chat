import { useState, useEffect, FormEvent } from 'react'
import { listAgents, createAgent, changeAgentRole, deactivateAgent, changePassword, currentAgentRole } from '../api'
import { HttpError } from '../mutator'
import type { AgentOut } from '../generated/model'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'

const ROLE_LABEL: Record<string, string> = { admin: 'Admin', member: 'Member' }

export default function AgentsTab() {
  const isAdmin = currentAgentRole() === 'admin'
  const [agents, setAgents] = useState<AgentOut[]>([])
  const [newUsername, setNewUsername] = useState('')
  const [newRole, setNewRole] = useState<'admin' | 'member'>('member')
  const [createdCred, setCreatedCred] = useState<{ username: string; password: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [pwForm, setPwForm] = useState({ current: '', next: '', error: '', success: false })

  const load = async () => setAgents(await listAgents())

  useEffect(() => { load() }, [])

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    if (!newUsername.trim()) return
    setLoading(true)
    const data = await createAgent(newUsername.trim(), newRole)
    setCreatedCred({ username: data.username, password: data.temp_password })
    setNewUsername('')
    await load()
    setLoading(false)
  }

  const handleRole = async (a: AgentOut, role: 'admin' | 'member') => {
    setError('')
    try {
      await changeAgentRole(a.id, role)
      await load()
    } catch (e) {
      setError(e instanceof HttpError && e.status === 409 ? '마지막 Admin은 강등할 수 없습니다.' : '역할 변경에 실패했습니다.')
    }
  }

  const handleDeactivate = async (id: string) => {
    if (!confirm('비활성화하시겠습니까?')) return
    setError('')
    try {
      await deactivateAgent(id)
      await load()
    } catch (e) {
      setError(e instanceof HttpError && e.status === 409 ? '마지막 Admin은 비활성화할 수 없습니다.' : '비활성화에 실패했습니다.')
    }
  }

  const handleChangePassword = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await changePassword(pwForm.current, pwForm.next)
      setPwForm({ current: '', next: '', error: '', success: true })
      setTimeout(() => setPwForm(f => ({ ...f, success: false })), 2000)
    } catch (err) {
      setPwForm(f => ({ ...f, error: err instanceof Error ? err.message : String(err) }))
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      {createdCred && (
        <Card className="border-amber-300 bg-amber-50 dark:bg-amber-950/30">
          <CardContent className="flex items-center gap-2 pt-5 text-sm">
            <span><strong>{createdCred.username}</strong> 계정이 생성되었습니다. 임시 비밀번호 (1회만 표시): <code className="rounded bg-muted px-1 py-0.5 text-xs">{createdCred.password}</code></span>
            <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setCreatedCred(null)}>✕</Button>
          </CardContent>
        </Card>
      )}

      {isAdmin && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold">팀원 추가</h2>
          <form onSubmit={handleCreate} className="flex gap-2">
            <Input className="flex-1" placeholder="사용자명" value={newUsername} onChange={e => setNewUsername(e.target.value)} />
            <select className="rounded-md border border-input bg-background px-2 text-sm" value={newRole}
              onChange={e => setNewRole(e.target.value as 'admin' | 'member')} aria-label="역할">
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
            <Button type="submit" disabled={loading}>추가</Button>
          </form>
        </div>
      )}

      <div className="space-y-2">
        <h2 className="text-sm font-semibold">팀원 목록</h2>
        {error && <p className="text-sm text-destructive">{error}</p>}
        {!isAdmin && <p className="text-xs text-muted-foreground">팀원 관리는 Admin만 할 수 있습니다.</p>}
        <Table>
          <TableHeader>
            <TableRow><TableHead>사용자명</TableHead><TableHead>역할</TableHead><TableHead>상태</TableHead>{isAdmin && <TableHead>작업</TableHead>}</TableRow>
          </TableHeader>
          <TableBody>
            {agents.map(a => (
              <TableRow key={a.id}>
                <TableCell>{a.username}</TableCell>
                <TableCell><Badge variant={a.role === 'admin' ? 'default' : 'secondary'}>{ROLE_LABEL[a.role] || a.role}</Badge></TableCell>
                <TableCell><Badge variant={a.is_active ? 'success' : 'secondary'}>{a.is_active ? '활성' : '비활성'}</Badge></TableCell>
                {isAdmin && (
                  <TableCell className="flex gap-2">
                    {a.is_active && (
                      <Button size="sm" variant="outline" onClick={() => handleRole(a, a.role === 'admin' ? 'member' : 'admin')}>
                        {a.role === 'admin' ? 'Member로' : 'Admin으로'}
                      </Button>
                    )}
                    {a.is_active && <Button size="sm" variant="destructive" onClick={() => handleDeactivate(a.id)}>비활성화</Button>}
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="space-y-2">
        <h2 className="text-sm font-semibold">내 비밀번호 변경</h2>
        <form onSubmit={handleChangePassword} className="flex max-w-sm flex-col gap-2">
          <Input type="password" placeholder="현재 비밀번호" value={pwForm.current} onChange={e => setPwForm(f => ({ ...f, current: e.target.value }))} />
          <Input type="password" placeholder="새 비밀번호" value={pwForm.next} onChange={e => setPwForm(f => ({ ...f, next: e.target.value }))} />
          {pwForm.error && <p className="text-sm text-destructive">{pwForm.error}</p>}
          <Button type="submit" className="self-start">{pwForm.success ? '✓ 변경됨' : '변경'}</Button>
        </form>
      </div>
    </div>
  )
}
