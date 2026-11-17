import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import './nav.css';
import './auth.css';
import './review.css';
import './retry.css';
import './trend.css';

type Call = {
  id: string; original_name: string; status: string; size_bytes: number; created_at: string;
  transcript: string | null; error: string | null; operator_id: string | null;
  assessment_status: string | null;
  assessment: {overall_score:number;violations_percent:number;sentiment:string;recommendations:string[]} | null;
};
type Dashboard = {total:number;queued:number;processing:number;completed:number;failed:number;assessed:number;average_score:number|null;trends:{date:string;count:number}[]};
type AuditEvent = {id:string;actor:string;action:string;target_id:string|null;created_at:string};

function App() {
  const [calls, setCalls] = useState<Call[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [operatorId, setOperatorId] = useState('');
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [token, setToken] = useState('');
  const [role, setRole] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  async function refresh() {
    try {
      const response = await fetch('/api/calls', { headers: { Authorization: 'Bearer ' + token } });
      if (response.status === 401) { setToken(''); return; }
      if (!response.ok) throw new Error('Ошибка API');
      setCalls(await response.json());
      const summary = await fetch('/api/dashboard', { headers: { Authorization: 'Bearer ' + token } });
      if (summary.ok) setDashboard(await summary.json());
      if (role === 'admin') {
        const auditResponse = await fetch('/api/audit', { headers: { Authorization: 'Bearer ' + token } });
        if (auditResponse.ok) setAuditEvents(await auditResponse.json());
      }
    } catch (cause) { setError(String(cause)); }
  }

  useEffect(() => {
    if (!token) return;
    void refresh();
    const timer = setInterval(() => { void refresh(); }, 3000);
    return () => clearInterval(timer);
  }, [token, role]);

  async function login(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    try {
      const response = await fetch('/api/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      if (!response.ok) throw new Error('Неверное имя пользователя или пароль');
      const result = await response.json();
      setRole(result.role);
      setToken(result.token);
      setPassword('');
    } catch (cause) { setError(String(cause)); }
  }

  async function download(format: 'csv' | 'json') {
    const response = await fetch('/api/reports/' + format, { headers: { Authorization: 'Bearer ' + token } });
    if (!response.ok) { setError('Не удалось скачать отчёт'); return; }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url; link.download = 'callguard-report.' + format; link.click();
    URL.revokeObjectURL(url);
  }

  async function review(callId: string, decision: 'approved' | 'rejected') {
    const response = await fetch('/api/calls/' + callId + '/review', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision })
    });
    if (!response.ok) { setError('Не удалось сохранить проверку'); return; }
    await refresh();
  }

  async function retry(callId: string) {
    const response = await fetch('/api/calls/' + callId + '/retry', {
      method: 'POST', headers: { Authorization: 'Bearer ' + token }
    });
    if (!response.ok) { setError('Повторная обработка пока недоступна'); return; }
    await refresh();
  }

  async function reassess(callId: string) {
    const response = await fetch('/api/calls/' + callId + '/assess', {
      method: 'POST', headers: { Authorization: 'Bearer ' + token }
    });
    if (!response.ok) { setError('Повторная оценка пока недоступна'); return; }
    await refresh();
  }

  async function logout() {
    await fetch('/api/logout', { method: 'POST', headers: { Authorization: 'Bearer ' + token } });
    setToken(''); setCalls([]); setDashboard(null);
  }

  async function upload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      const data = new FormData();
      data.append('file', file);
      data.append('operator_id', operatorId);
      const response = await fetch('/api/calls', { method: 'POST', body: data,
        headers: { Authorization: 'Bearer ' + token } });
      if (!response.ok) throw new Error(await response.text());
      await refresh();
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); event.target.value = ''; }
  }

  if (!token) return <main><header><div className="brand">CallGuard AI</div></header>
    <section className="login"><h1>Вход в систему</h1>
      <form onSubmit={login}>
        <label>Имя пользователя<input type="text" value={username} onChange={e=>setUsername(e.target.value)} required/></label>
        <label>Пароль<input type="password" value={password} onChange={e=>setPassword(e.target.value)} required/></label>
        <button type="submit">Войти</button>
      </form>{error && <p className="error">{error}</p>}
    </section></main>;

  return <main>
    <header><div className="brand"><span className="brandmark">●</span><span>Центр-инвест <b>× CallGuard</b></span></div><nav><a href="#overview">Обзор</a><a href="#calls">Звонки</a><a href="#reports">Отчёты</a><button onClick={logout}>Выйти</button></nav></header>
    <div className="hero"><p className="eyebrow">КОНТРОЛЬ КАЧЕСТВА КОММУНИКАЦИЙ</p><h1>Аналитика звонков</h1><p>Загружайте записи, отслеживайте обработку и изучайте качество диалогов в одном интерфейсе.</p></div>
    <section className="metrics" id="overview">{[
      ['Всего звонков', dashboard?.total], ['Обработано', dashboard?.completed],
      ['В очереди', dashboard?.queued], ['Средняя оценка', dashboard?.average_score ?? '—']
    ].map(([label, value]) => <div className="metric" key={label}><span>{label}</span><strong>{value ?? '—'}</strong></div>)}</section>
    {dashboard && <section><h2>Звонки за 14 дней</h2><div className="trend-chart">{dashboard.trends.map(point=><div className="trend-day" key={point.date} title={point.date + ': ' + point.count}><div className="trend-bar" style={{height: Math.max(4, point.count / Math.max(1, ...dashboard.trends.map(day=>day.count)) * 100) + '%'}}/><small>{point.date.slice(5)}</small></div>)}</div></section>}
    {role !== 'viewer' && <section><h2>Загрузка аудио</h2><p>WAV, MP3 или OGG, до 100 МБ</p>
      <label>Идентификатор оператора <input type="text" value={operatorId} onChange={e=>setOperatorId(e.target.value)} maxLength={64}/></label>
      <input type="file" accept=".wav,.mp3,.ogg" onChange={upload} disabled={busy}/>
      {busy && <p>Загрузка…</p>}{error && <p className="error">{error}</p>}
    </section>}
    <section id="calls"><div className="sectionhead"><h2>Звонки <small>({calls.length})</small></h2><div id="reports">{role !== 'viewer' && <><button onClick={()=>void download('csv')}>Скачать CSV</button><button onClick={()=>void download('json')}>Скачать JSON</button></>}</div></div>
      <table><thead><tr><th>Файл</th><th>Статус</th><th>Размер</th><th>Дата</th></tr></thead>
        <tbody>{calls.map(call => <tr key={call.id}>
          <td>{call.original_name}
            {call.transcript !== null && <details><summary>Расшифровка</summary><p>{call.transcript}</p></details>}
            {call.assessment && <details><summary>Оценка: {call.assessment.overall_score}/100 ({call.assessment_status})</summary><p>Нарушения: {call.assessment.violations_percent}% · Тональность: {call.assessment.sentiment}</p><ul>{call.assessment.recommendations.map((item,i)=><li key={i}>{item}</li>)}</ul>{call.assessment_status === 'pending_review' && role !== 'viewer' && <div className="review-actions"><button onClick={()=>void review(call.id,'approved')}>Подтвердить</button><button onClick={()=>void review(call.id,'rejected')}>Отклонить</button></div>}</details>}
            {call.assessment_status === 'failed' && <p className="error">Оценка недоступна. Проверьте локальную Qwen.</p>}
            {call.assessment_status === 'failed' && call.status === 'completed' && role !== 'viewer' && <button onClick={()=>void reassess(call.id)}>Повторить оценку</button>}
            {call.error && <p className="error">{call.error}</p>}
            {call.status === 'failed' && role !== 'viewer' && <button onClick={()=>void retry(call.id)}>Повторить обработку</button>}
          </td>
          <td>{call.status}</td><td>{(call.size_bytes / 1048576).toFixed(2)} МБ</td>
          <td>{new Date(call.created_at).toLocaleString('ru-RU')}</td>
        </tr>)}</tbody>
      </table>
      {calls.length === 0 && <p>Записей пока нет.</p>}
    </section>
    {role === 'admin' && <section><h2>Журнал действий</h2><table><thead><tr><th>Время</th><th>Пользователь</th><th>Действие</th><th>Объект</th></tr></thead><tbody>{auditEvents.map(event=><tr key={event.id}><td>{new Date(event.created_at).toLocaleString('ru-RU')}</td><td>{event.actor}</td><td>{event.action}</td><td>{event.target_id ?? '—'}</td></tr>)}</tbody></table></section>}
    <footer>CallGuard AI · Локальная обработка записей</footer>
  </main>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
