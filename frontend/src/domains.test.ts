import {describe, expect, it} from 'vitest';
import {byDomain, domainOf, phrase} from './domains';
import type {EvaluatorEntry} from './comparison';

const entry=(evaluator_id:string, relations:Record<string, Record<string, number>>, comparable=true):EvaluatorEntry=>
  ({evaluator_id, comparable, versions:{before:[], after:[]}, relations, ...(comparable?{}:{message:'Catalogue différent.'})});

describe('résultat par domaine', ()=>{
  it('dit chaque compte en phrase, accordée en genre et en nombre', ()=>{
    expect(phrase('taxo.spring-api', 'HANDLED_BY', 'ADDED', 4)).toBe('4 routes ajoutées');
    expect(phrase('taxo.spring-security', 'AUTHORIZED_BY', 'MODIFIED', 2)).toBe('2 règles de sécurité modifiées');
    expect(phrase('taxo.inventory', 'CONTAINS', 'REMOVED', 1)).toBe('1 fichier disparu');
    expect(phrase('taxo.structure', 'CONTAINS', 'ADDED', 2)).toBe('2 modules du dépôt ajoutés');
    expect(phrase('taxo.java-calls', 'CALLS', 'ADDED', 3)).toBe('3 appels entre méthodes ajoutés');
    expect(phrase('taxo.java-calls', 'CONTAINS', 'REMOVED', 1)).toBe('1 déclaration Java disparue');
    expect(phrase('taxo.java-calls', 'IMPLEMENTS', 'MODIFIED', 2)).toBe('2 implémentations modifiées');
    expect(phrase('taxo.git', 'HAS_COMMIT', 'OCCURRENCE_COUNT_CHANGED', 1)).toBe('1 commit relevé un nombre de fois différent');
    expect(phrase('x', 'NEW', 'STATUS_CHANGED', 3)).toBe('3 faits « NEW » dont le statut a changé');
    expect(phrase('x', 'NEW', 'OCCURRENCES_CHANGED', 1)).toBe('1 fait « NEW » dont les apparitions disent autre chose');
  });

  it('range chaque relation dans son domaine', ()=>{
    expect(domainOf('taxo.structure', 'CONTAINS')).toBe('architecture');
    expect(domainOf('taxo.java-calls', 'CONTAINS')).toBe('architecture');
    expect(domainOf('taxo.java-calls', 'CALLS')).toBe('architecture');
    expect(domainOf('taxo.java-calls', 'TYPED_AS')).toBe('architecture');
    expect(domainOf('taxo.inventory', 'CONTAINS')).toBe('fichiers');
    expect(domainOf('taxo.inventory', 'USES_TECHNOLOGY')).toBe('technologies');
    expect(domainOf('taxo.git', 'ABSENCE')).toBe('git');
    expect(domainOf('autre', 'ABSENCE')).toBe('autres');
  });

  it('ne additionne jamais deux évaluateurs : chacun est nommé', ()=>{
    const domains=byDomain({evaluators:[entry('taxo.structure', {BUILT_FROM:{ADDED:1}}), entry('taxo.spring-boot', {BUILT_FROM:{ADDED:1}})]});
    const architecture=domains.find(item=>item.id==='architecture');
    expect(architecture?.lines.map(line=>[line.text, line.source])).toEqual([
      ['1 composition d’application ajoutée', 'Structure du dépôt'], ['1 composition d’application ajoutée', 'Applications Spring Boot']]);
    expect(domains.find(item=>item.id==='api')?.state).toBe('unchanged');
    expect(domains.find(item=>item.id==='git')?.state).toBe('absent');
  });

  it('un domaine sans évaluateur comparable dit pourquoi ; un évaluateur inconnu a sa place à part', ()=>{
    const domains=byDomain({evaluators:[entry('taxo.git', {}, false), entry('outil.maison', {NEW:{REMOVED:2}})]});
    expect(domains.find(item=>item.id==='git')).toMatchObject({state:'refused', reasons:[{evaluator:'Historique Git', message:'Catalogue différent.'}]});
    expect(domains.find(item=>item.id==='autres')?.lines[0].text).toBe('2 faits « NEW » disparus');
    expect(byDomain({evaluators:[]}).map(item=>item.id)).not.toContain('autres');
  });
});
