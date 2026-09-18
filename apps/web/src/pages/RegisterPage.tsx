import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, UserPlus } from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext';
import { Button, Card, Field, Status } from '../components/UI';
import { errorMessage } from '../lib/api';
import type { Lang } from '../types';

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState<{ name: string; email: string; password: string; preferred_language: Lang }>({ name: '', email: '', password: '', preferred_language: 'hin_Deva' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(''); setBusy(true);
    try { await register(form); navigate('/student', { replace: true }); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  };

  return <div className="simple-auth"><Card className="register-card">
    <div className="auth-logo"><div className="brand-mark small">भा</div><BookOpen size={17} /> BhashaSaathi</div>
    <div className="auth-card-title"><div className="eyebrow">LEARNER ACCOUNT</div><h1>Create your account</h1><p>After signing in, enter your teacher's classroom code.</p></div>
    {error && <Status tone="danger">{error}</Status>}
    <form onSubmit={submit} className="auth-form">
      <Field label="Full name"><input autoComplete="name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Asha Kumar" /></Field>
      <Field label="Email"><input autoComplete="email" required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="asha@example.com" /></Field>
      <Field label="Password" hint="At least 8 characters."><input autoComplete="new-password" required minLength={8} type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
      <Field label="Preferred learning language"><select value={form.preferred_language} onChange={(e) => setForm({ ...form, preferred_language: e.target.value as Lang })}><option value="hin_Deva">हिन्दी</option><option value="sat_Olck">ᱥᱟᱱᱛᱟᱲᱤ · Santhali</option><option value="eng_Latn">English</option></select></Field>
      <Button type="submit" disabled={busy} className="full"><UserPlus size={16} />{busy ? 'Creating account…' : 'Create learner account'}</Button>
    </form>
    <button className="text-link" onClick={() => navigate('/login')}>← Back to sign in</button>
  </Card></div>;
}
