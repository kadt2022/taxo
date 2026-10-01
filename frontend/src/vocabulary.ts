// Vocabulaire de presentation (TAXO-UI-01) : le contrat de faits reste la representation interne de Taxo ;
// ces libelles en sont la lecture humaine. Rien n'est renomme cote backend : un terme inconnu s'affiche tel quel.

export const EVALUATORS:Record<string,string>={'taxo.inventory':'Inventaire du code', 'taxo.git':'Historique Git', 'taxo.spring-api':'Endpoints Spring',
  'taxo.spring-boot':'Applications Spring Boot', 'taxo.spring-security':'Sécurité Spring', 'taxo.structure':'Structure du dépôt'};

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
  PROTECTED_BY:'Protections', DEPENDS_ON:'Dépendances entre modules', BUILT_FROM:'Applications construites',
  SERVED_BY:'Routes servies'};

/** Ce qu'une relation affirme, dans une phrase « sujet verbe objet ». */
export const VERBS:Record<string,string>={CONTAINS:'contient', WRITTEN_IN:'est écrit en', USES_TECHNOLOGY:'utilise',
  DECLARED_BY:'est déclarée dans', HAS_COMMIT:'contient le', AUTHORED_BY:'a pour auteur', CHILD_OF:'suit le',
  CHANGES:'modifie', ANNOTATED_WITH:'est annoté', CALLS:'appelle', IMPLEMENTS:'implémente', DISPATCHES_TO:'délègue à',
  HANDLED_BY:'est traité par', ACCEPTS:'accepte', RETURNS:'renvoie', PERMITS_ALL:'est ouvert à tous',
  AUTHORIZED_BY:'est autorisé par', MATCHED_BY:'correspond à', PROTECTED_BY:'est protégé par',
  DEPENDS_ON:'dépend de', BUILT_FROM:'est construite depuis',
  SERVED_BY:'est servie par'};

export function label(labels:Record<string,string>, key:string){
  return labels[key]??key;
}

const TYPES:Record<string,string>={technology:'technologie', language:'langage', module:'module', symbol:'symbole',
  endpoint:'route', 'route-pattern':'routes', 'policy-rule':'règle', application:'application', person:'', file:'', commit:'commit'};

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

/** D'ou vient un fait. Une validation humaine reste distincte de ce que Taxo deduit ou observe. */
export const ORIGINS:Record<string,string>={OBSERVED:'Observé dans le code', INFERRED:'Déduit par Taxo',
  HUMAN_VALIDATED:'Validé par une personne'};

/** Ou en est un fait : rien ne dit ici qu'une personne l'a confirme. */
export const VALIDITIES:Record<string,string>={VALID:'À jour', STALE:'Périmé', REVALIDATION_REQUIRED:'À revérifier'};

/** Une reference nommee court, pour une phrase : `OrderController.get()`, l'application par son nom. */
export function named(value:string, project?:{id:string; name:string}){
  if(value.startsWith('symbol:java:')){
    const symbol=value.slice('symbol:java:'.length), hash=symbol.indexOf('#');
    const owner=(hash<0?symbol:symbol.slice(0,hash)).split('.').pop();
    return hash<0?owner:`${owner}.${symbol.slice(hash+1)}`;
  }
  if(value.startsWith('application:')&&value.includes('#'))return `application ${value.slice(value.lastIndexOf('#')+1)}`;
  return reference(value, project)??value;
}

/**
 * Une premisse d'inference dite en clair. Les evaluateurs l'ecrivent `RELATION : sujet -> objet (precision)`,
 * `ligne N : motif -> regle` ou `application charge configuration` ; toute autre forme s'affiche telle quelle.
 */
export function premise(text:string, project?:{id:string; name:string}){
  const colon=text.indexOf(' : '), arrow=text.indexOf(' -> ');
  if(colon>0&&arrow>colon){
    const head=text.slice(0,colon), left=text.slice(colon+3, arrow);
    let right=text.slice(arrow+4), detail='';
    const open=right.lastIndexOf(' (');
    if(open>0&&right.endsWith(')')){detail=` (${right.slice(open+2,-1)})`;right=right.slice(0,open);}
    if(Object.hasOwn(VERBS, head))return `${named(left, project)} ${VERBS[head]} ${named(right, project)}${detail}`;
    if(head.startsWith('ligne '))return `Règle de sécurité, ${head} : ${left} → ${right}${detail}`;
  }
  const loads=text.split(' charge ');
  if(loads.length===2&&!loads[0].includes(' '))return `${named(loads[0], project)} charge ${named(loads[1], project)}`;
  return text;
}
