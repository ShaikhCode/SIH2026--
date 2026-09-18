import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, CheckCircle2, Download, Headphones, RefreshCw, Volume2, Wifi, WifiOff } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { Page, SectionTitle } from '../components/Shell';
import { Button, Card, Status, useToast } from '../components/UI';
import { api, errorMessage } from '../lib/api';
import { get, put } from '../lib/idb';
import { queueAttempt, syncNow } from '../lib/sync';
import type { Lang, LessonPack } from '../types';
import { useAuth } from '../features/auth/AuthContext';

const languageName = (lang: Lang) => lang === 'sat_Olck' ? 'ᱥᱟᱱᱛᱟᱲᱤ' : lang === 'eng_Latn' ? 'English' : 'हिन्दी';

export default function StudentLessonPage() {
  const { id } = useParams();
  const lessonId = Number(id);
  const { user } = useAuth();
  const { push } = useToast();
  const [pack, setPack] = useState<LessonPack | null>(null);
  const [language, setLanguage] = useState<Lang>((localStorage.getItem('student_language') as Lang) || user?.preferred_language || 'sat_Olck');
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  const [offline, setOffline] = useState(!navigator.onLine);
  const [audioUrls, setAudioUrls] = useState<Record<number, string>>({});
  const [cached, setCached] = useState(false);

  const load = async () => {
    try {
      const onlinePack = await api.studentPackage(lessonId);
      setPack(onlinePack); setCached(false); setError(''); await put('lessons', String(lessonId), onlinePack);
    } catch (err) {
      const localPack = await get<LessonPack>('lessons', String(lessonId));
      if (localPack) { setPack(localPack); setCached(true); setError(''); }
      else setError(errorMessage(err));
    }
  };

  useEffect(() => { void load(); const on = () => { setOffline(false); void syncNow(); void load(); }; const off = () => setOffline(true); window.addEventListener('online', on); window.addEventListener('offline', off); return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off); }; }, [lessonId]);

  const translation = pack?.translations.find((item) => item.language === language);
  const text = language === pack?.lesson.source_language ? pack?.version.clean_transcript || pack?.version.source_text : translation?.text;
  const questions = useMemo(() => pack?.practice.filter((question) => question.language === language) || [], [pack, language]);

  useEffect(() => {
    if (!pack) return;
    (async () => {
      const next: Record<number, string> = {};
      for (const artifact of pack.artifacts.filter((item) => item.type === 'audio' && item.language === language)) {
        const blob = await get<Blob>('audio', String(artifact.id));
        if (blob) next[artifact.id] = URL.createObjectURL(blob);
      }
      setAudioUrls(next);
    })();
  }, [pack, language]);

  const download = async () => {
    if (!pack) return;
    try {
      await put('lessons', String(pack.lesson.id), pack);
      for (const artifact of pack.artifacts.filter((item) => item.type === 'audio')) {
        try { await put('audio', String(artifact.id), await api.fetchArtifact(artifact.id)); } catch { /* content remains downloadable */ }
      }
      await put('app_metadata', `cached:${pack.lesson.id}`, { cachedAt: Date.now(), version: pack.version.version_number });
      setCached(true); push('This lesson is ready for offline use.');
    } catch (err) { push(errorMessage(err), 'error'); }
  };

  const loadAudio = async (artifactId: number) => {
    if (audioUrls[artifactId]) return;
    try { const blob = await api.fetchArtifact(artifactId); setAudioUrls((old) => ({ ...old, [artifactId]: URL.createObjectURL(blob) })); }
    catch (err) { setError(errorMessage(err)); }
  };

  const submit = async () => {
    if (!pack) return;
    const payload = { ...answers, __lesson_id: lessonId, __language: language };
    if (navigator.onLine) {
      try { const response = await api.attempt(payload, pack.version.id); setResult(response); push('Practice submitted.'); }
      catch (err) { setError(errorMessage(err)); }
    } else {
      await queueAttempt({ localId: crypto.randomUUID(), lessonId, lessonVersionId: pack.version.id, answers: payload, createdAt: new Date().toISOString() });
      setResult({ score: null, pending: true }); push('Answer saved offline. It will sync when connection returns.');
    }
  };

  if (!pack) return <Page title="Opening lesson…"><Card>{error ? <><Status tone="danger">{error}</Status><Button variant="secondary" onClick={() => { setError(''); void load(); }}><RefreshCw size={15} /> Retry</Button></> : <div className="loading-inline"><RefreshCw size={18} className="spin" /> Loading lesson pack…</div>}</Card></Page>;

  return <Page eyebrow={`${pack.lesson.grade} · ${pack.lesson.subject}`} title={pack.lesson.title} subtitle={pack.version.learning_objectives[0] || pack.lesson.topic || 'Explore the lesson, then practice the concepts.'} actions={<div className="head-action-row"><Link to="/student"><Button variant="ghost"><ArrowLeft size={16} /> My learning</Button></Link><Button variant="secondary" onClick={() => void download()}><Download size={15} /> {cached ? 'Offline ready' : 'Download offline'}</Button></div>}>
    <div className="lesson-status-bar"><div>{offline || cached ? <Status tone="warning"><WifiOff size={15} /> {offline ? 'Offline mode' : 'Cached on this device'}</Status> : <Status tone="success"><Wifi size={15} /> Online</Status>}</div><div className="language-switcher">{(['hin_Deva', 'sat_Olck', 'eng_Latn'] as Lang[]).map((lang) => <button key={lang} className={language === lang ? 'selected' : ''} onClick={() => { setLanguage(lang); localStorage.setItem('student_language', lang); }}>{languageName(lang)}</button>)}</div></div>
    {error && <Card className="error-card"><Status tone="danger">{error}</Status><button onClick={() => setError('')}>Dismiss</button></Card>}
    <div className="lesson-main-grid"><Card className="lesson-reader"><div className="reader-kicker"><span>LESSON CONTENT</span>{translation ? <Status tone={translation.verification_status === 'TEACHER_APPROVED' ? 'success' : 'warning'}>{translation.verification_status.replaceAll('_', ' ')}</Status> : <Status>Source language</Status>}</div><div className={`lesson-script ${language === 'sat_Olck' ? 'ol-chiki' : ''}`}>{text || 'This language version has not been prepared yet.'}</div>{translation?.flags?.length ? <div className="info-banner warning"><span>Translation Guard</span><p>This version carries {translation.flags.length} review flag(s). Student delivery uses only what the educator published.</p></div> : null}<div className="audio-block"><SectionTitle title="Listen" subtitle="Audio is cached by the educator or downloaded to this device." />{pack.artifacts.filter((artifact) => artifact.type === 'audio' && artifact.language === language).length ? <div className="audio-list">{pack.artifacts.filter((artifact) => artifact.type === 'audio' && artifact.language === language).map((artifact) => <div className="student-audio" key={artifact.id}><div><Volume2 size={17} /><div><strong>{languageName(language)} audio</strong><span>Local classroom recording</span></div></div><audio controls src={audioUrls[artifact.id]} onPlay={() => void loadAudio(artifact.id)} /></div>)}</div> : <Status tone="warning">Audio has not been prepared for this language yet.</Status>}</div></Card><Card className="lesson-side-card"><SectionTitle title="Learning at a glance" /><div className="concept-chip-list">{pack.version.concepts.map((concept) => <span key={concept.concept_id}>{concept.label}</span>)}</div><div className="side-rule" /><div className="side-info"><Headphones size={17} /><div><strong>Listen</strong><span>Play cached audio whenever it is available.</span></div></div><div className="side-info"><Download size={17} /><div><strong>Offline</strong><span>Download once, then continue without internet.</span></div></div></Card></div>
    <Card><SectionTitle title="Practice your understanding" subtitle="Answer the questions from the prepared lesson package. Exact wording is not the goal; understanding the concept is." />{questions.length === 0 ? <Status tone="warning">Practice has not been prepared in {languageName(language)} yet.</Status> : <div className="practice-list">{questions.map((question, index) => <div className="practice-card" key={question.id}><div className="practice-number">{String(index + 1).padStart(2, '0')}</div><div className="practice-body"><strong>{question.prompt}</strong><div className="option-list">{question.options.map((option) => <label key={option} className={answers[String(question.id)] === option ? 'option selected' : 'option'}><input type="radio" name={`question-${question.id}`} checked={answers[String(question.id)] === option} onChange={() => setAnswers((old) => ({ ...old, [String(question.id)]: option }))} /><span>{option}</span></label>)}</div></div></div>)}<div className="practice-submit"><Button onClick={() => void submit()} disabled={questions.some((question) => !answers[String(question.id)])}><CheckCircle2 size={16} /> {offline ? 'Save offline answer' : 'Submit answers'}</Button>{result?.pending && <Status tone="warning">Saved locally · waiting for sync</Status>}{result && result.score !== null && <div className="score-box"><strong>{result.score}%</strong><span>Concept understanding</span></div>}</div></div>}</Card>
  </Page>;
}
