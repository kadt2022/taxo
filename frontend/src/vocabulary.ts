// Vocabulaire de presentation (TAXO-UI-01) : le contrat de faits reste la representation interne de Taxo ;
// ces libelles en sont la lecture humaine. Rien n'est renomme cote backend : un terme inconnu s'affiche tel quel.

export const EVALUATORS:Record<string,string>={'taxo.inventory':'Inventaire du code', 'taxo.git':'Historique Git', 'taxo.spring-api':'Endpoints Spring',
  'taxo.spring-boot':'Applications Spring Boot', 'taxo.spring-security':'Sécurité Spring', 'taxo.structure':'Structure du dépôt'};

export const STATUSES:Record<string,string>={SUCCESS:'Terminée', PARTIAL:'Partielle', FAILED:'Échec',
  UNSUPPORTED:'Non pris en charge'};

export const COVERAGE:Record<string,string>={ANALYSED:'Analysé', NOT_INTERPRETED:'Non analysé par Taxo', READ_ERROR:'Illisible',
  OUT_OF_SCOPE:'Hors de son périmètre'};

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

/** La forme d'une relation dans la vue Chaîne (TAXO-UI-06, E1) : dans la chaîne, sujet au-dessus, ou à côté, comme la
 * réalisation UML. Une relation absente est dans la chaîne. */
export const FORMS:Record<string,'CHAIN'|'SIDE'>={IMPLEMENTS:'SIDE'};

/** La teinte d'un type de référence (TAXO-UI-06, E7) : un jeton CSS `--tone-<teinte>`. L'orange des frontières n'en est
 * pas une. Un type absent prend la teinte neutre. */
export const TONES:Record<string,string>={endpoint:'route', symbol:'symbol', module:'module', repository:'module',
  file:'file', application:'app', 'policy-rule':'policy', 'route-pattern':'policy', commit:'history', person:'history',
  technology:'tech', language:'tech'};
/** Ce que chaque teinte désigne, pour la légende. */
export const TONE_NAMES:Record<string,string>={route:'route', symbol:'symbole', module:'module, dépôt', file:'fichier',
  app:'application', policy:'règle, motif de routes', history:'commit, personne', tech:'technologie, langage',
  neutral:'autre type'};

/** Le statut d'un fait en une lettre, sur sa flèche : observé, déduit, validé. */
export const STATUS_MARKS:Record<string,string>={OBSERVED:'O', INFERRED:'D', HUMAN_VALIDATED:'V'};

export function label(labels:Record<string,string>, key:string){
  return labels[key]??key;
}

export const TYPES:Record<string,string>={technology:'technologie', language:'langage', module:'module', symbol:'symbole',
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
export const VALIDITIES:Record<string,string>={VALID:'Valide', STALE:'Périmé', REVALIDATION_REQUIRED:'À revérifier'};

