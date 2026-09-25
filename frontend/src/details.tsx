// Details de l'analyse (TAXO-UI-01) : le deuxieme niveau de lecture, pour verifier Taxo.
// Rien n'y est cache ni renomme : identifiants, versions, couverture et relations restent visibles, avec leur
// libelle humain a cote du terme interne.
import {COVERAGE, EVALUATORS, METRICS, RELATIONS, STATUSES, label} from './vocabulary';
import {evaluationsOf, type EvaluationSummary, type Scan} from './overview';

const date=(value:string)=>new Date(value).toLocaleString('fr-CA');
const count=(value:number)=>value.toLocaleString('fr-CA');
const subject=(value:string)=>value.startsWith('repository:')?'repository':value.replace(/^file:/,'');

export function EvaluationPanel({summary}:Readonly<{summary:EvaluationSummary}>){
  const relations=Object.entries(summary.relations);
  const duration=new Intl.NumberFormat('fr-CA',{minimumFractionDigits:1,maximumFractionDigits:1}).format(summary.duration_seconds)+' s';
  return <section className="evaluation" aria-label={`Exécution : ${label(EVALUATORS,summary.evaluator_id)}`}>
    <h3>{label(EVALUATORS,summary.evaluator_id)}</h3>
    <div className="evaluation-metrics">
      <div><strong className={'status status-'+summary.status.toLowerCase()}>{label(STATUSES,summary.status)}</strong><span>Statut</span></div>
      <div><strong>{duration}</strong><span>{METRICS.duration_seconds}</span></div>
      <div><strong>{count(summary.fact_count)}</strong><span>{METRICS.fact_count}</span></div>
      <div><strong>{count(summary.coverage_count)}</strong><span>{METRICS.coverage_count}</span></div>
      <div><strong>{count(summary.warning_count)}</strong><span>{METRICS.warning_count}</span></div>
    </div>
    <div className="evaluation-details">
      <section><h4>Exécution</h4><dl>
        <div><dt>Évaluateur</dt><dd>{summary.evaluator_id}</dd></div>
        <div><dt>Version</dt><dd>{summary.producer_version}</dd></div>
        <div><dt>Execution ID</dt><dd><code>{summary.execution_id}</code></dd></div>
        <div><dt>Commit</dt><dd><code title={summary.snapshot.commit}>{summary.snapshot.commit.slice(0,12)}…</code></dd></div>
        <div><dt>Statut</dt><dd>{summary.status}</dd></div>
        <div><dt>Début</dt><dd>{date(summary.started_at)}</dd></div>
        <div><dt>Fin</dt><dd>{date(summary.finished_at)}</dd></div>
      </dl></section>
      <section><h4>Couverture</h4>
        {summary.coverage.length?<div className="table-wrap"><table><thead><tr><th>Type</th><th>Zones</th><th>Nombre</th></tr></thead><tbody>
          {summary.coverage.map(group=><tr key={group.coverage_type}><td>{label(COVERAGE,group.coverage_type)} <span className="muted">{group.coverage_type}</span></td><td>{group.subjects.map(value=><code className="coverage-subject" key={value}>{subject(value)}</code>)}{group.count>group.subjects.length&&<span className="muted">+ {group.count-group.subjects.length} autres</span>}</td><td>{count(group.count)}</td></tr>)}
        </tbody></table></div>:<p className="muted">Aucune couverture détaillée disponible.</p>}
      </section>
      <section><h4>Faits par relation</h4>
        {relations.length?<div className="table-wrap"><table><thead><tr><th>Élément</th><th>Relation</th><th>Nombre</th></tr></thead><tbody>
          {relations.map(([relation,value])=><tr key={relation}><td>{label(RELATIONS,relation)}</td><td><code>{relation}</code></td><td>{count(value)}</td></tr>)}
        </tbody></table></div>:<p className="muted">Aucun fait produit.</p>}
      </section>
    </div>
  </section>;
}

/** Deuxieme niveau de lecture : replie par defaut, il contient tout ce qui sert a verifier l'analyse. */
export function AnalysisDetails({scan}:Readonly<{scan:Scan}>){
  const warnings=[...new Set(scan.warnings??[])];
  return <details className="analysis-details">
    <summary>Détails de l’analyse</summary>
    <p className="muted">Ce que Taxo a exécuté pour produire cette vue : évaluateurs, versions, couverture, relations et avertissements.</p>
    {evaluationsOf(scan).map(summary=><EvaluationPanel key={summary.execution_id} summary={summary}/>)}
    {warnings.length>0&&<section className="evaluation"><h3>Avertissements</h3><ul>{warnings.map(w=><li key={w}>{w}</li>)}</ul></section>}
  </details>;
}
