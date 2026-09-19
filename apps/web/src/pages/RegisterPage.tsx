import { FormEvent, useState } from 'react';
import { BookOpen, GraduationCap, Languages, School, UserPlus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthContext';
import { Button, Card, Field, Status } from '../components/UI';
import { errorMessage } from '../lib/api';
import type { Lang, Role } from '../types';

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState<{ name: string; email: string; password: string; preferred_language: Lang; account_role: Role }>({
    name: '', email: '', password: '', preferred_language: 'hin_Deva', account_role: 'student',
  });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(''); setBusy(true);
    try {
      const user = await register(form);
      navigate(user.account_role === 'admin' ? '/dashboard' : '/student', { replace: true });
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  };

  return <div className="simple-auth"><Card className="register-card">
    <div className="auth-logo"><div className="brand-mark small">भा</div><BookOpen size={17} /> BhashaSaathi</div>
    <div className="auth-card-title"><div className="eyebrow">GET STARTED</div><h1>Create your account</h1><p>Choose how you want to use BhashaSaathi. You can join classrooms after creating your account.</p></div>
    {error && <Status tone="danger">{error}</Status>}
    <form onSubmit={submit} className="auth-form">
      <Field label="I want to use BhashaSaathi as">
        <div className="role-choice-grid">
          <button type="button" className={`role-choice ${form.account_role === 'admin' ? 'selected' : ''}`} onClick={() => setForm({ ...form, account_role: 'admin' })}>
            <span className="role-choice-icon"><School size={20} /></span><strong>Creator / Educator</strong><small>Create classrooms, build lessons and approve AI content.</small>
          </button>
          <button type="button" className={`role-choice ${form.account_role === 'student' ? 'selected' : ''}`} onClick={() => setForm({ ...form, account_role: 'student' })}>
            <span className="role-choice-icon"><GraduationCap size={20} /></span><strong>Student / Learner</strong><small>Join classrooms, learn, practice and use lessons offline.</small>
          </button>
        </div>
      </Field>
      <Field label="Full name"><input autoComplete="name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Asha Kumar" /></Field>
      <Field label="Email"><input autoComplete="email" required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="asha@example.com" /></Field>
      <Field label="Password" hint="At least 8 characters."><input autoComplete="new-password" required minLength={8} type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
      <Field label="Preferred language"><select value={form.preferred_language} onChange={(e) => setForm({ ...form, preferred_language: e.target.value as Lang })}><option value="hin_Deva">हिन्दी · Hindi</option><option value="sat_Olck">ᱥᱟᱱᱛᱟᱲᱤ · Santhali</option><option value="eng_Latn">English</option></select></Field>
      <Button type="submit" disabled={busy} className="full"><UserPlus size={16} />{busy ? 'Creating account…' : `Create ${form.account_role === 'admin' ? 'creator' : 'student'} account`}</Button>
    </form>
    <div className="language-note"><Languages size={15} /><span>You can change your preferred language later from the workspace.</span></div>
    <button className="text-link" onClick={() => navigate('/login')}>← Back to sign in</button>
  </Card></div>;
}
