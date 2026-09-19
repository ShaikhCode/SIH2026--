import { ArrowRight, BookOpen, Languages, LockKeyhole, WifiOff } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Button, Card, Status } from '../components/UI';

export default function LandingPage() {
  return <div className="auth-page landing-page"><div className="landing-shell"><header className="landing-nav"><div className="auth-brand"><div className="auth-logo">भा</div><div><strong>BhashaSaathi</strong><span>Translate the classroom, not just the words.</span></div></div><div className="head-action-row"><Link to="/login"><Button variant="ghost">Sign in</Button></Link><Link to="/register"><Button>Create account <ArrowRight size={15} /></Button></Link></div></header><section className="landing-hero"><div className="landing-copy"><Status tone="success">Local-first · Teacher-controlled · Offline-ready</Status><h1>One lesson.<br /><span>Every learner's language.</span></h1><p>Turn a teacher's Hindi lesson into a reviewed, multilingual learning experience — with concepts, translation, audio, practice and offline delivery.</p><div className="head-action-row"><Link to="/login"><Button>Open educator workspace <ArrowRight size={16} /></Button></Link><Link to="/register"><Button variant="secondary">Create account</Button></Link></div></div><Card className="landing-loop"><div className="eyebrow">THE CORE LOOP</div><div className="landing-flow"><Flow icon={<BookOpen />} text="Speak / write" /><span>↓</span><Flow icon={<Languages />} text="Translate + verify" /><span>↓</span><Flow icon={<WifiOff />} text="Publish + sync" /><span>↓</span><Flow icon={<BookOpen />} text="Learn + practice" /></div></Card></section><section className="landing-features"><Feature icon={<Languages />} title="Hindi · English · Marathi" body="Build one canonical lesson and prepare the languages you actually need." /><Feature icon={<LockKeyhole />} title="Teacher stays in control" body="AI prepares drafts. The educator reviews and approves before publication." /><Feature icon={<WifiOff />} title="Learning continues offline" body="Published text, audio, worksheets and practice can stay on the learner's device." /></section></div></div>;
}

function Flow({ icon, text }: { icon: ReactNode; text: string }) {
  return <div className="landing-flow-item"><div>{icon}</div><span>{text}</span></div>;
}

function Feature({ icon, title, body }: { icon: ReactNode; title: string; body: string }) {
  return <Card className="landing-feature"><div className="metric-icon">{icon}</div><strong>{title}</strong><p>{body}</p></Card>;
}
