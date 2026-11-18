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
  segments: {start:number;end:number;text:string;role?:string;role_source?:string}[] | null;
  assessment: {overall_score:number|null;violations_percent:number|null;sentiment:string;client_sentiment?:string;operator_sentiment?:string;role_method?:string;role_counts?:Record<string,number>;sentiment_details?:{counts:Record<string,number>;evidence:{sentiment:string;quote:string;start:number|null}[]};recommendations?:string[];estimated_pause_seconds?:number;average_response_seconds?:number;response_method?:string;evidence?:{criterion:string;status:string;quote:string|null;start:number|null;end:number|null}[]} | null;
};
type Dashboard = {sentiments?:Record<string,number>;bucket_days?:number;bucket_unit?:'hour'|'day';total:number;queued:number;processing:number;completed:number;failed:number;assessed:number;average_score:number|null;operators:{operator_id:string;average_score:number|null}[];trends:{date:string;count:number;average_score:number|null}[]};
type AuditEvent = {id:string;actor:string;action:string;target_id:string|null;created_at:string};

const sentimentLabel = (s?:string) => (({positive:'Положительная',negative:'Отрицательная',neutral:'Нейтральная',unknown:'Не определена'} as Record<string,string>)[s ?? 'unknown'] ?? 'Не определена');
const roleLabel = (s?:string) => s==='operator'?'Сотрудник банка':s==='client'?'Клиент':'Роль не определена';
const utcDay = (d:Date) => d.toISOString().slice(0,10);
function periodDates(period:string, from:string, to:string):Record<string,string> {
  if(period==='all') return {};
  if(period==='custom') return {...(from?{date_from:from}:{}),...(to?{date_to:to}:{})};
  const now=new Date(); const start=new Date(now);
  start.setUTCDate(start.getUTCDate()-(({day:0,week:6,month:29,year:364} as Record<string,number>)[period] ?? 29));
  return {date_from:utcDay(start),date_to:utcDay(now)};
}
function App() {
  const [token, setToken] = useState('');
  const [calls, setCalls] = useState<Call[]>([]);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(0);
  const [period,setPeriod]=useState('month');
  const [dateFrom,setDateFrom]=useState('');
  const [dateTo,setDateTo]=useState('');
  const invalidPeriod=period==='custom' && !!dateFrom && !!dateTo && dateFrom>dateTo;
  const dates=periodDates(period,dateFrom,dateTo);
  const dateQuery=new URLSearchParams(dates).toString();
  const [selected, setSelected] = useState<Call|null>(null);
  const [audioUrl, setAudioUrl] = useState('');
  useEffect(() => {
    if (!selected || !token) return;
    let active = true; let url = '';
    setAudioUrl('');
    fetch('/api/calls/'+selected.id+'/audio', {headers:{Authorization:'Bearer '+token}})
      .then(r=>{if (!r.ok) throw new Error('Аудио недоступно'); return r.blob();})
      .then(blob=>{if(active){url=URL.createObjectURL(blob);setAudioUrl(url);}}).catch(()=>{});
    return ()=>{active=false;if(url) URL.revokeObjectURL(url);};
  }, [selected?.id, token]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [operatorId, setOperatorId] = useState('');
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [role, setRole] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  async function refresh() {
    if(invalidPeriod) {setCalls([]);setDashboard(null);return;}
    try {
      const response = await fetch('/api/calls?'+new URLSearchParams({offset:String(page*25),limit:'25',search,status,...dates}), { headers: { Authorization: 'Bearer ' + token } });
      if (response.status === 401) { setToken(''); return; }
      if (!response.ok) throw new Error('Ошибка API');
      setCalls(await response.json());
      const summary = await fetch('/api/dashboard?'+dateQuery, { headers: { Authorization: 'Bearer ' + token } });
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
  }, [token, role, page, search, status, dateQuery, invalidPeriod]);

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
    if(invalidPeriod) return;
    const response = await fetch('/api/reports/' + format+'?'+dateQuery, { headers: { Authorization: 'Bearer ' + token } });
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
    setToken(''); setSelected(null); setCalls([]); setDashboard(null);
  }

  async function upload(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;
    setBusy(true);
    setError('');
    try {
      const failures: string[] = [];
      for (const file of files) {
      const data = new FormData();
      data.append('file', file);
      data.append('operator_id', operatorId);
      const response = await fetch('/api/calls', { method: 'POST', body: data,
        headers: { Authorization: 'Bearer ' + token } });
      if (!response.ok) failures.push(file.name + ": " + await response.text());
      }
      await refresh();
      if (failures.length) setError(failures.join("; "));
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

  if (selected) {
    const call = calls.find(c=>c.id===selected.id) ?? selected;
    return <main><button onClick={()=>setSelected(null)}>← К звонкам</button><section><h1>{call.original_name}</h1><p>Оператор: {call.operator_id ?? 'не указан'} · {call.status}</p>
      {audioUrl ? <audio controls src={audioUrl} id="call-audio"/> : <p>Аудио пока недоступно</p>}
      <p>Среднее время ответа: {call.assessment?.average_response_seconds ?? 'не установлено'}; средняя пауза: {call.assessment?.estimated_pause_seconds ?? '—'} с.</p><p>{call.assessment?.response_method}</p>
      <h2>Доказательства и кандидаты на проверку</h2>{call.assessment?.evidence?.map((e,i)=><p key={i}><strong>{e.criterion}</strong> · {e.status} {e.start!==null && <button onClick={()=>{const a=document.getElementById('call-audio') as HTMLAudioElement|null;if(a&&e.start!==null)a.currentTime=e.start;}}>{e.start} с</button>} {e.quote ?? 'Не обнаружено'}</p>)}
      <h2>Тональность диалога: {sentimentLabel(call.assessment?.sentiment)}</h2>
      <p>Клиент: {sentimentLabel(call.assessment?.client_sentiment)} · Сотрудник: {sentimentLabel(call.assessment?.operator_sentiment)}. Оценка по тексту, не по интонации.</p>
      {call.assessment?.sentiment_details?.evidence.map((e,i)=><p key={i}>{sentimentLabel(e.sentiment)} · {e.start??'—'} с · {e.quote}</p>)}
      <p>{call.assessment?.role_method}</p>
      {call.assessment?.role_counts && <p>Реплик: сотрудник {call.assessment.role_counts.operator}, клиент {call.assessment.role_counts.client}, неизвестно {call.assessment.role_counts.unknown}</p>}
      {role!=='viewer' && call.status==='completed' && call.transcript && !['queued','processing'].includes(call.assessment_status??'') && <button onClick={()=>{if(window.confirm('Пересчитать оценку? Предыдущее подтверждение будет сброшено.')) void reassess(call.id);}}>Пересчитать тональность и роли</button>}
      <h2>Расшифровка</h2>{call.segments?.map((s,i)=><p key={i}><button onClick={()=>{const a=document.getElementById('call-audio') as HTMLAudioElement|null;if(a)a.currentTime=s.start;}}>{s.start.toFixed(1)} с</button> <span className={"speaker "+(s.role??"unknown")}>{roleLabel(s.role)}{s.role_source==='text'?' (оценочно)':''}</span> {s.text}</p>)}
      </section></main>;
  }
  return <main>
    <header><div className="brand"><span className="brandmark">●</span><span>Центр-инвест <b>× CallGuard</b></span></div><nav><a href="#overview">Обзор</a><a href="#calls">Звонки</a><a href="#reports">Отчёты</a><button onClick={logout}>Выйти</button></nav></header>
    <div className="hero"><p className="eyebrow">КОНТРОЛЬ КАЧЕСТВА КОММУНИКАЦИЙ</p><h1>Аналитика звонков</h1><p>Загружайте записи, отслеживайте обработку и изучайте качество диалогов в одном интерфейсе.</p></div>
    <section className="period-controls"><h2>Период аналитики</h2><label>Период <select value={period} onChange={e=>{setPeriod(e.target.value);setPage(0);}}><option value="day">За день</option><option value="week">За неделю</option><option value="month">За месяц</option><option value="year">За год</option><option value="all">За всё время</option><option value="custom">Выбрать даты</option></select></label>
    {period==='custom' && <><label>С <input type="date" value={dateFrom} onChange={e=>{setDateFrom(e.target.value);setPage(0);}}/></label><label>По <input type="date" value={dateTo} onChange={e=>{setDateTo(e.target.value);setPage(0);}}/></label></>}
    <p>По дате загрузки, UTC. {invalidPeriod?'Начальная дата позже конечной.':`${dates.date_from??'Начало'} — ${dates.date_to??'Без ограничения'}`}</p></section>
    <section className="metrics" id="overview">{[
      ['Всего звонков', dashboard?.total], ['Обработано', dashboard?.completed],
      ['В очереди', dashboard?.queued], ['Средняя оценка', dashboard?.average_score ?? '—']
    ].map(([label, value]) => <div className="metric" key={label}><span>{label}</span><strong>{value ?? '—'}</strong></div>)}</section>
    {dashboard && <section><h2>Динамика звонков</h2><div className="trend-chart">{dashboard.trends.map(point=><div className="trend-day" key={point.date} title={point.date + ': ' + point.count}><div className="trend-bar" style={{height: Math.max(0, point.count / Math.max(1, ...dashboard.trends.map(day=>day.count)) * 100) + '%'}}/><small>{dashboard.bucket_unit==='hour'?point.date.slice(11,16):point.date.slice(5)}</small></div>)}</div></section>}
    {dashboard && <section><h2>Тональность звонков (включая предварительные оценки)</h2><div className="sentiment-grid">{['positive','neutral','negative','unknown'].map(v=><div className={'sentiment-box '+v} key={v}><span>{sentimentLabel(v)}</span><strong>{dashboard.sentiments?.[v]??0}</strong></div>)}</div><p>Интервал графика: {dashboard.bucket_unit==='hour'?'1 час (UTC)':`${dashboard.bucket_days??1} дн.`}</p></section>}
    {dashboard && <section><h2>Качество и рейтинг операторов (подтверждённые оценки)</h2><p>{dashboard.trends.map(p=>(dashboard.bucket_unit==='hour'?p.date.slice(11,16):p.date.slice(5))+': '+(p.average_score ?? '—')).join(' · ')}</p>{dashboard.operators.map(o=><p key={o.operator_id}>{o.operator_id}: {o.average_score ?? '—'}/100</p>)}</section>}
    {role !== 'viewer' && <section><h2>Загрузка аудио</h2><p>WAV, MP3 или OGG, до 100 МБ</p>
      <label>Идентификатор оператора <input type="text" value={operatorId} onChange={e=>setOperatorId(e.target.value)} maxLength={64}/></label>
      <input type="file" multiple accept=".wav,.mp3,.ogg" onChange={upload} disabled={busy}/>
      {busy && <p>Загрузка…</p>}{error && <p className="error">{error}</p>}
    </section>}
    <section id="calls"><div className="sectionhead"><h2>Звонки <small>({calls.length})</small></h2><div id="reports">{role !== 'viewer' && <><button disabled={invalidPeriod} onClick={()=>void download('csv')}>Скачать CSV</button><button disabled={invalidPeriod} onClick={()=>void download('json')}>Скачать JSON</button></>}</div></div>
      <div className="sectionhead"><input aria-label="Поиск" placeholder="Файл или оператор" value={search} onChange={e=>{setSearch(e.target.value);setPage(0);}}/><select aria-label="Статус" value={status} onChange={e=>{setStatus(e.target.value);setPage(0);}}><option value="">Все статусы</option>{['queued','processing','completed','failed'].map(s=><option key={s}>{s}</option>)}</select></div>
      <table><thead><tr><th>Файл</th><th>Статус</th><th>Размер</th><th>Дата</th></tr></thead>
        <tbody>{calls.map(call => <tr key={call.id}>
          <td><button onClick={()=>setSelected(call)}>{call.original_name}</button>
            {call.transcript !== null && <details><summary>Расшифровка</summary><p>{call.transcript}</p></details>}
            {call.assessment && <details><summary>Оценка: {call.assessment.overall_score ?? "—"}/100 ({call.assessment_status})</summary><p>Нарушения: {call.assessment.violations_percent ?? "не установлено"} · Тональность: {sentimentLabel(call.assessment.sentiment)}</p><ul>{(call.assessment.recommendations ?? []).map((item,i)=><li key={i}>{item}</li>)}</ul>{call.assessment_status === 'pending_review' && role !== 'viewer' && <div className="review-actions"><button onClick={()=>void review(call.id,'approved')}>Подтвердить</button><button onClick={()=>void review(call.id,'rejected')}>Отклонить</button></div>}</details>}
            {call.assessment_status === 'failed' && <p className="error">Оценка недоступна. Проверьте журнал worker.</p>}
            {call.assessment_status === 'failed' && call.status === 'completed' && role !== 'viewer' && <button onClick={()=>void reassess(call.id)}>Повторить оценку</button>}
            {call.error && <p className="error">{call.error}</p>}
            {call.status === 'failed' && role !== 'viewer' && <button onClick={()=>void retry(call.id)}>Повторить обработку</button>}
          </td>
          <td>{call.status}</td><td>{(call.size_bytes / 1048576).toFixed(2)} МБ</td>
          <td>{new Date(call.created_at).toLocaleString('ru-RU')}</td>
        </tr>)}</tbody>
      </table>
      {calls.length === 0 && <p>Записей пока нет.</p>}
      <div className="sectionhead"><button disabled={page===0} onClick={()=>setPage(p=>p-1)}>Назад</button><span>Страница {page+1}</span><button disabled={calls.length<25} onClick={()=>setPage(p=>p+1)}>Далее</button></div>
    </section>
    {role === 'admin' && <section><h2>Журнал действий</h2><table><thead><tr><th>Время</th><th>Пользователь</th><th>Действие</th><th>Объект</th></tr></thead><tbody>{auditEvents.map(event=><tr key={event.id}><td>{new Date(event.created_at).toLocaleString('ru-RU')}</td><td>{event.actor}</td><td>{event.action}</td><td>{event.target_id ?? '—'}</td></tr>)}</tbody></table></section>}
    <footer>CallGuard AI · Локальная обработка записей</footer>
  </main>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
