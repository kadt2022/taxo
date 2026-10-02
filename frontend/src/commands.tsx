// Les commandes de la barre du haut (TAXO-UI-05) : Analyse est un panneau de commande, pas une liste. Il lance une analyse du
// projet actif et mene a la derniere ; consulter les analyses existantes reste la page Analyses.
import {day, sideLabel} from './comparison';
import {href} from './nav';
import {sideOf} from './pages';
import {type Scan} from './overview';

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
