import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft, ArrowRight, Check, ChevronDown, FileText, Layers, Mic, Pause,
  Play, Printer, RefreshCw, Send, ShieldCheck, Upload, Volume2, XCircle,
} from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { Page, SectionTitle } from '../components/Shell';
import { Button, Busy, Card, Field, Modal, Status, useToast } from '../components/UI';
import { api, errorMessage } from '../lib/api';
import type { Lang, LessonPack, Practice, Translation, VersionSummary } from '../types';

const STEPS = [
  { key: 'source', label: 'Source', short: 'Input' },
  { key: 'understand', label: 'Understand', short: 'AI context' },
  { key: 'concepts', label: 'Concepts', short: 'Meaning' },
  { key: 'languages', label: 'Languages', short: 'Translate' },
  { key: 'activities', label: 'Activities', short: 'Practice' },
  { key: 'review', label: 'Review', short: 'Publish' },
] as const;

const LANGUAGES: Lang[] = ['eng_Latn', 'hin_Deva', 'mar_Deva'];
const label = (lang: Lang) => lang === 'eng_Latn' ? 'English' : lang === 'mar_Deva' ? 'Marathi' : 'Hindi';
const nativeLabel = (lang: Lang) => lang === 'mar_Deva' ? 'मराठी' : lang === 'eng_Latn' ? 'English' : 'हिन्दी';

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
  const [outcome, setOutcome] = useState('');
  const [concepts, setConcepts] = useState<string[]>([]);
  const [target, setTarget] = useState<Lang>('mar_Deva');
  const [editedTranslation, setEditedTranslation] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [recording, setRecording] = useState(false);
  const [media, setMedia] = useState<MediaRecorder | null>(null);
  const [artifactUrls, setArtifactUrls] = useState<Record<number, string>>({});
  const [worksheetHtml, setWorksheetHtml] = useState('');
  const [worksheetOpen, setWorksheetOpen] = useState(false);
  const [lastSaved, setLastSaved] = useState<number | null>(null);
  const [activePracticeLanguage, setActivePracticeLanguage] = useState<Lang>('hin_Deva');
  const autosaveTimer = useRef<number | null>(null);
  const hydrated = useRef(false);
  const worksheetFrame = useRef<HTMLIFrameElement>(null);

  const refresh = useCallback(async () => {
    const current = await api.lesson(lessonId);
    setPack(current);
    setTitle(current.lesson.title);
    setTopic(current.lesson.topic || '');
    setSource(current.version.source_text || '');
    setSourceLanguage(current.lesson.source_language);
    setTranscript(current.version.clean_transcript || '');
    setOutcome(current.version.learning_objectives[0] || '');
    setConcepts(current.version.concepts.map((concept) => concept.label));
    hydrated.current = true;
    return current;
  }, [lessonId]);

  const loadVersions = useCallback(async () => {
    try { setVersions(await api.versions(lessonId)); } catch { /* diagnostics only */ }
  }, [lessonId]);

  useEffect(() => {
    void (async () => {
      try { await refresh(); await loadVersions(); setError(''); }
      catch (err) { setError(errorMessage(err)); }
    })();
  }, [refresh, loadVersions]);

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
  }, [currentTranslation?.id, currentTranslation?.text]);

  useEffect(() => {
    return () => {
      (Object.values(artifactUrls) as string[]).forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);

  useEffect(() => {
    if (!hydrated.current || sourceLanguage === target) return;
    void api.warmTranslation(sourceLanguage, target).catch(() => {
      // Prewarm is best-effort; the real translation request remains authoritative.
    });
  }, [sourceLanguage, target]);

  useEffect(() => {
    if (!hydrated.current) return;
    // Warm TTS while the teacher is doing other lesson work. This is intentionally
    // non-blocking; opening the builder must stay responsive.
    void api.warmTTS().catch(() => undefined);
  }, [lessonId]);

  useEffect(() => {
    if (step !== 4) return;
    void api.warmTTS().catch(() => {
      // The audio action will surface the real runtime error if warm-up fails.
    });
  }, [step]);

  const saveDraft = useCallback(async (silent = false) => {
    if (!hydrated.current) return;
    try {
      const updated = await api.patchLesson(lessonId, {
        title: title.trim(),
        topic: topic.trim(),
        source_text: source,
        clean_transcript: transcript,
        learning_outcome: outcome,
        concepts,
        source_language: sourceLanguage,
      });
      setPack(updated);
      setLastSaved(Date.now());
      if (!silent) push('Draft saved.');
    } catch (err) {
      if (!silent) setError(errorMessage(err));
    }
  }, [lessonId, title, topic, source, sourceLanguage, transcript, outcome, concepts, push]);

  useEffect(() => {
    if (!hydrated.current) return;
    if (autosaveTimer.current) window.clearTimeout(autosaveTimer.current);
    autosaveTimer.current = window.setTimeout(() => void saveDraft(true), 1200);
    return () => { if (autosaveTimer.current) window.clearTimeout(autosaveTimer.current); };
  }, [title, topic, source, transcript, outcome, concepts, saveDraft]);

  const run = async (labelText: string, action: () => Promise<void>) => {
    setBusy(labelText);
    setError('');
    setNotice('');
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

  const translateOne = (language: Lang) => run(`Preparing ${label(language)}…`, async () => {
    if (language === sourceLanguage) throw new Error('Choose a target language different from the lesson source.');
    await saveDraft(true);
    const existing = pack?.translations.find((item) => item.language === language);
    if (existing?.verification_status === 'TEACHER_APPROVED' && existing.text.trim()) {
      setTarget(language);
      push(`${label(language)} is already approved; no regeneration was needed.`);
      return;
    }
    await api.translate(lessonId, language);
    // Translation is ready; warm the resident TTS model in the background so
    // the later audio button does not pay the model-load cost.
    void api.warmTTS().catch(() => undefined);
    await refresh();
    setTarget(language);
    push(`${label(language)} translation is ready for teacher review.`);
  });

  const translateAll = () => run('Preparing target translations…', async () => {
    await saveDraft(true);
    const fresh = await refresh();
    const targets = LANGUAGES.filter((language) => language !== sourceLanguage);
    const failures: unknown[] = [];
    for (const language of targets) {
      const existing = fresh.translations.find((item) => item.language === language);
      if (existing?.verification_status === 'TEACHER_APPROVED' && existing.text.trim()) continue;
      try {
        await api.translate(lessonId, language);
      } catch (err) {
        failures.push(err);
      }
    }
    void api.warmTTS().catch(() => undefined);
    await refresh();
    if (failures.length) throw failures[0];
    push('All required target translations are ready for review.');
  });

  const saveTranslation = () => run('Saving teacher approval…', async () => {
    if (!currentTranslation) throw new Error(`Generate ${label(target)} before approving it.`);
    const updated = await api.verify(lessonId, {
      translation_id: currentTranslation.id,
      approved: true,
      edited_text: editedTranslation,
      native_review_status: target === 'mar_Deva' ? 'PENDING' : 'NOT_REVIEWED',
    });
    setPack(updated);
    push(`${label(target)} approved by the educator.`);
  });

  const generatePractice = (language: Lang) => run(`Preparing ${label(language)} practice…`, async () => {
    await api.practice(lessonId, language, 4);
    await refresh();
    setActivePracticeLanguage(language);
    push(`${label(language)} practice draft is ready for teacher approval.`);
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

  const generateFlashcards = (language: Lang) => run(`Preparing ${label(language)} flashcards…`, async () => {
    await api.flashcards(lessonId, language);
    await refresh();
    push('Flashcards refreshed from lesson concepts.');
  });

  const makeTTS = (language: Lang) => run(`Creating ${label(language)} audio…`, async () => {
    const result = await api.tts(lessonId, language);
    const blob = await api.fetchArtifact(result.artifact_id);
    const url = URL.createObjectURL(blob);
    setArtifactUrls((old) => ({ ...old, [result.artifact_id]: url }));
    await refresh();
    push(`${label(language)} audio is ready.`);
  });

  const createVersion = () => run('Saving new version…', async () => {
    const updated = await api.newVersion(lessonId, { source_text: source, clean_transcript: transcript, learning_outcome: outcome, concepts });
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

  const publish = () => run('Publishing lesson…', async () => {
    if (!readiness.publish) throw new Error(`Publish is blocked: ${readiness.problems.join(' • ')}`);
    const updated = await api.publish(lessonId);
    setPack(updated);
    await loadVersions();
    push('Lesson published. Students can now download it for offline learning.');
  });

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
        void run('Transcribing recording…', async () => {
          const result = await api.transcribe(lessonId, file);
          setTranscript(result.text || '');
          setSource(result.text || '');
          await refresh();
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

  const requiredLanguages = LANGUAGES.filter((language) => language !== sourceLanguage);

  useEffect(() => {
    if (target === sourceLanguage) {
      setTarget(requiredLanguages[0] || LANGUAGES[0]);
    }
    if (activePracticeLanguage === sourceLanguage) {
      setActivePracticeLanguage(requiredLanguages[0] || LANGUAGES[0]);
    }
  }, [sourceLanguage]);

  const languageReady = requiredLanguages.every((language) => Boolean(translationByLanguage.get(language)?.text.trim()));
  const languageApproved = requiredLanguages.every((language) => translationByLanguage.get(language)?.verification_status === 'TEACHER_APPROVED');

  const approvedPractice = (pack?.practice_all || []).filter((question) => question.approved);
  const practiceByLanguage = new Map<Lang, Practice[]>();
  for (const language of requiredLanguages) {
    practiceByLanguage.set(language, approvedPractice.filter((question) => question.language === language));
  }
  const practiceReady = requiredLanguages.every((language) => (practiceByLanguage.get(language)?.length || 0) > 0);
  const audioReadyByLanguage = requiredLanguages.map((language) => ({
    language,
    ready: Boolean(pack?.artifacts.some((artifact) => artifact.type === 'audio' && artifact.language === language)),
  }));
  const audioReady = audioReadyByLanguage.every((item) => item.ready);
  const practiceDrafts = (pack?.practice_all || []).filter((question) => !question.approved);

  const readiness = useMemo(() => {
    const problems: string[] = [];
    if (!title.trim()) problems.push('Add a title');
    if (!source.trim() && !transcript.trim()) problems.push('Add lesson source');
    if (!outcome.trim()) problems.push('Prepare learning outcome');
    if (!concepts.filter(Boolean).length) problems.push('Prepare concepts');
    requiredLanguages.forEach((language) => {
      const translation = translationByLanguage.get(language);
      if (!translation?.text.trim()) problems.push(`Generate ${label(language)}`);
      if (translation?.verification_status !== 'TEACHER_APPROVED') problems.push(`Approve ${label(language)}`);
    });
    requiredLanguages.forEach((language) => {
      if (!(practiceByLanguage.get(language)?.length || 0)) problems.push(`Approve at least one ${label(language)} practice question`);
    });
    audioReadyByLanguage.forEach(({ language, ready }) => {
      if (!ready) problems.push(`Prepare ${label(language)} audio`);
    });
    return { publish: problems.length === 0, problems };
  }, [title, source, transcript, outcome, concepts, translationByLanguage, pack?.practice_all, pack?.artifacts, sourceLanguage]);

  const next = () => {
    if (step === 0 && (!title.trim() || !(source.trim() || transcript.trim()))) {
      setError('Complete the lesson title and add the teacher source first.');
      return;
    }
    if (step === 1 && (!outcome.trim() || !concepts.length)) {
      setError('Run “Prepare learning context” before continuing.');
      return;
    }
    if (step === 2 && (!outcome.trim() || !concepts.length)) {
      setError('Prepare the learning outcome and at least one concept.');
      return;
    }
    if (step === 3 && !languageReady) {
      setError('Generate the required target languages before leaving the Languages step.');
      return;
    }
    if (step === 4 && !practiceDrafts.length && !approvedPractice.length) {
      setError('Generate practice, then approve at least one question.');
      return;
    }
    setError('');
    setStep((current) => Math.min(STEPS.length - 1, current + 1));
  };

  const back = () => setStep((current) => Math.max(0, current - 1));

  if (!pack) {
    return <Page title="Opening lesson…"><Card>{error ? <div className="stack-sm"><Status tone="danger">{error}</Status><Button onClick={() => { setError(''); void refresh(); }}><RefreshCw size={15} /> Retry</Button></div> : <Busy label="Loading lesson workspace…" />}</Card></Page>;
  }

  return <>
    <Page
      eyebrow={`${pack.lesson.grade} · ${pack.lesson.subject}`}
      title={pack.lesson.title}
      subtitle="Build once. Review carefully. Publish a complete multilingual lesson pack."
      actions={<div className="head-action-row"><Button variant="ghost" onClick={() => navigate(`/groups/${pack.lesson.group_id}`)}><ArrowLeft size={16} /> Classroom</Button>{lastSaved && <Status tone="success">Saved {new Date(lastSaved).toLocaleTimeString()}</Status>}<Status tone={readiness.publish ? 'success' : 'warning'}>{readiness.publish ? 'Ready' : 'Draft'}</Status></div>}
    >
      {busy && <div className="busy-bar"><Busy label={busy} /></div>}
      {error && <div className="error-banner"><XCircle size={18} /><div><strong>We couldn't complete that step.</strong><span>{error}</span></div><button onClick={() => setError('')} aria-label="Dismiss"><XCircle size={15} /></button></div>}
      {notice && <div className="success-banner"><Check size={18} />{notice}</div>}

      <div className="builder-steps">
        {STEPS.map((item, index) => {
          const available = index <= step || (index === 3 && languageReady) || (index === 4 && languageReady) || (index === 5 && languageApproved && practiceReady);
          return <button key={item.key} className={index === step ? 'active' : available ? 'done' : ''} onClick={() => available ? setStep(index) : setError(`Finish the earlier step before opening ${item.label}.`)}>
            <span className="step-number">{available && index !== step ? <Check size={15} /> : index + 1}</span><div><strong>{item.label}</strong><small>{item.short}</small></div>
          </button>;
        })}
      </div>

      <div className="builder-layout">
        <section className="builder-main">
          {step === 0 && <Card><SectionTitle title="1. Teacher source" subtitle="Write the lesson or record the teacher's explanation in the selected source language. The source is always preserved." />
            <div className="form-grid three"><Field label="Lesson title"><input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Why Plants Need Water" /></Field><Field label="Source language"><select value={sourceLanguage} onChange={(e) => setSourceLanguage(e.target.value as Lang)}><option value="hin_Deva">हिन्दी · Hindi</option><option value="eng_Latn">English</option><option value="mar_Deva">मराठी · Marathi</option></select></Field><Field label="Topic"><input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Plants" /></Field></div>
            <Field label="Teacher lesson" hint="Keep the original teaching meaning. AI will prepare suggestions around this source."><textarea rows={12} value={source} onChange={(e) => { setSource(e.target.value); setTranscript(e.target.value); }} placeholder="आज हम सीखेंगे कि पौधों को पानी की आवश्यकता क्यों होती है…" /></Field>
            <div className="source-tools"><Button variant={recording ? 'danger' : 'secondary'} onClick={() => void record()}>{recording ? <Pause size={16} /> : <Mic size={16} />}{recording ? 'Stop & transcribe' : `Record ${label(sourceLanguage)}`}</Button><label className="upload-button"><Upload size={16} /> Upload audio<input type="file" accept="audio/*" hidden onChange={(e) => uploadAudio(e.target.files?.[0])} /></label><Button variant="ghost" onClick={() => void saveDraft(false)} disabled={!!busy}>Save draft</Button></div>
            <div className="privacy-note"><ShieldCheck size={16} /><span>Original source and transcript remain separate from AI outputs. Nothing is silently overwritten.</span></div>
            <div className="wizard-nav"><span /><Button onClick={next}>Continue <ArrowRight size={16} /></Button></div>
          </Card>}

          {step === 1 && <Card><SectionTitle title="2. Understand the lesson" subtitle="AI prepares context, learning outcome and an explanation. You remain responsible for the final content." />
            <div className="analysis-panel"><div><span className="eyebrow">CURRENT SOURCE</span><p>{transcript || source}</p></div>{outcome && <div className="analysis-output"><strong>Learning outcome</strong><p>{outcome}</p></div>}</div>
            <div className="button-row"><Button onClick={analyze} disabled={!!busy || !(source.trim() || transcript.trim())}><RefreshCw size={16} /> Prepare learning context</Button>{outcome && <Status tone="success">Learning outcome ready</Status>}{concepts.length > 0 && <Status tone="success">{concepts.length} concepts ready</Status>}</div>
            <div className="wizard-nav"><Button variant="ghost" onClick={back}><ArrowLeft size={16} /> Back</Button><Button onClick={next}>Continue <ArrowRight size={16} /></Button></div>
          </Card>}

          {step === 2 && <Card><SectionTitle title="3. Concepts & meaning" subtitle="Concepts become the common representation for translation, practice, visuals and assessment." />
            <Field label="Learning outcome"><textarea rows={3} value={outcome} onChange={(e) => setOutcome(e.target.value)} /></Field>
            <div className="concept-editor"><div className="concept-editor-head"><strong>Key concepts</strong><Button variant="ghost" onClick={() => setConcepts((items) => [...items, ''])}><FileText size={15} /> Add concept</Button></div>{concepts.map((concept, index) => <div className="concept-edit-row" key={`concept-${index}`}><span>{index + 1}</span><input value={concept} onChange={(e) => setConcepts((items) => items.map((item, itemIndex) => itemIndex === index ? e.target.value : item))} placeholder="Concept" /><button onClick={() => setConcepts((items) => items.filter((_, itemIndex) => itemIndex !== index))} aria-label="Remove concept">×</button></div>)}</div>
            <div className="info-banner"><ShieldCheck size={16} /><div><strong>Trust rule</strong><p>AI suggestions may simplify or structure content, but they must not silently change the teacher's meaning.</p></div></div>
            <div className="wizard-nav"><Button variant="ghost" onClick={back}><ArrowLeft size={16} /> Back</Button><Button onClick={() => void saveDraft(false)} variant="secondary">Save concepts</Button><Button onClick={next}>Continue <ArrowRight size={16} /></Button></div>
          </Card>}

          {step === 3 && <Card><SectionTitle title="4. Languages & Translation Guard" subtitle="Generate both required showcase languages, then review each output before publication." />
            <div className="language-toolbar"><Button onClick={() => void translateAll()} disabled={!!busy || !(source.trim() || transcript.trim())}><RefreshCw size={16} /> Generate targets</Button>{requiredLanguages.map((lang) => <button key={lang} className={target === lang ? 'language-tab active' : 'language-tab'} onClick={() => setTarget(lang)}>{nativeLabel(lang)}</button>)}</div>
            <div className="translation-grid-large"><div className="translation-source"><div className="translation-head"><strong>Teacher source</strong><Status>{nativeLabel(sourceLanguage)} · Source</Status></div><div className="translation-text original">{transcript || source}</div></div><div className="translation-target"><div className="translation-head"><strong>{nativeLabel(target)}</strong>{currentTranslation ? <Status tone={currentTranslation.verification_status === 'TEACHER_APPROVED' ? 'success' : 'warning'}>{currentTranslation.verification_status.replaceAll('_', ' ')}</Status> : <Status>Not prepared</Status>}</div><textarea rows={15} value={editedTranslation} onChange={(e) => setEditedTranslation(e.target.value)} placeholder={`Generate ${label(target)} to review it here…`} /></div></div>
            <div className="translation-actions"><Button variant="secondary" onClick={() => void translateOne(target)} disabled={!!busy}><RefreshCw size={15} /> Generate {label(target)}</Button>{currentTranslation && <Button onClick={() => void saveTranslation()} disabled={!!busy || !editedTranslation.trim()}><Check size={15} /> Approve {label(target)}</Button>}{currentTranslation && currentTranslation.flags.length > 0 ? <Status tone="warning">{currentTranslation.flags.length} Translation Guard flag(s)</Status> : currentTranslation ? <Status tone="success">Automated checks passed; teacher review still required</Status> : <Status tone="warning">This language is not prepared yet</Status>}</div>
            {currentTranslation && <div className="guard-panel-large"><div className="guard-summary"><div><span>Confidence</span><strong>{Math.round(currentTranslation.confidence * 100)}%</strong></div><div><span>Concepts missing</span><strong>{currentTranslation.validation?.concepts_missing?.length || 0}</strong></div><div><span>Numbers</span><strong>{currentTranslation.validation?.number_mismatch ? 'Mismatch' : 'OK'}</strong></div><div><span>Source leakage</span><strong>{currentTranslation.validation?.source_leakage ? 'Review' : 'OK'}</strong></div></div>{currentTranslation.flags.length > 0 && <div className="flag-list">{currentTranslation.flags.map((flag) => <span key={flag}>{flag.replaceAll('_', ' ')}</span>)}</div>}{target === 'mar_Deva' && <div className="native-review"><div><strong>Marathi native review</strong><span>{currentTranslation.native_review_status === 'PENDING' ? 'Pending qualified language review. Teacher approval does not claim native verification.' : currentTranslation.native_review_status}</span></div><Status tone="warning">Not automatically verified</Status></div>}</div>}
            <div className="wizard-nav"><Button variant="ghost" onClick={back}><ArrowLeft size={16} /> Back</Button><Button onClick={next}>Continue to activities <ArrowRight size={16} /></Button></div>
          </Card>}

          {step === 4 && <Card><SectionTitle title="5. Activities, worksheets & audio" subtitle="Draft useful classroom support, review practice, then prepare cached audio." />
            <div className="action-card-grid"><Card className="action-card"><div className="action-icon"><FileText size={19} /></div><strong>Practice</strong><span>Generate draft MCQs from approved concepts.</span><div className="button-row wrap">{requiredLanguages.map((lang) => <span key={lang} className="inline-action"><Button variant={activePracticeLanguage === lang ? 'primary' : 'secondary'} onClick={() => void generatePractice(lang)} disabled={!!busy}>{label(lang)}</Button></span>)}</div></Card><Card className="action-card"><div className="action-icon"><Printer size={19} /></div><strong>Worksheet</strong><span>Open the bilingual print-first worksheet inside this app.</span><Button variant="secondary" onClick={() => void generateWorksheet()} disabled={!!busy}>Preview worksheet</Button></Card><Card className="action-card"><div className="action-icon"><Layers size={19} /></div><strong>Flashcards</strong><span>Generate visual-ready concept cards.</span><Button variant="secondary" onClick={() => void generateFlashcards(target)} disabled={!!busy}>Refresh flashcards</Button></Card><Card className="action-card"><div className="action-icon"><Volume2 size={19} /></div><strong>Audio</strong><span>Generate target audio after translation approval. The voice model preloads when you enter this step, so the button does not have to load it from scratch.</span><div className="button-row wrap">{requiredLanguages.map((lang) => <Button key={lang} variant="secondary" onClick={() => void makeTTS(lang)} disabled={!!busy}>{label(lang)}</Button>)}</div></Card></div>
            <div className="review-block"><SectionTitle title="Practice review" subtitle="Generated questions are drafts until the educator approves them." />{(pack.practice_all || []).filter((q) => q.language === activePracticeLanguage).length === 0 ? <Status tone="warning">Generate {label(activePracticeLanguage)} practice first.</Status> : <div className="practice-review-list">{(pack.practice_all || []).filter((q) => q.language === activePracticeLanguage).map((question) => <div className="practice-review-row" key={question.id}><div><strong>{question.prompt}</strong><span>{question.options.join(' · ')}</span></div>{question.approved ? <Status tone="success">Approved</Status> : <Button variant="secondary" onClick={() => void approvePractice(question)} disabled={!!busy}>Approve</Button>}</div>)}</div>}</div>
            {pack.artifacts.filter((item) => item.type === 'audio').length > 0 && <div className="artifact-list"><SectionTitle title="Prepared audio" subtitle="Protected audio is loaded with the signed user session." />{pack.artifacts.filter((item) => item.type === 'audio').map((artifact) => <div className="artifact-row" key={artifact.id}><div><strong>{label(artifact.language)}</strong><span>{Math.max(1, Math.round(artifact.size_bytes / 1024))} KB cached artifact</span></div>{artifactUrls[artifact.id] ? <audio controls src={artifactUrls[artifact.id]} /> : <Button variant="secondary" onClick={() => void (async () => { try { const blob = await api.fetchArtifact(artifact.id); setArtifactUrls((old) => ({ ...old, [artifact.id]: URL.createObjectURL(blob) })); } catch (err) { setError(errorMessage(err)); } })()}><Play size={15} /> Load audio</Button>}</div>)}</div>}
            <div className="wizard-nav"><Button variant="ghost" onClick={back}><ArrowLeft size={16} /> Back</Button><Button onClick={next}>Continue to review <ArrowRight size={16} /></Button></div>
          </Card>}

          {step === 5 && <Card><SectionTitle title="6. Review & publish" subtitle="Students only receive the published version. Publication is blocked until the complete package is approved." />
            <div className="preview-card"><div className="preview-top"><div><span className="eyebrow">STUDENT PREVIEW</span><h2>{title}</h2><p>{outcome}</p></div><Status tone={readiness.publish ? 'success' : 'warning'}>{readiness.publish ? 'Ready to publish' : 'Review required'}</Status></div><div className="preview-concepts">{concepts.filter(Boolean).map((concept) => <span key={concept}>{concept}</span>)}</div><div className="preview-source-strip"><strong>{nativeLabel(sourceLanguage)} · Original teacher source</strong><p>{transcript || source}</p></div><div className="preview-language-grid">{requiredLanguages.map((lang) => { const translation = translationByLanguage.get(lang); const approved = translation?.verification_status === 'TEACHER_APPROVED'; return <div className="preview-language" key={lang}><div><strong>{nativeLabel(lang)}</strong>{translation ? <Status tone={approved ? 'success' : 'warning'}>{translation.verification_status.replaceAll('_',' ')}</Status> : <Status>Not prepared</Status>}</div><p>{translation?.text || 'Not prepared yet.'}</p></div>; })}</div></div>
            <div className="publish-checklist"><div><Check size={15} /><span>Original source preserved</span></div><div><Check size={15} /><span>Learning outcome + concepts prepared</span></div><div><Check size={15} /><span>{requiredLanguages.map(label).join(' + ')} prepared and teacher-approved</span></div><div><Check size={15} /><span>{approvedPractice.length} approved practice question(s) across required languages</span></div><div><Check size={15} /><span>{audioReady ? 'All target-language audio prepared' : 'Target-language audio still required'}</span></div><div><Check size={15} /><span>Published package becomes eligible for offline sync</span></div></div>
            {!readiness.publish && <div className="blocker-panel"><strong>Still blocked</strong><ul>{readiness.problems.map((problem) => <li key={problem}>{problem.replaceAll('_',' ')}</li>)}</ul></div>}
            <div className="button-row wrap"><Button variant="secondary" onClick={createVersion} disabled={!!busy}><Layers size={15} /> Save as new version</Button><Button variant="secondary" onClick={() => void generateWorksheet()} disabled={!!busy}><Printer size={15} /> Worksheet preview</Button><Button onClick={() => void publish()} disabled={!readiness.publish || !!busy}><Send size={15} /> Publish lesson</Button></div>
            <div className="version-history"><SectionTitle title="Version history" subtitle="Restore only previously published versions; history is never deleted." />{versions.map((version) => <div className="version-row" key={version.id}><div><strong>Version {version.version_number}</strong><span>{new Date(version.created_at).toLocaleString()}</span></div><div>{version.published_at ? <Status tone="success">Published</Status> : <Status>Draft</Status>}{version.published_at && version.id !== pack.version.id && <Button variant="ghost" onClick={() => void rollback(version.id)} disabled={!!busy}>Restore</Button>}</div></div>)}</div>
          </Card>}
        </section>

        <aside className="builder-side"><Card className="sticky-card"><SectionTitle title="Live readiness" subtitle="This is based on actual backend state — not the current step number." /><div className="status-list"><Readiness label="Original lesson" ok={Boolean(source.trim() || transcript.trim())} text={source.trim() || transcript.trim() ? 'Ready' : 'Missing'} /><Readiness label="Learning outcome" ok={Boolean(outcome.trim())} text={outcome.trim() ? 'Ready' : 'Missing'} /><Readiness label="Concepts" ok={Boolean(concepts.filter(Boolean).length)} text={`${concepts.filter(Boolean).length} saved`} />{requiredLanguages.map((language) => { const translation = translationByLanguage.get(language); return <Readiness key={language} label={label(language)} ok={translation?.verification_status === 'TEACHER_APPROVED'} text={translation?.verification_status === 'TEACHER_APPROVED' ? 'Approved' : translation ? 'Review' : 'Not prepared'} />; })}<Readiness label="Practice" ok={practiceReady} text={practiceReady ? 'All target languages covered' : 'Target-language approval required'} />{audioReadyByLanguage.map(({ language, ready }) => <Readiness key={`audio-${language}`} label={`${label(language)} audio`} ok={ready} text={ready ? 'Ready' : 'Required'} />)}<Readiness label="Publish" ok={readiness.publish} text={readiness.publish ? 'Unlocked' : 'Blocked'} /></div><div className="side-hint"><strong>Why is it blocked?</strong><p>{readiness.publish ? 'Everything required for publication has been prepared and approved.' : readiness.problems.join(' • ')}</p></div></Card><Card><SectionTitle title="Core loop" /><div className="mini-flow"><span>Speak / write</span><b>↓</b><span>Understand</span><b>↓</b><span>Concepts</span><b>↓</b><span>Translate + verify</span><b>↓</b><span>Publish + sync</span><b>↓</b><span>Learn + practice</span></div></Card></aside>
      </div>
    </Page>

    {worksheetOpen && <Modal title="Worksheet preview" onClose={() => setWorksheetOpen(false)} wide><div className="worksheet-preview-actions"><Status tone="success">No pop-up required</Status><Button variant="secondary" onClick={() => worksheetFrame.current?.contentWindow?.print()}><Printer size={15} /> Print / Save PDF</Button><Button variant="ghost" onClick={() => setWorksheetOpen(false)}>Close</Button></div><iframe ref={worksheetFrame} className="worksheet-frame" title="BhashaSaathi worksheet" srcDoc={worksheetHtml} /></Modal>}
  </>;
}

function Readiness({ label, ok, text }: { label: string; ok: boolean; text: string }) {
  return <div><span>{label}</span><Status tone={ok ? 'success' : 'warning'}>{text}</Status></div>;
}
