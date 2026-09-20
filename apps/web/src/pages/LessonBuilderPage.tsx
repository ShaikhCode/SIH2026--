import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft, ArrowRight, Check, FileText, Mic, Pause, Play, Printer,
  RefreshCw, Search, Send, ShieldCheck, Upload, Volume2, XCircle,
} from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { Page, SectionTitle } from '../components/Shell';
import { Button, Busy, Card, Field, Modal, Status, useToast } from '../components/UI';
import { api, errorMessage } from '../lib/api';
import type { Lang, LessonPack, Practice, Translation, VersionSummary } from '../types';

const STEPS = [
  { key: 'source', label: 'Source', short: 'Input' },
  { key: 'concepts', label: 'Concepts', short: 'Meaning' },
  { key: 'languages', label: 'Languages', short: 'Translate' },
  { key: 'activities', label: 'Activities', short: 'Practice + audio' },
  { key: 'review', label: 'Review', short: 'Publish' },
] as const;

const LANGUAGES: Lang[] = ['eng_Latn', 'hin_Deva', 'mar_Deva'];
const label = (lang: Lang) => lang === 'eng_Latn' ? 'English' : lang === 'mar_Deva' ? 'Marathi' : 'Hindi';
const nativeLabel = (lang: Lang) => lang === 'mar_Deva' ? 'मराठी' : lang === 'eng_Latn' ? 'English' : 'हिन्दी';

type AudioState = 'idle' | 'queued' | 'generating' | 'ready' | 'error';

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
  const [sourceLanguage, setSourceLanguage] = useState<Lang>('hin_Deva');
  const [transcript, setTranscript] = useState('');
  const [target, setTarget] = useState<Lang>('mar_Deva');
  const [editedTranslation, setEditedTranslation] = useState('');
  const [backTranslation, setBackTranslation] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [recording, setRecording] = useState(false);
  const [media, setMedia] = useState<MediaRecorder | null>(null);
  const [artifactUrls, setArtifactUrls] = useState<Record<number, string>>({});
  const [audioStatus, setAudioStatus] = useState<Record<string, AudioState>>({});
  const [audioErrors, setAudioErrors] = useState<Record<string, string>>({});
  const [worksheetHtml, setWorksheetHtml] = useState('');
  const [worksheetOpen, setWorksheetOpen] = useState(false);
  const [lastSaved, setLastSaved] = useState<number | null>(null);
  const [activePracticeLanguage, setActivePracticeLanguage] = useState<Lang>('hin_Deva');
  const [concepts, setConcepts] = useState<string[]>([]);

  const autosaveTimer = useRef<number | null>(null);
  const hydrated = useRef(false);
  const worksheetFrame = useRef<HTMLIFrameElement>(null);
  const warmStarted = useRef(false);
  const preparationSignature = useRef('');
  const publishLock = useRef(false);

  const refresh = useCallback(async () => {
    const current = await api.lesson(lessonId);
    setPack(current);
    setTitle(current.lesson.title);
    setTopic(current.lesson.topic || '');
    setSource(current.version.source_text || '');
    setSourceLanguage(current.lesson.source_language);
    setTranscript(current.version.clean_transcript || '');
    if (current.version.concepts.length) {
      setConcepts(current.version.concepts.map((concept) => concept.label));
    }
    hydrated.current = true;
    return current;
  }, [lessonId]);


  const loadVersions = useCallback(async () => {
    try { setVersions(await api.versions(lessonId)); } catch { /* diagnostics only */ }
  }, [lessonId]);

  useEffect(() => {
    void (async () => {
      try {
        await refresh();
        await loadVersions();
        setError('');
      } catch (err) {
        setError(errorMessage(err));
      }
    })();
  }, [refresh, loadVersions]);

  const requiredLanguages = useMemo(
    () => LANGUAGES.filter((language) => language !== sourceLanguage),
    [sourceLanguage],
  );

  useEffect(() => {
    if (target === sourceLanguage) setTarget(requiredLanguages[0] || LANGUAGES[0]);
    if (activePracticeLanguage === sourceLanguage) setActivePracticeLanguage(requiredLanguages[0] || LANGUAGES[0]);
  }, [sourceLanguage, requiredLanguages, target, activePracticeLanguage]);

  const currentTranslation = useMemo(
    () => pack?.translations.find((item) => item.language === target),
    [pack, target],
  );

  const translationByLanguage = useMemo(() => {
    const map = new Map<Lang, Translation>();
    pack?.translations.forEach((item) => map.set(item.language, item));
    return map;
  }, [pack]);

  useEffect(() => {
    setEditedTranslation(currentTranslation?.text || '');
    const savedBack = currentTranslation?.validation?.back_translation;
    setBackTranslation(typeof savedBack === 'string' ? savedBack : '');
  }, [currentTranslation?.id, currentTranslation?.text, currentTranslation?.validation?.back_translation]);

  useEffect(() => () => {
    Object.values(artifactUrls).forEach((url) => URL.revokeObjectURL(url));
  }, []);

  useEffect(() => { warmStarted.current = false; }, [sourceLanguage]);

  // Warm only the two routes required by this source language, in the background.
  // This removes the first-click model-load penalty without blocking the editor.
  useEffect(() => {
    if (!hydrated.current || warmStarted.current) return;
    warmStarted.current = true;
    void (async () => {
      for (const language of requiredLanguages) {
        try { await api.warmTranslation(sourceLanguage, language); } catch { /* best effort */ }
      }
    })();
  }, [sourceLanguage, requiredLanguages]);

  const saveDraft = useCallback(async (silent = false) => {
    if (!hydrated.current || publishLock.current) return;
    try {
      const updated = await api.patchLesson(lessonId, {
        title: title.trim(),
        topic: topic.trim(),
        source_text: source,
        clean_transcript: transcript,
        concepts,
        source_language: sourceLanguage,
      });
      setPack(updated);
      setLastSaved(Date.now());
      if (!silent) push('Draft saved.');
    } catch (err) {
      if (!silent) setError(errorMessage(err));
    }
  }, [lessonId, title, topic, source, sourceLanguage, transcript, concepts, push]);

  useEffect(() => {
    if (!hydrated.current) return;
    if (autosaveTimer.current) window.clearTimeout(autosaveTimer.current);
    autosaveTimer.current = window.setTimeout(() => void saveDraft(true), 1800);
    return () => { if (autosaveTimer.current) window.clearTimeout(autosaveTimer.current); };
  }, [title, topic, source, transcript, concepts, saveDraft]);

  const run = async (labelText: string, action: () => Promise<void>) => {
    setBusy(labelText);
    setError('');
    try { await action(); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(''); }
  };

  const prepareConcepts = async (): Promise<boolean> => {
    setBusy('Preparing concepts…');
    setError('');
    try {
      await saveDraft(true);
      const result = await api.prepareConcepts(lessonId);
      const nextConcepts = (result.concepts || []).map((item: any) => String(item.label || '')).filter(Boolean);
      setConcepts(nextConcepts);
      await refresh();
      push('Concepts prepared.');
      return nextConcepts.length > 0;
    } catch (err) {
      setError(errorMessage(err));
      return false;
    } finally {
      setBusy('');
    }
  };

  const applyTranslationResult = useCallback((language: Lang, result: any, selectLanguage = true) => {
    setPack((previous) => {
      if (!previous) return previous;
      const nextTranslation: Translation = {
        id: Number(result.translation_id),
        language,
        text: String(result.text || ''),
        confidence: Number(result.confidence || 0),
        flags: Array.isArray(result.flags) ? result.flags : [],
        validation: result.validation || {},
        verification_status: String(result.verification_status || 'UNVERIFIED'),
        teacher_edited: false,
        native_review_status: String(result.native_review_status || 'NOT_REVIEWED'),
        student_feedback: result.student_feedback || { confirmed: 0, reported: 0 },
        my_student_feedback: null,
      };
      return {
        ...previous,
        translations: [...previous.translations.filter((item) => item.language !== language), nextTranslation],
        artifacts: previous.artifacts.filter((item) => !(item.type === 'audio' && item.language === language)),
      };
    });
    if (selectLanguage) setEditedTranslation(String(result.text || ''));
    if (selectLanguage) setBackTranslation('');
  }, []);

  const translateOne = (language: Lang) => run(`Translating ${label(language)}…`, async () => {
    if (language === sourceLanguage) throw new Error('Choose a target language different from the lesson source.');
    const result = await api.translate(lessonId, language, source, transcript, sourceLanguage);
    applyTranslationResult(language, result);
    setTarget(language);
    push(`${label(language)} ready for review (${Math.round(Number(result.total_ms || result.translation_ms || 0))} ms model path).`);
  });

  const translateAll = () => run('Preparing target translations…', async () => {
    const targets = requiredLanguages.filter((language) => {
      const existing = translationByLanguage.get(language);
      return !(existing?.verification_status === 'TEACHER_APPROVED' && existing.text.trim());
    });
    if (!targets.length) {
      push('All target translations are already approved.');
      return;
    }
    // Launch both target requests together. The backend's model lock protects CPU
    // inference, while the UI receives each completed language independently.
    await Promise.all(targets.map(async (language) => {
      const result = await api.translate(lessonId, language, source, transcript, sourceLanguage);
      applyTranslationResult(language, result, false);
    }));
    setTarget(targets[0] || sourceLanguage);
    push('Target translations are ready. Review and approve each one.');
  });

  const meaningCheck = () => run(`Checking ${label(target)} meaning…`, async () => {
    if (!currentTranslation) throw new Error('Generate the translation first.');
    const result = await api.backTranslate(lessonId, currentTranslation.id);
    setBackTranslation(result.back_translation || '');
    push('Meaning check ready. Compare it with the teacher source.');
  });

  const saveTranslation = () => run('Saving text approval…', async () => {
    if (!currentTranslation) throw new Error(`Generate ${label(target)} before approving it.`);
    const result = await api.verify(lessonId, {
      translation_id: currentTranslation.id,
      approved: true,
      edited_text: editedTranslation,
      native_review_status: target === 'mar_Deva' ? 'PENDING' : 'NOT_REVIEWED',
    });
    setPack((previous) => previous ? {
      ...previous,
      translations: previous.translations.map((item) => item.id === currentTranslation.id ? {
        ...item,
        text: String(result.text || editedTranslation),
        verification_status: 'TEACHER_APPROVED',
        teacher_edited: item.text.trim() !== editedTranslation.trim() || item.teacher_edited,
      } : item),
    } : previous);
    push(`${label(target)} approved. Audio and practice are now preparing in the background.`);
    setStep(3);
  });

  const generatePractice = (language: Lang) => run(`Preparing ${label(language)} practice…`, async () => {
    await api.practice(lessonId, language, 4);
    await refresh();
    setActivePracticeLanguage(language);
    push(`${label(language)} practice is ready for review.`);
  });

  const approvePractice = (question: Practice) => run('Saving practice approval…', async () => {
    await api.approvePractice(lessonId, question.id, true);
    await refresh();
    push('Practice question approved.');
  });

  const generateWorksheet = () => run('Preparing worksheet…', async () => {
    const result = await api.worksheet(lessonId);
    setWorksheetHtml(result.html);
    setWorksheetOpen(true);
    push('Worksheet preview is ready.');
  });


  const queueAudio = (language: Lang) => run(`Queueing ${label(language)} audio…`, async () => {
    await api.queueTTSPreparation(lessonId, language);
    setAudioStatus((old) => ({ ...old, [language]: 'queued' }));
    push(`${label(language)} audio queued. It is separate from publishing and practice.`);
  });

  const playArtifact = useCallback(async (language: Lang) => {
    const artifact = pack?.artifacts.find((item) => item.type === 'audio' && item.language === language);
    if (!artifact) { push(`${label(language)} audio is still preparing.`); return; }
    let url = artifactUrls[artifact.id];
    if (!url) {
      const blob = await api.fetchArtifact(artifact.id);
      url = URL.createObjectURL(blob);
      setArtifactUrls((old) => ({ ...old, [artifact.id]: url! }));
    }
    const audio = document.getElementById(`lesson-audio-${language}`) as HTMLAudioElement | null;
    if (audio) {
      audio.src = url;
      await audio.play().catch(() => undefined);
    }
  }, [pack?.artifacts, artifactUrls, push]);

  // Background preparation status is persisted in the database. Poll only while
  // work exists, and refresh the full lesson pack only when a job completes.
  const syncPreparations = useCallback(async () => {
    try {
      const jobs = await api.preparations(lessonId);
      setAudioStatus((old) => {
        const next = { ...old };
        for (const job of jobs) {
          if (job.kind === 'tts' && job.language) {
            next[job.language] = job.status === 'FAILED' ? 'error' : job.status === 'READY' ? 'ready' : job.status === 'RUNNING' ? 'generating' : 'queued';
          }
        }
        return next;
      });
      setAudioErrors((old) => {
        const next = { ...old };
        for (const job of jobs) {
          if (job.kind === 'tts' && job.language && job.error) next[job.language] = job.error;
        }
        return next;
      });
      const signature = jobs.map((job) => `${job.id}:${job.status}:${job.error || ''}`).join('|');
      const changed = signature !== preparationSignature.current;
      preparationSignature.current = signature;
      if (changed) await refresh();
      return jobs.some((job) => job.status === 'QUEUED' || job.status === 'RUNNING');
    } catch {
      return false;
    }
  }, [lessonId, refresh]);

  useEffect(() => {
    let timer: number | null = null;
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      const active = await syncPreparations();
      if (!cancelled && active) timer = window.setTimeout(tick, 1600);
    };
    void tick();
    return () => { cancelled = true; if (timer) window.clearTimeout(timer); };
  }, [syncPreparations]);

  const createVersion = () => run('Saving new version…', async () => {
    const updated = await api.newVersion(lessonId, { source_text: source, clean_transcript: transcript, concepts });
    setPack(updated);
    await loadVersions();
    setStep(0);
    push(`Version ${updated.version.version_number} created.`);
  });

  const rollback = (versionId: number) => run('Restoring version…', async () => {
    const updated = await api.rollback(lessonId, versionId);
    setPack(updated);
    await loadVersions();
    push(`Published version ${updated.version.version_number} restored.`);
  });

  const approvedPractice = (pack?.practice_all || []).filter((question) => question.approved);
  const practiceByLanguage = new Map<Lang, Practice[]>();
  for (const language of requiredLanguages) {
    practiceByLanguage.set(language, approvedPractice.filter((question) => question.language === language));
  }
  const practiceReady = requiredLanguages.every((language) => (practiceByLanguage.get(language)?.length || 0) > 0);
  const practiceDrafts = (pack?.practice_all || []).filter((question) => !question.approved);
  const languageReady = requiredLanguages.every((language) => Boolean(translationByLanguage.get(language)?.text.trim()));
  const languageApproved = requiredLanguages.every((language) => translationByLanguage.get(language)?.verification_status === 'TEACHER_APPROVED');
  const audioReadyByLanguage = requiredLanguages.map((language) => ({
    language,
    ready: Boolean(pack?.artifacts.some((artifact) => artifact.type === 'audio' && artifact.language === language)),
  }));
  const audioReady = audioReadyByLanguage.every((item) => item.ready);

  const readiness = useMemo(() => {
    const problems: string[] = [];
    if (!title.trim()) problems.push('Add a title');
    if (!source.trim() && !transcript.trim()) problems.push('Add lesson source');
    requiredLanguages.forEach((language) => {
      const translation = translationByLanguage.get(language);
      if (!translation?.text.trim()) problems.push(`Generate ${label(language)}`);
      if (translation?.verification_status !== 'TEACHER_APPROVED') problems.push(`Approve ${label(language)}`);
    });
    return { publish: problems.length === 0, problems };
  }, [title, source, transcript, translationByLanguage, requiredLanguages]);

  const publish = () => run('Publishing lesson…', async () => {
    if (!readiness.publish) throw new Error(`Publish is blocked: ${readiness.problems.join(' • ')}`);
    publishLock.current = true;
    if (autosaveTimer.current) {
      window.clearTimeout(autosaveTimer.current);
      autosaveTimer.current = null;
    }
    try {
      const updated = await api.publish(lessonId);
      setPack(updated);
      await loadVersions();
      push('Lesson published. Students can now download it for offline learning.');
    } catch (err) {
      publishLock.current = false;
      throw err;
    }
  });

  const next = async () => {
    if (step === 0) {
      if (!title.trim() || !(source.trim() || transcript.trim())) {
        setError('Complete the lesson title and add the teacher source first.');
        return;
      }
      if (!concepts.length) {
        const prepared = await prepareConcepts();
        if (!prepared) return;
      }
    }
    if (step === 1 && !concepts.length) {
      setError('Prepare at least one concept.');
      return;
    }
    if (step === 2 && !languageReady) {
      setError('Generate the required target languages before leaving the Languages step.');
      return;
    }
    setError('');
    setStep((current) => Math.min(STEPS.length - 1, current + 1));
  };

  const back = () => setStep((current) => Math.max(0, current - 1));

  const record = async () => {
    if (recording) {
      media?.stop();
      setRecording(false);
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError('This browser cannot record audio. Use the text editor or upload an audio file.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
        const extension = blob.type.includes('ogg') ? 'ogg' : 'webm';
        const file = new File([blob], `teacher-recording.${extension}`, { type: blob.type });
        void run('Transcribing audio…', async () => {
          const result = await api.transcribe(lessonId, file);
          setTranscript(result.text || '');
          setSource(result.text || '');
          push('Transcript prepared. Edit it before continuing.');
        });
      };
      setMedia(recorder);
      recorder.start();
      setRecording(true);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const uploadAudio = (file?: File) => {
    if (!file) return;
    void run('Transcribing audio…', async () => {
      const result = await api.transcribe(lessonId, file);
      setTranscript(result.text || '');
      setSource(result.text || '');
      await refresh();
      push('Transcript prepared. Edit it before continuing.');
    });
  };

  if (!pack) {
    return <Page title="Opening lesson…"><Card>{error ? <div className="stack-sm"><Status tone="danger">{error}</Status><Button onClick={() => { setError(''); void refresh(); }}><RefreshCw size={15} /> Retry</Button></div> : <Busy label="Loading lesson workspace…" />}</Card></Page>;
  }

  return <>
    <Page
      eyebrow={`${pack.lesson.grade} · ${pack.lesson.subject}`}
      title={pack.lesson.title}
      subtitle="Review the text you teach. Everything downstream prepares in the background."
      actions={<div className="head-action-row"><Button variant="ghost" onClick={() => navigate(`/groups/${pack.lesson.group_id}`)}><ArrowLeft size={16} /> Classroom</Button>{lastSaved && <Status tone="success">Saved {new Date(lastSaved).toLocaleTimeString()}</Status>}<Status tone={readiness.publish ? 'success' : 'warning'}>{readiness.publish ? 'Ready' : 'Draft'}</Status></div>}
    >
      {busy && <div className="busy-bar"><Busy label={busy} /></div>}
      {error && <div className="error-banner"><XCircle size={18} /><div><strong>We couldn't complete that step.</strong><span>{error}</span></div><button onClick={() => setError('')} aria-label="Dismiss"><XCircle size={15} /></button></div>}

      <div className="builder-steps">
        {STEPS.map((item, index) => {
          const available = index <= step || (index === 2 && languageReady) || (index >= 3 && languageApproved);
          return <button key={item.key} className={index === step ? 'active' : available ? 'done' : ''} onClick={() => available ? setStep(index) : setError(`Finish the earlier step before opening ${item.label}.`)}>
            <span className="step-number">{available && index !== step ? <Check size={15} /> : index + 1}</span><div><strong>{item.label}</strong><small>{item.short}</small></div>
          </button>;
        })}
      </div>

      <div className="builder-layout">
        <section className="builder-main">
          {step === 0 && <Card><SectionTitle title="1. Teacher source" subtitle="Write or record the lesson. The original source is preserved." />
            <div className="form-grid three"><Field label="Lesson title"><input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Why Plants Need Water" /></Field><Field label="Source language"><select value={sourceLanguage} onChange={(e) => setSourceLanguage(e.target.value as Lang)}><option value="hin_Deva">हिन्दी · Hindi</option><option value="eng_Latn">English</option><option value="mar_Deva">मराठी · Marathi</option></select></Field><Field label="Topic"><input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Plants" /></Field></div>
            <Field label="Teacher lesson"><textarea rows={12} value={source} onChange={(e) => { setSource(e.target.value); setTranscript(e.target.value); }} placeholder="Today we will learn why plants need water…" /></Field>
            <div className="source-tools"><Button variant={recording ? 'danger' : 'secondary'} onClick={() => void record()}>{recording ? <Pause size={16} /> : <Mic size={16} />}{recording ? 'Stop & transcribe' : `Record ${label(sourceLanguage)}`}</Button><label className="upload-button"><Upload size={16} /> Upload audio<input type="file" accept="audio/*" hidden onChange={(e) => uploadAudio(e.target.files?.[0])} /></label><Button variant="ghost" onClick={() => void saveDraft(false)} disabled={!!busy}>Save draft</Button></div>
            <div className="privacy-note"><ShieldCheck size={16} /><span>Source text stays immutable in the version history; generated translations never overwrite it.</span></div>
            <div className="wizard-nav"><span /><Button onClick={() => void next()}>Continue <ArrowRight size={16} /></Button></div>
          </Card>}

          {step === 1 && <Card><SectionTitle title="2. Concepts" subtitle="Keep only the concepts that matter. No learning-outcome generation is required." />
            <div className="analysis-panel"><div><span className="eyebrow">SOURCE</span><p>{transcript || source}</p></div></div>
            <div className="button-row"><Button onClick={() => void prepareConcepts()} disabled={!!busy || !(source.trim() || transcript.trim())}><RefreshCw size={16} /> Auto-find concepts</Button><Status tone="info">Local, deterministic extraction</Status></div>
            <div className="concept-editor"><div className="concept-editor-head"><strong>Key concepts</strong><Button variant="ghost" onClick={() => setConcepts((items) => [...items, ''])}><FileText size={15} /> Add concept</Button></div>{concepts.map((concept, index) => <div className="concept-edit-row" key={`concept-${index}`}><span>{index + 1}</span><input value={concept} onChange={(e) => setConcepts((items) => items.map((item, itemIndex) => itemIndex === index ? e.target.value : item))} placeholder="Concept" /><button onClick={() => setConcepts((items) => items.filter((_, itemIndex) => itemIndex !== index))} aria-label="Remove concept">×</button></div>)}</div>
            <div className="info-banner"><ShieldCheck size={16} /><div><strong>Speed rule</strong><p>Concept extraction is local and lightweight. Heavy translation/TTS models do not run here.</p></div></div>
            <div className="wizard-nav"><Button variant="ghost" onClick={back}><ArrowLeft size={16} /> Back</Button><Button variant="secondary" onClick={() => void saveDraft(false)}>Save concepts</Button><Button onClick={() => void next()}>Continue <ArrowRight size={16} /></Button></div>
          </Card>}

          {step === 2 && <Card><SectionTitle title="3. Languages & Translation Guard" subtitle="The translated text is the only human approval gate. Use Meaning Check when you want a source-language semantic view." />
            <div className="language-toolbar"><Button onClick={() => void translateAll()} disabled={!!busy || !(source.trim() || transcript.trim())}><RefreshCw size={16} /> Generate targets</Button>{requiredLanguages.map((lang) => <button key={lang} className={target === lang ? 'language-tab active' : 'language-tab'} onClick={() => setTarget(lang)}>{nativeLabel(lang)}</button>)}</div>
            <div className="translation-grid-large"><div className="translation-source"><div className="translation-head"><strong>Teacher source</strong><Status>{nativeLabel(sourceLanguage)} · Source</Status></div><div className="translation-text original">{transcript || source}</div></div><div className="translation-target"><div className="translation-head"><strong>{nativeLabel(target)}</strong>{currentTranslation ? <Status tone={currentTranslation.verification_status === 'TEACHER_APPROVED' ? 'success' : 'warning'}>{currentTranslation.verification_status.replaceAll('_', ' ')}</Status> : <Status>Not prepared</Status>}</div><textarea rows={15} value={editedTranslation} onChange={(e) => setEditedTranslation(e.target.value)} placeholder={`Generate ${label(target)} to review it here…`} /></div></div>
            <div className="translation-actions"><Button variant="secondary" onClick={() => void translateOne(target)} disabled={!!busy}><RefreshCw size={15} /> Generate {label(target)}</Button>{currentTranslation && <Button variant="secondary" onClick={() => void meaningCheck()} disabled={!!busy}><Search size={15} /> Meaning Check</Button>}{currentTranslation && <Button onClick={() => void saveTranslation()} disabled={!!busy || !editedTranslation.trim() || currentTranslation.verification_status === 'TEACHER_APPROVED'}><Check size={15} /> Approve {label(target)}</Button>}{currentTranslation && currentTranslation.flags.length > 0 ? <Status tone="warning">{currentTranslation.flags.length} Guard flag(s)</Status> : currentTranslation ? <Status tone="success">Automated checks passed; teacher review still required</Status> : <Status tone="warning">This language is not prepared yet</Status>}</div>
            {currentTranslation && <div className="guard-panel-large"><div className="guard-summary"><div><span>Confidence</span><strong>{Math.round(currentTranslation.confidence * 100)}%</strong></div><div><span>Concepts missing</span><strong>{currentTranslation.validation?.concepts_missing?.length || 0}</strong></div><div><span>Numbers</span><strong>{currentTranslation.validation?.number_mismatch ? 'Mismatch' : 'OK'}</strong></div><div><span>Source leakage</span><strong>{currentTranslation.validation?.source_leakage ? 'Review' : 'OK'}</strong></div></div>{currentTranslation.flags.length > 0 && <div className="flag-list">{currentTranslation.flags.map((flag) => <span key={flag}>{flag.replaceAll('_', ' ')}</span>)}</div>}{backTranslation && <div className="info-banner"><Search size={16} /><div><strong>Meaning Check · source-language back translation</strong><p>{backTranslation}</p></div></div>}{currentTranslation.native_review_status === 'PENDING' && <div className="native-review"><div><strong>Optional native-language review</strong><span>Useful when the teacher does not know the target language.</span></div><Status tone="warning">Pending</Status></div>}{(currentTranslation.student_feedback?.confirmed || currentTranslation.student_feedback?.reported) ? <div className="native-review"><div><strong>Student language feedback</strong><span>{currentTranslation.student_feedback?.confirmed || 0} confirmed · {currentTranslation.student_feedback?.reported || 0} reported</span></div><Status tone={(currentTranslation.student_feedback?.reported || 0) > 0 ? 'warning' : 'success'}>{(currentTranslation.student_feedback?.reported || 0) > 0 ? 'Review reports' : 'No reports'}</Status></div> : null}</div>}
            <div className="wizard-nav"><Button variant="ghost" onClick={back}><ArrowLeft size={16} /> Back</Button><Button onClick={() => void next()}>Continue to activities <ArrowRight size={16} /></Button></div>
          </Card>}

          {step === 3 && <Card><SectionTitle title="4. Activities, worksheets & audio" subtitle="Everything here is downstream from approved text. It can finish in the background and never blocks publishing." />
            <div className="action-card-grid">
              <Card className="action-card"><div className="action-icon"><FileText size={19} /></div><strong>Practice</strong><span>Draft questions are prepared automatically after translation approval. Approve them before students start practice.</span><div className="button-row wrap">{requiredLanguages.map((lang) => <Button key={lang} variant={activePracticeLanguage === lang ? 'primary' : 'secondary'} onClick={() => setActivePracticeLanguage(lang)} disabled={!!busy}>{label(lang)}</Button>)}</div></Card>
              <Card className="action-card"><div className="action-icon"><Printer size={19} /></div><strong>Worksheet</strong><span>Generate only when needed. It is not part of the critical publish path.</span><Button variant="secondary" onClick={() => void generateWorksheet()} disabled={!!busy}>Preview worksheet</Button></Card>
              <Card className="action-card"><div className="action-icon"><Volume2 size={19} /></div><strong>Audio</strong><span>Audio is manual because local Parler-TTS can be slow. Generate it only when you need a downloadable lesson recording. Publish never waits for audio.</span><div className="audio-prep-list">{requiredLanguages.map((lang) => { const artifact = pack.artifacts.find((item) => item.type === 'audio' && item.language === lang); const state = audioStatus[lang] || (artifact ? 'ready' : 'idle'); return <div className="audio-prep-row" key={lang}><div><strong>{label(lang)}</strong><small>{state === 'ready' ? 'Audio ready' : state === 'generating' ? 'Generating in background…' : state === 'queued' ? 'Queued in background…' : state === 'error' ? (audioErrors[lang] || 'Generation failed') : 'Waiting for text approval'}</small></div><div className="button-row">{state === 'ready' && artifact ? <><audio id={`lesson-audio-${lang}`} controls preload="none" /><Button variant="secondary" onClick={() => void playArtifact(lang)}><Play size={14} /> Hear</Button></> : state === 'error' ? <Button variant="secondary" onClick={() => { const job = pack.preparations?.find((item) => item.kind === 'tts' && item.language === lang); if (job) void run('Retrying audio…', async () => { await api.retryPreparation(lessonId, job.id); }); else void queueAudio(lang); }}>Retry</Button> : state === 'idle' ? <Button variant="secondary" onClick={() => void queueAudio(lang)}>Generate</Button> : <Status tone="info">Background</Status>}</div></div>; })}</div></Card>
            </div>
            <div className="info-banner"><ShieldCheck size={16} /><div><strong>Publish rule</strong><p>Approved text is enough to publish. Audio and practice continue preparing against the same lesson version after publication.</p></div></div>
            <div className="practice-review-block"><strong>Practice review</strong><span>Background questions are optional for publication. Review and approve them when you want the practice activity live.</span>{practiceDrafts.length > 0 && <div className="practice-list">{practiceDrafts.slice(0, 6).map((question) => <div className="practice-row" key={question.id}><div><strong>{question.prompt}</strong><small>{label(question.language)}</small></div><Button variant="secondary" onClick={() => void approvePractice(question)} disabled={!!busy}><Check size={14} /> Approve</Button></div>)}</div>}{practiceDrafts.length === 0 && <Status tone={practiceReady ? 'success' : 'info'}>{practiceReady ? 'Approved practice is ready.' : 'Waiting for background practice generation.'}</Status>}</div>
            <div className="wizard-nav"><Button variant="ghost" onClick={back}><ArrowLeft size={16} /> Back</Button><Button onClick={() => void next()}>Continue to review <ArrowRight size={16} /></Button></div>
          </Card>}
          {step === 4 && <Card><SectionTitle title="5. Review & publish" subtitle="Students only receive the published version. Translation approval is the human content gate; audio is generated from that approved text." />
            <div className="preview-card"><div className="preview-top"><div><span className="eyebrow">STUDENT PREVIEW</span><h2>{title}</h2><p>{topic || 'Multilingual classroom lesson'}</p></div><Status tone={readiness.publish ? 'success' : 'warning'}>{readiness.publish ? 'Ready to publish' : 'Review required'}</Status></div><div className="preview-concepts">{concepts.filter(Boolean).map((concept) => <span key={concept}>{concept}</span>)}</div><div className="preview-source-strip"><strong>{nativeLabel(sourceLanguage)} · Original teacher source</strong><p>{transcript || source}</p></div><div className="preview-language-grid">{requiredLanguages.map((lang) => { const translation = translationByLanguage.get(lang); const approved = translation?.verification_status === 'TEACHER_APPROVED'; return <div className="preview-language" key={lang}><div><strong>{nativeLabel(lang)}</strong>{translation ? <Status tone={approved ? 'success' : 'warning'}>{translation.verification_status.replaceAll('_', ' ')}</Status> : <Status>Not prepared</Status>}</div><p>{translation?.text || 'Not prepared yet.'}</p></div>; })}</div></div>
            <div className="publish-checklist"><div><Check size={15} /><span>Original source preserved</span></div><div><Check size={15} /><span>{requiredLanguages.map(label).join(' + ')} prepared and teacher-approved</span></div><div><Check size={15} /><span>{approvedPractice.length} approved practice question(s)</span></div><div><Check size={15} /><span>{audioReady ? 'All target-language audio prepared' : 'Background audio still preparing'}</span></div><div><Check size={15} /><span>Published package becomes eligible for offline sync</span></div></div>
            {!readiness.publish && <div className="blocker-panel"><strong>Still blocked</strong><ul>{readiness.problems.map((problem) => <li key={problem}>{problem.replaceAll('_',' ')}</li>)}</ul></div>}
            <div className="button-row wrap"><Button variant="secondary" onClick={createVersion} disabled={!!busy}><Layers size={15} /> Save as new version</Button><Button variant="secondary" onClick={() => void generateWorksheet()} disabled={!!busy}><Printer size={15} /> Worksheet preview</Button><Button onClick={() => void publish()} disabled={!readiness.publish || !!busy}><Send size={15} /> Publish lesson</Button></div>
            <div className="version-history"><SectionTitle title="Version history" subtitle="Restore only previously published versions; history is never deleted." />{versions.map((version) => <div className="version-row" key={version.id}><div><strong>Version {version.version_number}</strong><span>{new Date(version.created_at).toLocaleString()}</span></div><div>{version.published_at ? <Status tone="success">Published</Status> : <Status>Draft</Status>}{version.published_at && version.id !== pack.version.id && <Button variant="ghost" onClick={() => void rollback(version.id)} disabled={!!busy}>Restore</Button>}</div></div>)}</div>
          </Card>}
        </section>

        <aside className="builder-side"><Card className="sticky-card"><SectionTitle title="Live readiness" subtitle="Background work persists on the server." /><div className="status-list"><Readiness label="Original lesson" ok={Boolean(source.trim() || transcript.trim())} text={source.trim() || transcript.trim() ? 'Ready' : 'Missing'} /><Readiness label="Concepts" ok={Boolean(concepts.filter(Boolean).length)} text={`${concepts.filter(Boolean).length} saved`} />{requiredLanguages.map((language) => { const translation = translationByLanguage.get(language); return <Readiness key={language} label={label(language)} ok={translation?.verification_status === 'TEACHER_APPROVED'} text={translation?.verification_status === 'TEACHER_APPROVED' ? 'Approved' : translation ? 'Review' : 'Not prepared'} />; })}<Readiness label="Practice" ok={practiceReady} text={practiceReady ? 'Ready' : 'Background'} />{audioReadyByLanguage.map(({ language, ready }) => <Readiness key={`audio-${language}`} label={`${label(language)} audio`} ok={ready} text={ready ? 'Ready' : (audioStatus[language] || 'Background')} />)}<Readiness label="Publish" ok={readiness.publish} text={readiness.publish ? 'Unlocked' : 'Needs text approval'} /></div><div className="side-hint"><strong>Why is it blocked?</strong><p>{readiness.publish ? 'Text approval is complete. Audio and practice may still be running in the background.' : readiness.problems.join(' • ')}</p></div></Card><Card><SectionTitle title="Core loop" /><div className="mini-flow"><span>Speak / write</span><b>↓</b><span>Concepts</span><b>↓</b><span>Translate + review</span><b>↓</b><span>Background audio + practice</span><b>↓</b><span>Publish + learn</span></div></Card></aside>
      </div>
    </Page>

    {worksheetOpen && <Modal title="Worksheet preview" onClose={() => setWorksheetOpen(false)} wide><div className="worksheet-preview-actions"><Status tone="success">No pop-up required</Status><Button variant="secondary" onClick={() => worksheetFrame.current?.contentWindow?.print()}><Printer size={15} /> Print / Save PDF</Button><Button variant="ghost" onClick={() => setWorksheetOpen(false)}>Close</Button></div><iframe ref={worksheetFrame} className="worksheet-frame" title="BhashaSaathi worksheet" srcDoc={worksheetHtml} /></Modal>}
  </>;
}

function Readiness({ label, ok, text }: { label: string; ok: boolean; text: string }) {
  return <div><span>{label}</span><Status tone={ok ? 'success' : 'warning'}>{text}</Status></div>;
}
