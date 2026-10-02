import {describe, expect, it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {ChoiceCard, NO_SEARCH, commitDay, localDay, matches, type Choice} from './picker';
import {sameCommit} from './comparison';

const commit={sha:'ada7a20ab4ffffffffffffffffffffffffffffff', subject:'Improve comparison UX', author:'Claude',
  authored_at:'2026-10-01T12:00:00+00:00'};
const analysis=(id:string, created_at:string, extra:Partial<Choice>={}):Choice=>({id, created_at,
  snapshot:{commit:commit.sha, mode:'COMMIT'}, commit, fact_count:53152, failed:[], ...extra});
const late=analysis('late', '2026-10-01T19:02:00');

describe('reconnaître une analyse', ()=>{
  it('montre la date de l’analyse, le commit tel qu’enregistré, son message et ses faits', ()=>{
    const html=renderToStaticMarkup(<ChoiceCard choice={late}/>);
    expect(html).toContain('Analyse du 1 oct. 2026');
    expect(html).toContain('Claude · 1 oct. 2026');
    expect(html).toContain('<code>ada7a20</code> · Claude');
    expect(html).toContain('« Improve comparison UX »');
    expect(html).toContain('53');
    expect(html).not.toContain('%');
  });

  it('dit les fichiers non commités, les analyseurs en échec, et un commit sans description', ()=>{
    const tree=renderToStaticMarkup(<ChoiceCard choice={analysis('t', '2026-10-01T20:00:00', {failed:['taxo.spring-security'],
      snapshot:{commit:commit.sha, mode:'WORKING_TREE', content_fingerprint:'sha256:abcdef0123456789'}})}/>);
    expect(tree).toContain('Fichiers non commités · empreinte abcdef0123');
    expect(tree).toContain('sur <code>ada7a20</code>');
    expect(tree).toContain('en échec : Sécurité Spring');
    const bare=renderToStaticMarkup(<ChoiceCard choice={analysis('b', '2026-10-01T20:00:00', {commit:null})}/>);
    expect(bare).toContain('commit ada7a20ab4');
  });
});

describe('rechercher une analyse', ()=>{
  it('par message, auteur ou début d’identifiant, sans casse', ()=>{
    expect(matches(late, {...NO_SEARCH, text:'COMPARISON'})).toBe(true);
    expect(matches(late, {...NO_SEARCH, text:'pi', field:'author'})).toBe(false);
    expect(matches(late, {...NO_SEARCH, text:'ADA7', field:'sha'})).toBe(true);
    expect(matches(late, {...NO_SEARCH, text:'7a20', field:'sha'})).toBe(false);
    expect(matches(analysis('n', '2026-10-01T19:02:00', {commit:null}), {...NO_SEARCH, text:'ada7', field:'sha'})).toBe(true);
  });

  it('par date de l’analyse ou date du commit, bornes incluses', ()=>{
    expect(matches(late, {...NO_SEARCH, from:'2026-10-01', to:'2026-10-01'})).toBe(true);
    expect(matches(late, {...NO_SEARCH, from:'2026-10-02'})).toBe(false);
    expect(matches(late, {...NO_SEARCH, dayOf:'commit', to:'2026-09-30'})).toBe(false);
    expect(matches(analysis('n', '2026-10-01T19:02:00', {commit:null}), {...NO_SEARCH, dayOf:'commit', from:'2026-01-01'})).toBe(false);
    expect(localDay('pas une date')).toBe('pas une da');
    expect(commitDay('demain')).toBe('demain');
  });

  it('signale deux analyses du même commit, jamais des fichiers non commités', ()=>{
    expect(sameCommit(late, analysis('early', '2026-09-30T03:22:00'))).toBe(true);
    expect(sameCommit(late, analysis('t', '2026-10-01T20:00:00', {snapshot:{commit:commit.sha, mode:'WORKING_TREE'}}))).toBe(false);
    expect(sameCommit(late, analysis('o', '2026-10-01T20:00:00', {snapshot:{commit:'b'.repeat(40), mode:'COMMIT'}}))).toBe(false);
  });
});
