import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, FileText, Layers, Mic, Play, Printer, RefreshCw, Send, ShieldCheck, Upload, Volume2 } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { Page, SectionTitle } from '../components/Shell';
import { Button, Busy, Card, Field, Status, useToast } from '../components/UI';
import { api, errorMessage } from '../lib/api';
import type { Lang, LessonPack, Translation, VersionSummary } from '../types';

const STEPS = [
  { key: 'source', label: 'Source', short: 'Input' },
  { key: 'understand', label: 'Understand', short: 'AI context' },
  { key: 'concepts', label: 'Concepts', short: 'Meaning' },
  { key: 'languages', label: 'Languages', short: 'Translate' },
  { key: 'activities', label: 'Activities', short: 'Practice' },
  { key: 'review', label: 'Review', short: 'Publish' },
] as const;

const languageLabel = (lang: Lang) => lang === 'sat_Olck' ? 'Santhali' : lang === 'eng_Latn' ? 'English' : 'Hindi';

export default function LessonBuilderPage() {
  const { id } = useParams();
  const lessonId = Number(id);
  const navigate = useNavigate();
  const { push } = useToast();
  const [pack, setPack] = useState<LessonPack | null>(null);
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [step, setStep] = useState(0);
  const [title, setTitle] = useState('');
  const [topic, setTopic] = useState('');
  const [source, setSource] = useState('');
  const [transcript, setTranscript] = useState('');
  const [outcome, setOutcome] = useState('');
  const [concepts, setConcepts] = useState<string[]>([]);
  const [target, setTarget] = useState<Lang>('sat_Olck');
  const [editedTranslation, setEditedTranslation] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [recording, setRecording] = useState(false);
  const [media, setMedia] = useState<MediaRecorder | null>(null);
  const [artifactUrls, setArtifactUrls] = useState<Record<number, string>>({});
  const [lastSaved, setLastSaved] = useState<number | null>(null);
  const autosaveTimer = useRef<number | null>(null);
  const hydrated = useRef(false);

  const refresh = useCallback(async () => {
    const current = await api.lesson(lessonId);
    setPack(current);
    setTitle(current.lesson.title);
    setTopic(current.lesson.topic || '');
    setSource(current.version.source_text || '');
    setTranscript(current.version.clean_transcript || '');
    setOutcome(current.version.learning_objectives[0] || '');
    setConcepts(current.version.concepts.map((concept) => concept.label));
    const selected = current.translations.find((item) => item.language === target);
    setEditedTranslation(selected?.text || '');
    hydrated.current = true;
  }, [lessonId, target]);

  const loadVersions = useCallback(async () => {
    try { setVersions(await api.versions(lessonId)); } catch { /* optional */ }
  }, [lessonId]);

  useEffect(() => {
    (async () => {
      try { await refresh(); await loadVersions(); setError(''); }
      catch (err) { setError(errorMessage(err)); }
    })();
  }, [refresh, loadVersions]);

  const currentTranslation = useMemo(() => pack?.translations.find((item) => item.language === target), [pack, target]);
  const canPublish = useMemo(() => {
    if (!pack?.translations.length) return false;
    return pack.translations.every((item) => item.verification_status === 'TEACHER_APPROVED');
  }, [pack]);

  useEffect(() => {
    if (currentTranslation) setEditedTranslation(currentTranslation.text);
    else setEditedTranslation('');
  }, [currentTranslation?.id]);

  useEffect(() => {
    if (!pack) return;
    let cancelled = false;
    (async () => {
      const audioArtifacts = pack.artifacts.filter((artifact) => artifact.type === 'audio');
      for (const artifact of audioArtifacts) {
        if (artifactUrls[artifact.id]) continue;
        try {
          const blob = await api.fetchArtifact(artifact.id);
          if (!cancelled) setArtifactUrls((old) => old[artifact.id] ? old : ({ ...old, [artifact.id]: URL.createObjectURL(blob) }));
        } catch {
          // An unavailable audio file should not block the lesson builder.
        }
      }
    })();
    return () => { cancelled = true; };
  }, [pack?.version.id, pack?.artifacts.length]);

  const saveDraft = useCallback(async (silent = false) => {
    if (!hydrated.current) return;
    try {
      const updated = await api.patchLesson(lessonId, { title, topic, source_text: source, clean_transcript: transcript, learning_outcome: outcome, concepts });
      setPack(updated);
      setLastSaved(Date.now());
      if (!silent) { setNotice('Draft saved.'); push('Draft saved.'); }
    } catch (err) {
      if (!silent) setError(errorMessage(err));
    }
  }, [lessonId, title, topic, source, transcript, outcome, concepts, push]);

  useEffect(() => {
    if (!hydrated.current) return;
    if (autosaveTimer.current) window.clearTimeout(autosaveTimer.current);
    autosaveTimer.current = window.setTimeout(() => { void saveDraft(true); }, 1400);
    return () => { if (autosaveTimer.current) window.clearTimeout(autosaveTimer.current); };
  }, [title, topic, source, transcript, outcome, concepts, saveDraft]);

  const run = async (label: string, action: () => Promise<void>) => {
    setBusy(label); setError(''); setNotice('');
    try { await action(); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(''); }
  };

  const analyze = () => run('Preparing learning context…', async () => {
    await saveDraft(true);
    const result = await api.analyze(lessonId);
    setOutcome(result.learning_objective || '');
    setConcepts((result.concepts || []).map((concept: any) => concept.label).filter(Boolean));
    await refresh();
    push('Learning outcome and concepts are ready.');
  });

  const translate = () => run(`Preparing ${languageLabel(target)}…`, async () => {
    await saveDraft(true);
    await api.translate(lessonId, target);
    await refresh();
    push(`${languageLabel(target)} translation is ready for review.`);
  });

  const saveTranslation = async () => {
    if (!currentTranslation) return;
    await run('Saving review…', async () => {
      const updated = await api.verify(lessonId, { translation_id: currentTranslation.id, approved: true, edited_text: editedTranslation, native_review_status: target === 'sat_Olck' ? 'PENDING' : 'NOT_REVIEWED' });
      setPack(updated);
      push(`${languageLabel(target)} translation approved by teacher.`);
    });
  };

  const markNativeVerified = async () => {
    if (!currentTranslation || target !== 'sat_Olck') return;
    await run('Saving language review…', async () => {
      const updated = await api.verify(lessonId, { translation_id: currentTranslation.id, approved: true, edited_text: editedTranslation, native_review_status: 'VERIFIED' });
      setPack(updated);
      push('Santhali native-review state marked verified.');
    });
  };

  const generatePractice = (language: Lang) => run('Preparing practice…', async () => {
    await api.practice(lessonId, language, 4);
    await refresh();
    push(`${languageLabel(language)} practice is ready.`);
  });

  const generateWorksheet = () => run('Preparing worksheet…', async () => {
    const result = await api.worksheet(lessonId);
    const popup = window.open('', '_blank', 'noopener,noreferrer');
    if (!popup) throw new Error('The worksheet window was blocked. Allow pop-ups for localhost:5173.');
    popup.document.write(result.html);
    popup.document.close();
    push('Worksheet preview opened.');
  });

  const generateFlashcards = (language: Lang) => run('Preparing flashcards…', async () => {
    await api.flashcards(lessonId, language);
    await refresh();
    push('Flashcards are ready.');
  });

  const makeTTS = (language: Lang) => run(`Creating ${languageLabel(language)} audio…`, async () => {
    const result = await api.tts(lessonId, language);
    await refresh();
    if (result?.artifact_id) {
      try { const blob = await api.fetchArtifact(result.artifact_id); setArtifactUrls((old) => ({ ...old, [result.artifact_id]: URL.createObjectURL(blob) })); } catch { /* play through refresh when possible */ }
    }
    push(`${languageLabel(language)} audio is ready.`);
  });

  const createVersion = () => run('Saving new version…', async () => {
    const updated = await api.newVersion(lessonId, { source_text: source, clean_transcript: transcript, learning_outcome: outcome, concepts });
    setPack(updated); await loadVersions(); setStep(0); push(`Version ${updated.version.version_number} created.`);
  });

  const rollback = (versionId: number) => run('Restoring version…', async () => {
    const updated = await api.rollback(lessonId, versionId);
    setPack(updated); await loadVersions(); push(`Version ${versionId} restored.`);
  });

  const publish = () => run('Publishing lesson…', async () => {
    if (!canPublish) throw new Error('Publish is blocked. Approve every prepared translation first, including the Santhali showcase translation.');
    const updated = await api.publish(lessonId);
    setPack(updated); await loadVersions(); push('Lesson published. Students can now sync it for offline use.');
  });

  const record = async () => {
    if (recording) { media?.stop(); setRecording(false); return; }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError('This browser does not support microphone recording. Use the text editor or upload a supported audio file from the API tools.'); return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        setRecording(false);
        setBusy('Transcribing Hindi audio…'); setError('');
        try {
          const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
          const extension = (recorder.mimeType || '').includes('ogg') ? 'ogg' : 'webm';
          const file = new File([blob], `teacher-recording.${extension}`, { type: blob.type });
          const result = await api.transcribe(lessonId, file);
          setTranscript(result.text || ''); setSource(result.text || '');
          await refresh(); push('Transcript is ready. Review it before analysis.');
        } catch (err) { setError(errorMessage(err)); }
        finally { setBusy(''); }
      };
      recorder.start(); setMedia(recorder); setRecording(true); push('Recording started. Keep it short and clear.');
    } catch { setError('Microphone access was denied. Check browser permissions and try again.'); }
  };

  const uploadAudio = async (file: File | undefined) => {
    if (!file) return;
    await run('Transcribing audio…', async () => {
      const result = await api.transcribe(lessonId, file);
      setTranscript(result.text || ''); setSource(result.text || ''); await refresh(); push('Uploaded audio transcribed.');
    });
  };

  const next = () => setStep((current) => Math.min(STEPS.length - 1, current + 1));
  const back = () => setStep((current) => Math.max(0, current - 1));

  if (!pack) return <Page title="Opening lesson…"><Card>{error ? <><Status tone="danger">{error}</Status><Button variant="secondary" onClick={() => { setError(''); void refresh(); }}>Retry</Button></> : <div className="loading-inline"><RefreshCw size={18} className="spin" /> Loading lesson data…</div>}</Card></Page>;

  return <Page eyebrow={`${pack.lesson.grade} · ${pack.lesson.subject}`} title={pack.lesson.title} subtitle="AI prepares. The educator decides. The learner learns." actions={<div className="head-action-row"><Button variant="ghost" onClick={() => navigate(`/groups/${pack.lesson.group_id}`)}><ArrowLeft size={16} /> Classroom</Button><Button variant="secondary" onClick={() => void saveDraft()} disabled={!!busy}>Save now</Button></div>}>
    <div className="builder-topbar"><div className="builder-status"><span className={`status-dot ${pack.lesson.status === 'PUBLISHED' ? 'published' : ''}`}></span><strong>{pack.lesson.status.replaceAll('_', ' ')}</strong><span>Version {pack.version.version_number}</span>{lastSaved && <small>Saved {new Date(lastSaved).toLocaleTimeString()}</small>}</div><div className="builder-actions"><Button variant="ghost" onClick={createVersion} disabled={!!busy}><Layers size={15} /> New version</Button></div></div>
    {busy && <Busy label={busy} />}{error && <Card className="error-card"><Status tone="danger">{error}</Status><button onClick={() => setError('')}>Dismiss</button></Card>}{notice && <Status tone="success">{notice}</Status>}
    <div className="stepper">{STEPS.map((item, index) => <button key={item.key} onClick={() => setStep(index)} className={`stepper-item ${step === index ? 'active' : ''} ${index < step ? 'complete' : ''}`}><span>{index < step ? <Check size={14} /> : index + 1}</span><div><strong>{item.label}</strong><small>{item.short}</small></div></button>)}</div>
    <div className="builder-layout">
      <div className="builder-main">
        {step === 0 && <Card><SectionTitle title="1. Original lesson" subtitle="Keep the teacher's content as the source of truth." /><div className="info-banner"><FileText size={17} /><div><strong>Source preservation</strong><span>AI suggestions never replace this original text.</span></div></div><div className="form-stack"><Field label="Lesson title"><input value={title} onChange={(e) => setTitle(e.target.value)} /></Field><Field label="Topic" hint="Optional but useful for curriculum context."><input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Plants and Water" /></Field><Field label="Teacher lesson"><textarea rows={10} value={source} onChange={(e) => setSource(e.target.value)} placeholder="आज हम सीखेंगे कि पौधों को पानी की आवश्यकता क्यों होती है…" /></Field></div><div className="recording-box"><div><strong>Voice input</strong><span>Teacher speaks Hindi → Whisper transcript → editable text.</span></div><div className="button-row"><Button variant={recording ? 'danger' : 'secondary'} onClick={() => void record()} disabled={!!busy}><Mic size={16} />{recording ? 'Stop recording' : 'Record Hindi'}</Button><label className="btn btn-ghost file-btn"><Upload size={16} /> Upload audio<input type="file" accept="audio/*,.webm" onChange={(e) => void uploadAudio(e.target.files?.[0])} /></label></div></div>{transcript && <div className="subcard"><div className="subcard-head"><strong>Editable transcript</strong><Status tone="info">Whisper output</Status></div><textarea rows={7} value={transcript} onChange={(e) => setTranscript(e.target.value)} /></div>}<div className="wizard-nav"><Button onClick={() => setStep(1)} disabled={!source.trim()}>Continue <ArrowRight size={16} /></Button></div></Card>}

        {step === 1 && <Card><SectionTitle title="2. Understand the lesson" subtitle="Create learning context before translation." /><div className="context-card"><div className="context-icon"><ShieldCheck size={19} /></div><div><strong>Teacher meaning stays intact</strong><p>The system extracts a learning outcome, explanation and activity suggestions without rewriting your source.</p></div></div><Field label="Learning outcome"><textarea rows={5} value={outcome} onChange={(e) => setOutcome(e.target.value)} placeholder="Learner can explain why plants need water to live and grow." /></Field><div className="button-row"><Button onClick={() => void analyze()} disabled={!!busy || !source.trim()}><RefreshCw size={16} /> Analyze with lesson intelligence</Button><Button variant="ghost" onClick={() => setStep(2)}>Edit manually</Button></div><div className="wizard-nav"><Button variant="ghost" onClick={back}><ArrowLeft size={16} /> Back</Button><Button onClick={next}>Continue <ArrowRight size={16} /></Button></div></Card>}

        {step === 2 && <Card><SectionTitle title="3. Concepts" subtitle="Concepts are reused across translation, practice, flashcards and assessment." />{concepts.length ? <div className="concept-editor">{concepts.map((concept, index) => <div className="concept-editor-row" key={`${concept}-${index}`}><span>{index + 1}</span><input value={concept} onChange={(e) => setConcepts(concepts.map((old, i) => i === index ? e.target.value : old))} /><button onClick={() => setConcepts(concepts.filter((_, i) => i !== index))} aria-label={`Remove ${concept}`}>&times;</button></div>)}</div> : <div className="empty compact"><div className="empty-icon"><Layers size={17} /></div><h3>No concepts yet</h3><p>Run analysis or add the core learning concepts manually.</p></div>}<div className="button-row"><Button variant="secondary" onClick={() => setConcepts([...concepts, 'New concept'])}>+ Add concept</Button><Button variant="ghost" onClick={() => void analyze()}>Refresh from source</Button></div><div className="wizard-nav"><Button variant="ghost" onClick={back}><ArrowLeft size={16} /> Back</Button><Button onClick={next} disabled={!concepts.length}>Continue <ArrowRight size={16} /></Button></div></Card>}

        {step === 3 && <Card><SectionTitle title="4. Languages & Translation Guard" subtitle="Generate English and Santhali separately so each output can be reviewed." /><div className="language-tabs">{(['eng_Latn', 'sat_Olck'] as Lang[]).map((lang) => <button key={lang} className={target === lang ? 'selected' : ''} onClick={() => setTarget(lang)}><strong>{languageLabel(lang)}</strong><span>{lang === 'sat_Olck' ? 'ᱥᱟᱱᱛᱟᱲᱤ · Ol Chiki' : 'English · Latin'}</span></button>)}</div><div className="translation-review-editor"><div className="translation-column"><div className="translation-head"><span>Original Hindi</span><small>Teacher source</small></div><div className="translation-text original">{transcript || source || 'No lesson source yet.'}</div></div><div className="translation-column"><div className="translation-head"><span>{languageLabel(target)}</span><small>{currentTranslation ? 'Reviewable output' : 'Not prepared'}</small></div><textarea rows={12} value={editedTranslation} onChange={(e) => setEditedTranslation(e.target.value)} placeholder={`Generate ${languageLabel(target)} to review it here…`} /></div></div><div className="translation-actions"><Button onClick={() => void translate()} disabled={!!busy || !source.trim()}><RefreshCw size={16} /> Generate {languageLabel(target)}</Button>{currentTranslation && <Button variant="secondary" onClick={() => void saveTranslation()} disabled={!!busy || !editedTranslation.trim()}><Check size={16} /> Approve translation</Button>}{currentTranslation?.flags?.length ? <Status tone="warning">{currentTranslation.flags.length} guard flag(s) need attention.</Status> : currentTranslation ? <Status tone="success">Automated checks passed. Teacher review still required.</Status> : <Status>Generate both languages before publishing.</Status>}</div>{currentTranslation && <div className="guard-panel-large"><div className="guard-summary"><div><span>Confidence</span><strong>{Math.round(currentTranslation.confidence * 100)}%</strong></div><div><span>Source leakage</span><strong>{currentTranslation.validation?.source_leakage ? 'Detected' : 'No'}</strong></div><div><span>Numbers</span><strong>{currentTranslation.validation?.number_mismatch ? 'Mismatch' : 'Preserved'}</strong></div><div><span>Teacher state</span><strong>{currentTranslation.verification_status.replaceAll('_', ' ')}</strong></div></div>{currentTranslation.flags.length > 0 && <div className="flag-list">{currentTranslation.flags.map((flag) => <span key={flag}>{flag.replaceAll('_', ' ')}</span>)}</div>}{target === 'sat_Olck' && <div className="native-review"><div><strong>Santhali native review</strong><span>{currentTranslation.native_review_status === 'VERIFIED' ? 'Verified by reviewer' : 'AI output is not automatically native-verified.'}</span></div>{currentTranslation.native_review_status !== 'VERIFIED' && <Button variant="ghost" onClick={() => void markNativeVerified()} disabled={!!busy}>Mark native review verified</Button>}</div>}</div>}<div className="wizard-nav"><Button variant="ghost" onClick={back}><ArrowLeft size={16} /> Back</Button><Button onClick={next}>Continue <ArrowRight size={16} /></Button></div></Card>}

        {step === 4 && <Card><SectionTitle title="5. Activities, worksheets & audio" subtitle="Create classroom support from the approved lesson concepts." /><div className="action-card-grid"><Card className="action-card"><BookIcon /><strong>Practice</strong><span>Generate MCQs from concepts.</span><div className="button-row"><Button variant="secondary" onClick={() => void generatePractice('hin_Deva')} disabled={!!busy}>Hindi</Button><Button variant="secondary" onClick={() => void generatePractice('eng_Latn')} disabled={!!busy}>English</Button><Button variant="secondary" onClick={() => void generatePractice('sat_Olck')} disabled={!!busy}>Santhali</Button></div></Card><Card className="action-card"><Printer size={19} /><strong>Worksheet</strong><span>Open the bilingual print-first worksheet preview.</span><Button variant="secondary" onClick={() => void generateWorksheet()} disabled={!!busy}>Preview worksheet</Button></Card><Card className="action-card"><Layers size={19} /><strong>Flashcards</strong><span>Concept cards are generated from approved meaning.</span><Button variant="secondary" onClick={() => void generateFlashcards(target)} disabled={!!busy}>Refresh flashcards</Button></Card><Card className="action-card"><Volume2 size={19} /><strong>Audio</strong><span>TTS is generated locally and stored as a cached artifact.</span><div className="button-row"><Button variant="secondary" onClick={() => void makeTTS('hin_Deva')} disabled={!!busy}>Hindi</Button><Button variant="secondary" onClick={() => void makeTTS('eng_Latn')} disabled={!!busy}>English</Button><Button variant="secondary" onClick={() => void makeTTS('sat_Olck')} disabled={!!busy}>Santhali</Button></div></Card></div>{pack.artifacts.filter((a) => a.type === 'audio').length > 0 && <div className="artifact-list">{pack.artifacts.filter((a) => a.type === 'audio').map((artifact) => <div key={artifact.id} className="artifact-row"><div><strong>{languageLabel(artifact.language)}</strong><span>Cached audio · {Math.max(1, Math.round(artifact.size_bytes / 1024))} KB</span></div><audio controls src={artifactUrls[artifact.id]} onPlay={async () => { if (!artifactUrls[artifact.id]) { try { const blob = await api.fetchArtifact(artifact.id); setArtifactUrls((old) => ({ ...old, [artifact.id]: URL.createObjectURL(blob) })); } catch (err) { setError(errorMessage(err)); } } }} /></div>)}</div>}<div className="wizard-nav"><Button variant="ghost" onClick={back}><ArrowLeft size={16} /> Back</Button><Button onClick={next}>Continue <ArrowRight size={16} /></Button></div></Card>}

        {step === 5 && <Card><SectionTitle title="6. Review & publish" subtitle="Preview what students will receive. Publishing is blocked until every prepared translation is approved." /><div className="preview-card"><div className="preview-top"><div><span className="eyebrow">STUDENT PREVIEW</span><h2>{title}</h2><p>{outcome || 'Learning outcome not added yet.'}</p></div><Status tone={canPublish ? 'success' : 'warning'}>{canPublish ? 'Ready to publish' : 'Review required'}</Status></div><div className="preview-concepts">{concepts.map((concept) => <span key={concept}>{concept}</span>)}</div><div className="preview-language-grid">{(['hin_Deva', 'eng_Latn', 'sat_Olck'] as Lang[]).map((lang) => { const t = lang === 'hin_Deva' ? null : pack.translations.find((translation) => translation.language === lang); return <div key={lang} className="preview-language"><div><strong>{languageLabel(lang)}</strong>{t ? <Status tone={t.verification_status === 'TEACHER_APPROVED' ? 'success' : 'warning'}>{t.verification_status.replaceAll('_', ' ')}</Status> : <Status>Source language</Status>}</div><p>{lang === 'hin_Deva' ? (transcript || source) : t?.text || 'Not prepared yet.'}</p></div>; })}</div></div><div className="publish-checklist"><div><Check size={15} /><span>Original source preserved</span></div><div><Check size={15} /><span>Learning outcome and concepts prepared</span></div><div><Check size={15} /><span>Teacher approval required for translations</span></div><div><Check size={15} /><span>Published package becomes eligible for offline sync</span></div></div><div className="button-row"><Button variant="secondary" onClick={createVersion} disabled={!!busy}><Layers size={15} /> Save as new version</Button><Button variant="secondary" onClick={() => void generateWorksheet()} disabled={!!busy}><Printer size={15} /> Worksheet preview</Button><Button onClick={() => void publish()} disabled={!canPublish || !!busy}><Send size={15} /> Publish lesson</Button></div><div className="version-history"><SectionTitle title="Version history" subtitle="Published versions can be restored without deleting their history." />{versions.map((version) => <div className="version-row" key={version.id}><div><strong>Version {version.version_number}</strong><span>{new Date(version.created_at).toLocaleString()}</span></div><div>{version.published_at ? <Status tone="success">Published</Status> : <Status>Draft</Status>}{version.published_at && version.id !== pack.version.id && <Button variant="ghost" onClick={() => void rollback(version.id)} disabled={!!busy}>Restore</Button>}</div></div>)}</div><div className="wizard-nav"><Button variant="ghost" onClick={back}><ArrowLeft size={16} /> Back</Button><Button variant="secondary" onClick={() => navigate(`/groups/${pack.lesson.group_id}`)}>Done</Button></div></Card>}
      </div>
      <aside className="builder-side">
        <Card className="sticky-card"><SectionTitle title="Live readiness" subtitle="This updates as you work." /><div className="status-list"><div><span>Original lesson</span><Status tone={source.trim() ? 'success' : 'warning'}>{source.trim() ? 'Ready' : 'Missing'}</Status></div><div><span>Learning outcome</span><Status tone={outcome.trim() ? 'success' : 'warning'}>{outcome.trim() ? 'Ready' : 'Missing'}</Status></div><div><span>Concepts</span><Status tone={concepts.length ? 'success' : 'warning'}>{concepts.length} saved</Status></div><div><span>English</span><Status tone={pack.translations.some((t) => t.language === 'eng_Latn' && t.verification_status === 'TEACHER_APPROVED') ? 'success' : 'warning'}>{pack.translations.some((t) => t.language === 'eng_Latn' && t.verification_status === 'TEACHER_APPROVED') ? 'Approved' : 'Review'}</Status></div><div><span>Santhali</span><Status tone={pack.translations.some((t) => t.language === 'sat_Olck' && t.verification_status === 'TEACHER_APPROVED') ? 'success' : 'warning'}>{pack.translations.some((t) => t.language === 'sat_Olck' && t.verification_status === 'TEACHER_APPROVED') ? 'Approved' : 'Review'}</Status></div><div><span>Publish</span><Status tone={canPublish ? 'success' : 'warning'}>{canPublish ? 'Unlocked' : 'Blocked'}</Status></div></div><div className="side-hint"><strong>Why blocked?</strong><p>{canPublish ? 'All prepared translations have teacher approval.' : 'Prepare English + Santhali, review each output and approve them. Santhali native review can stay visible as a separate trust state.'}</p></div></Card>
        <Card><SectionTitle title="Core loop" /><div className="mini-flow"><span>Speak / write</span><b>↓</b><span>Understand</span><b>↓</b><span>Concepts</span><b>↓</b><span>Translate + verify</span><b>↓</b><span>Publish + sync</span><b>↓</b><span>Learn + practice</span></div></Card>
      </aside>
    </div>
  </Page>;
}

function BookIcon() { return <BookGlyph />; }
function BookGlyph() { return <div className="action-icon"><FileText size={19} /></div>; }
