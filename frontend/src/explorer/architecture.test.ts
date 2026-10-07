// Les garde-fous du découpage de l'explorateur (TAXO-01J, « Découpage architectural ») : les modules purs n'atteignent
// React ni le réseau, même par un module importé ; seul `protocol.ts` parle au serveur, et seulement au protocole ; rien
// n'appelle Minia ; aucune ligne ne nomme une relation ou un type de référence.
import {readFileSync, readdirSync} from 'node:fs';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {describe, expect, it} from 'vitest';
import {VERBS} from '../vocabulary';

const HERE=dirname(fileURLToPath(import.meta.url));
const PURE=['graph.ts', 'layout.ts', 'chain.ts', 'sentences.ts', 'state.ts', 'relations.ts', 'protocol.ts'];
const SOURCES=readdirSync(HERE).filter(name=>/\.tsx?$/.test(name)&&!name.includes('.test.'));

/** Les modules qu'un fichier importe pour de vrai (un import de type seul ne charge rien). */
function imports(file:string){
  const text=readFileSync(file, 'utf8');
  return [...text.matchAll(/^import\s+(?!type\s)[^'"]*['"]([^'"]+)['"]/gm)].map(match=>match[1]);
}

/** Tout ce qu'un module charge, de proche en proche ; les paquets sont rendus par leur nom. */
function closure(file:string, seen=new Set<string>()):Set<string>{
  for(const target of imports(file)){
    if(!target.startsWith('.')){seen.add(target);continue;}
    const base=resolve(dirname(file), target);
    const found=['.ts', '.tsx'].map(extension=>`${base}${extension}`).find(path=>{try{readFileSync(path);return true;}catch{return false;}});
    if(found&&!seen.has(found)){seen.add(found);closure(found, seen);}
  }
  return seen;
}

describe('le découpage de l’explorateur', ()=>{
  it('ses modules purs n’atteignent ni React ni le réseau, même indirectement', ()=>{
    for(const name of PURE){
      const reached=[...closure(join(HERE, name))];
      expect(reached.filter(item=>!item.startsWith('/')), name).toEqual([]);
      for(const path of [join(HERE, name), ...reached])expect(readFileSync(path, 'utf8'), path).not.toMatch(/\bfetch\(|XMLHttpRequest|EventSource/);
    }
  });

  it('seul protocol.ts construit une demande au serveur, et seulement au protocole ; rien n’appelle Minia', ()=>{
    for(const name of SOURCES){
      const text=readFileSync(join(HERE, name), 'utf8');
      expect(text, name).not.toMatch(/minia/i);
      if(name!=='protocol.ts')expect(text, name).not.toMatch(/taxo-query|\/api\//);
    }
    expect(readFileSync(join(HERE, 'protocol.ts'), 'utf8')).toContain('/taxo-query');
  });

  it('ne nomme aucune relation ni aucun type de référence', ()=>{
    const relations=new RegExp(`\\b(${Object.keys(VERBS).join('|')})\\b`);
    const types=/['"`](endpoint|module|symbol|file|commit|repository|route-pattern|policy-rule|application|technology|language):/;
    for(const name of SOURCES){
      const text=readFileSync(join(HERE, name), 'utf8');
      expect(text, name).not.toMatch(relations);
      expect(text, name).not.toMatch(types);
    }
  });
});
