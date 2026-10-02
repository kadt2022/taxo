// Les commandes de la barre du haut (TAXO-UI-05) : Analyse est un panneau de commande, pas une liste. Il lance une analyse du
// projet actif et mene a la derniere ; consulter les analyses existantes reste la page Analyses.
import {day, sideLabel} from './comparison';
import {href} from './nav';
import {sideOf} from './pages';
import {type Scan} from './overview';
import {type Run, type StepState} from './analysis';

type Props={project?:{name:string}; latest?:Scan; running:boolean; canAnalyze:boolean; onAnalyze:()=>void; onClose:()=>void};

const PLAY=<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5l12 7-12 7z"/></svg>;

/** Le panneau Analyse : lancer une analyse du projet actif, retrouver la derniere, aller aux analyses et aux comparaisons. */
export function AnalysisCommand({project, latest, running, canAnalyze, onAnalyze, onClose}:Readonly<Props>){
  if(!project)return <div className="command">
    <section><h3>Nouvelle analyse</h3><p>Sélectionnez d’abord un projet.</p>
      <a className="primary command-main" href={href('projets')} onClick={onClose}>Choisir un projet</a></section>
  </div>;
  const launch=latest?'Lancer l’analyse globale':'Lancer la première analyse';
  return <div className="command">
    <section>
      <h3>Nouvelle analyse</h3>
      <p>Analyse le projet actif et enregistre un nouvel état Taxo, sans modifier les analyses déjà faites.</p>
      <dl><dt>Projet</dt><dd>{project.name}</dd></dl>
      {!latest&&<p className="command-empty">Aucune analyse pour ce projet.</p>}
      <button type="button" className="primary command-main" disabled={running||!canAnalyze} onClick={()=>{onClose();onAnalyze();}}>
        {PLAY}{running?'Analyse en cours…':launch}</button>
    </section>
    {latest&&<section>
      <h3>Dernière analyse</h3>
      <p className="command-when">{day(latest.created_at)}</p>
      <p className="command-code"><code>{sideLabel(sideOf(latest))}</code></p>
      <a className="ghost" href={href('analyses', latest.id)} onClick={onClose}>Voir l’analyse</a>
    </section>}
    <nav className="command-links" aria-label="Analyses existantes">
      <a href={href('analyses')} onClick={onClose}>Toutes les analyses <span aria-hidden="true">→</span></a>
      <a href={href('comparaisons')} onClick={onClose}>Comparer deux analyses <span aria-hidden="true">→</span></a>
    </nav>
  </div>;
}

const STATE_LABELS:Record<StepState, string>={pending:'à venir', running:'en cours', done:'terminée', failed:'en échec'};

/** La page Analyses s'ouvre sur ce poste de lancement : lancer une analyse du projet actif, puis la suivre etape par etape.
 * Chaque segment de la piste est une etape reelle annoncee par le serveur : rien n'est estime. */
export function LaunchCard({project, latest, count, run, canAnalyze, onAnalyze}:Readonly<{project?:{name:string}; latest?:Scan; count:number;
  run:Run|null; canAnalyze:boolean; onAnalyze:()=>void}>){
  const live=run&&run.status!=='done'?run:null;
  const running=live?.status==='running', failed=live?.status==='failed';
  const settled=live?.steps.filter(step=>step.state==='done'||step.state==='failed').length??0;
  const current=live?.steps.find(step=>step.state==='running');
  const launch=latest?'Lancer l’analyse globale':'Lancer la première analyse';
  return <section className={`launch${running?' is-running':''}${failed?' is-failed':''}`} aria-label="Nouvelle analyse">
    <div className="launch-mark" aria-hidden="true">{running?<span className="launch-spin"/>:PLAY}</div>
    <div className="launch-body">
      <span className="launch-eyebrow">{running?'Analyse en cours':failed?'Analyse interrompue':'Nouvelle analyse'}</span>
      <h2>{project?`${running?'Analyse de':'Analyser'} ${project.name}${running?'…':' maintenant'}`:'Choisissez un projet'}</h2>
      {!live&&<p>Taxo lit le dépôt local sans l’exécuter, fait travailler ses analyseurs et enregistre un nouvel état. Les analyses déjà faites ne changent pas.</p>}
      {live&&<>
        <ol className="launch-track" aria-label={`${settled} étape${settled>1?'s':''} sur ${live.steps.length} terminée${settled>1?'s':''}`}>{live.steps.map(step=>
          <li key={step.id} className={`track-${step.state}`} title={`${step.label} : ${STATE_LABELS[step.state]}`}/>)}</ol>
        <p className="launch-status" aria-live="polite">
          <span>{failed?<strong>{live.message||'L’analyse s’est arrêtée.'}</strong>
            :current?<><strong>{current.label}</strong>{current.detail&&<> · {current.detail}</>}</>:'Démarrage…'}</span>
          <span className="launch-count">{settled} étape{settled>1?'s':''} sur {live.steps.length}</span></p>
      </>}
      {!live&&<ul className="launch-meta">
        {latest?<li><i aria-hidden="true"/>Dernière : {day(latest.created_at)} · <code>{sideLabel(sideOf(latest))}</code></li>:<li><i aria-hidden="true"/>Aucune analyse pour ce projet.</li>}
        {count>0&&<li>{count} analyse{count>1?'s':''} enregistrée{count>1?'s':''}</li>}
      </ul>}
    </div>
    <button type="button" className="launch-button" disabled={running||!canAnalyze||!project} onClick={onAnalyze}>
      {running?'Analyse en cours…':<>{PLAY}{failed?'Relancer l’analyse':launch}</>}</button>
  </section>;
}
