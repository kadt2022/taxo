// Vocabulaire de presentation (TAXO-UI-01) : le contrat de faits reste la representation interne de Taxo ;
// ces libelles en sont la lecture humaine. Rien n'est renomme cote backend : un terme inconnu s'affiche tel quel.

export const EVALUATORS:Record<string,string>={'taxo.inventory':'Inventaire du code', 'taxo.git':'Historique Git', 'taxo.spring-api':'Endpoints Spring'};

export const STATUSES:Record<string,string>={SUCCESS:'Terminée', PARTIAL:'Partielle', FAILED:'Échec'};

export const COVERAGE:Record<string,string>={ANALYSED:'Analysé', NOT_INTERPRETED:'Non analysé par Taxo', READ_ERROR:'Illisible'};

export const METRICS:Record<string,string>={fact_count:'Éléments identifiés', coverage_count:'Zones de couverture',
  warning_count:'Points à vérifier', duration_seconds:'Durée'};

/** Ce qu'une relation designe, quand on la compte. */
export const RELATIONS:Record<string,string>={CONTAINS:'Fichiers du projet', WRITTEN_IN:'Fichiers par langage',
  USES_TECHNOLOGY:'Technologies utilisées', DECLARED_BY:'Déclarations de technologie', HAS_COMMIT:'Commits',
  AUTHORED_BY:'Auteur', CHILD_OF:'Liens de parenté entre commits', CHANGES:'Fichiers modifiés',
  ANNOTATED_WITH:'Annotations', CALLS:'Appels', IMPLEMENTS:'Implémentations', DISPATCHES_TO:'Délégations',
  HANDLED_BY:'Routes traitées', ACCEPTS:'Entrées acceptées', RETURNS:'Réponses renvoyées',
  PERMITS_ALL:'Routes ouvertes à tous', AUTHORIZED_BY:'Autorisations', MATCHED_BY:'Correspondances de routes',
  PROTECTED_BY:'Protections'};

/** Ce qu'une relation affirme, dans une phrase « sujet verbe objet ». */
export const VERBS:Record<string,string>={CONTAINS:'contient', WRITTEN_IN:'est écrit en', USES_TECHNOLOGY:'utilise',
  DECLARED_BY:'est déclarée dans', HAS_COMMIT:'contient le', AUTHORED_BY:'a pour auteur', CHILD_OF:'suit le',
  CHANGES:'modifie', ANNOTATED_WITH:'est annoté', CALLS:'appelle', IMPLEMENTS:'implémente', DISPATCHES_TO:'délègue à',
  HANDLED_BY:'est traité par', ACCEPTS:'accepte', RETURNS:'renvoie', PERMITS_ALL:'est ouvert à tous',
  AUTHORIZED_BY:'est autorisé par', MATCHED_BY:'correspond à', PROTECTED_BY:'est protégé par'};

export function label(labels:Record<string,string>, key:string){
  return labels[key]??key;
}

const TYPES:Record<string,string>={technology:'technologie', language:'langage', module:'module', symbol:'symbole',
  endpoint:'route', 'route-pattern':'routes', person:'', file:'', commit:'commit'};

/** Une reference `type:cle` dite en clair : le depot par le nom du projet, un commit par son identifiant court. */
export function reference(value:string|null, project?:{id:string; name:string}){
  if(value===null)return null;
  if(project&&value===`repository:${project.id}`)return `dépôt ${project.name}`;
  const at=value.indexOf(':');
  if(at<0)return value;
  const type=value.slice(0,at), key=value.slice(at+1);
  if(type==='repository')return `dépôt ${key}`;
  if(!(type in TYPES))return value;
  const shown=type==='commit'?key.slice(0,12):key;
  return TYPES[type]?`${TYPES[type]} ${shown}`:shown;
}
