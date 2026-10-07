// Rendu humain deterministe des faits (TAXO-UI-01). Le contrat reste la verite : une relation canonique, un sujet et
// un objet types. Ce module ne remplace aucune chaine : il lit la structure, puis choisit la phrase selon la relation
// ET le type de chaque cote. Un cas qu'il ne connait pas est dit de facon neutre, jamais devine.
import {VERBS, reference} from './vocabulary';

type Project={id:string; name:string};
/** Une reference du contrat `type:cle`, lue une fois. */
export type Entity={type:string; key:string; raw:string};
/** Une phrase : du texte, et des noms a montrer tels quels (route, methode, motif, role). */
export type Segment=string|{code:string};
export type Sentence=Segment[];

export function entity(raw:string):Entity{
  const at=raw.indexOf(':');
  return at<0?{type:'', key:raw, raw}:{type:raw.slice(0, at), key:raw.slice(at+1), raw};
}

/** Le nom court d'une entite : `OrderController.get()`, l'application par sa classe, le depot par le projet. */
export function name(item:Entity, project?:Project){
  if(item.type==='symbol'){
    const symbol=item.key.startsWith('java:')?item.key.slice(5):item.key, hash=symbol.indexOf('#');
    const owner=(hash<0?symbol:symbol.slice(0, hash)).split('.').pop();
    return hash<0?owner??symbol:`${owner}.${symbol.slice(hash+1)}`;
  }
  if(item.type==='application'&&item.key.includes('#'))return item.key.slice(item.key.lastIndexOf('#')+1);
  if(item.type==='repository')return project&&item.key===project.id?project.name:item.key;
  if(item.type==='commit')return item.key.slice(0, 12);
  return item.key;
}

const code=(item:Entity, project?:Project):Segment=>({code:name(item, project)});

/** Un symbole se dit par sa forme (ARCHITECTURE § 5.3) : `T#m(…)` une méthode, `T#champ` un champ, `T` une classe. */
function symbolNoun(key:string){
  if(key.includes('('))return 'la méthode ';
  return key.includes('#')?'le champ ':'la classe ';
}

/** Le groupe nominal d'une entite, selon son type. */
function noun(item:Entity, project?:Project):Sentence{
  const shown=code(item, project);
  switch(item.type){
  case 'endpoint':return ['la route ', shown];
  case 'symbol':return [symbolNoun(item.key), shown];
  case 'application':return ['l’application ', shown];
  case 'module':return ['le module ', shown];
  case 'route-pattern':return ['le motif ', shown];
  case 'policy-rule':return ['la règle ', shown];
  case 'file':return ['le fichier ', shown];
  case 'technology':return ['la technologie ', shown];
  case 'language':return ['le langage ', shown];
  case 'commit':return ['le commit ', shown];
  case 'repository':return ['le dépôt ', shown];
  case 'person':return [shown];
  default:return [{code:reference(item.raw)??item.raw}];
  }
}

/** Ce qu'exige une expression Spring Security connue ; une autre expression est montree telle quelle. */
export function requirement(expression:string):Sentence{
  // Un seul appel simple `nom(arguments)` : une expression composee n'est jamais interpretee.
  const open=expression.indexOf('('), inner=expression.slice(open+1, -1);
  const simple=open>0&&expression.endsWith(')')&&/^\w+$/.test(expression.slice(0, open))&&!/[()]/.test(inner);
  const call=simple?expression.slice(0, open):'';
  const args=call?inner.split(',').map(item=>item.trim().replace(/^["']|["']$/g, '')).filter(Boolean):[];
  const listed=(values:string[])=>values.flatMap((value, index):Sentence=>index?[', ', {code:value}]:[{code:value}]);
  switch(call){
  case 'authenticated':return ['exige que l’utilisateur soit authentifié'];
  case 'fullyAuthenticated':return ['exige une authentification complète'];
  case 'permitAll':return ['est ouverte à tous'];
  case 'denyAll':return ['refuse tout accès'];
  case 'anonymous':return ['n’admet que les utilisateurs anonymes'];
  case 'hasRole':return args.length===1?['exige le rôle ', {code:args[0]}]:['applique ', {code:expression}];
  case 'hasAnyRole':return ['exige l’un des rôles ', ...listed(args)];
  case 'hasAuthority':return args.length===1?['exige l’autorisation ', {code:args[0]}]:['applique ', {code:expression}];
  case 'hasAnyAuthority':return ['exige l’une des autorisations ', ...listed(args)];
  default:return ['applique ', {code:expression}];
  }
}

const policy=(item:Entity)=>item.type==='policy-rule'?item.key:item.raw;

/** Les phrases propres a une relation, quand les types des deux cotes sont ceux qu'elle attend. */
const RULES:Record<string, (subject:Entity, object:Entity, project?:Project)=>Sentence|null>={
  HANDLED_BY:(subject, object, project)=>subject.type==='endpoint'&&object.type==='symbol'
    ?['la requête ', code(subject), ' est traitée par ', code(object, project)]:null,
  SERVED_BY:(subject, object, project)=>subject.type==='endpoint'&&object.type==='application'
    ?['la route ', code(subject), ' est exposée par ', ...noun(object, project)]:null,
  MATCHED_BY:(subject, object)=>subject.type==='endpoint'&&(object.type==='route-pattern'||object.type==='')
    ?['la route ', code(subject), ' correspond au motif ', code(object)]:null,
  PROTECTED_BY:(subject, object)=>subject.type==='endpoint'?['la route ', code(subject), ' ', ...requirement(policy(object))]:null,
  AUTHORIZED_BY:(subject, object)=>subject.type==='route-pattern'||subject.type===''
    ?['le motif ', {code:subject.key}, ' ', ...requirement(policy(object))]:null,
  PERMITS_ALL:subject=>subject.type==='endpoint'?['la route ', code(subject), ' est ouverte à tous']:null,
  BUILT_FROM:(subject, object, project)=>subject.type==='application'&&object.type==='module'
    ?[...noun(subject, project), ' est construite à partir du module ', code(object)]:null,
  DEPENDS_ON:(subject, object)=>subject.type==='module'&&object.type==='module'
    ?['le module ', code(subject), ' dépend du module ', code(object)]:null,
  WRITTEN_IN:(subject, object, project)=>[...noun(subject, project), ' est écrit en ', code(object)],
  HAS_COMMIT:(subject, object, project)=>[...noun(subject, project), ' contient ', ...noun(object, project)],
  CHILD_OF:(subject, object, project)=>[...noun(subject, project), ' suit ', ...noun(object, project)],
  // Entre types, l'objet est une interface ; entre methodes, chaque cote se dit par sa forme (TAXO-01K).
  IMPLEMENTS:(subject, object)=>subject.type==='symbol'&&object.type==='symbol'&&!subject.key.includes('#')
    &&!object.key.includes('#')?[...noun(subject), ' implémente l’interface ', code(object)]:null,
  TYPED_AS:(subject, object)=>subject.type==='symbol'&&object.type==='symbol'
    ?[...noun(subject), ' est déclaré du type ', code(object)]:null,
};

/** Le debut d'une phrase prend une majuscule ; elle se termine par un point. */
function finished(sentence:Sentence, detail=''):Sentence{
  const [first, ...rest]=sentence;
  const head=typeof first==='string'?first.charAt(0).toUpperCase()+first.slice(1):first;
  return [head, ...rest, `${detail}.`];
}

/** Une relation canonique dite en francais, selon les types de ses deux cotes. */
export function relation(canonical:string, subject:Entity, object:Entity, project?:Project, detail=''):Sentence{
  const typed=Object.hasOwn(RULES, canonical)?RULES[canonical](subject, object, project):null;
  const verb=Object.hasOwn(VERBS, canonical)?VERBS[canonical]:canonical;
  return finished(typed??[...noun(subject, project), ` ${verb} `, ...noun(object, project)], detail);
}

/** Le sujet seul, pour titrer un changement dont l'objet differe d'un cote a l'autre. */
export const subjectOf=(raw:string, project?:Project)=>finished(noun(entity(raw), project)).slice(0, -1);

/**
 * Une premisse, telle que les evaluateurs l'ecrivent, lue en structure puis dite en clair :
 * `RELATION : sujet -> objet (precision)`, `ligne N : [verbe] motifs -> expression`, `ligne N : regle non lue (raison)`,
 * `application charge configuration`. Toute autre forme est rendue telle quelle.
 */
export function premise(text:string, project?:Project):Sentence{
  const colon=text.indexOf(' : '), arrow=text.indexOf(' -> ');
  const head=colon>0?text.slice(0, colon):'';
  if(head.startsWith('ligne ')){
    const line=head.slice(6), body=text.slice(colon+3);
    if(arrow>colon)return finished(['la règle ', {code:text.slice(colon+3, arrow)}, ' ', ...requirement(text.slice(arrow+4))], ` (ligne ${line})`);
    if(body.startsWith('règle non lue'))return finished([`la règle de la ligne ${line} n’a pas pu être lue`], body.slice('règle non lue'.length));
  }
  if(arrow>colon&&Object.hasOwn(VERBS, head)){
    let right=text.slice(arrow+4), detail='';
    const open=right.lastIndexOf(' (');
    if(open>0&&right.endsWith(')')){detail=` (${right.slice(open+2, -1)})`;right=right.slice(0, open);}
    return relation(head, entity(text.slice(colon+3, arrow)), entity(right), project, detail);
  }
  const loads=text.split(' charge ');
  if(loads.length===2&&!loads[0].includes(' ')&&!loads[1].includes(' ')){
    return finished([...noun(entity(loads[0]), project), ' charge la configuration de sécurité ', code(entity(loads[1]))]);
  }
  return [text];
}

/** La phrase en texte simple, pour un titre ou un test. */
export const plain=(sentence:Sentence)=>sentence.map(item=>typeof item==='string'?item:item.code).join('');
