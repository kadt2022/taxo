// Le poste de lancement de la page Analyses (TAXO-UI-05).
import {day, sideLabel} from './comparison';
import {sideOf} from './pages';
import {type Scan} from './overview';
import {type Run, type StepState} from './analysis';

const PLAY=<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5l12 7-12 7z"/></svg>;

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
