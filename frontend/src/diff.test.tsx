import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it} from 'vitest';
import {DiffView, type DiffFacts, type FileDiff, type LinkedFact} from './diff';

const line=(number:number, text:string, eol:'LF'|'CRLF'|'NONE'='LF')=>({number, text, eol});
const diff:FileDiff={path:'SecurityConfig.java', old_path:null, status:'MODIFIED', commit:'bbbbbbb1', parent:'aaaaaaa1',
  displayable:true, reason:null, before:{path:'SecurityConfig.java', size:10}, after:{path:'SecurityConfig.java', size:12},
  hunks:[{before_start:4, after_start:4, rows:[
    {kind:'equal', before:line(4, 'http'), after:line(4, 'http')},
    {kind:'changed', before:line(5, '.permitAll()'), after:line(5, '.hasRole("R")', 'CRLF')},
    {kind:'removed', before:line(6, 'fin', 'NONE'), after:null},
    {kind:'added', before:null, after:line(6, 'ajout')},
  ]}]};
const fact:LinkedFact={change:'MODIFIED', kind:'ASSERTION', subject:'route-pattern:/api/**', relation:'AUTHORIZED_BY',
  status:'OBSERVED', before:'symbol:permitAll', after:'symbol:hasRole', evaluator_id:'test.routes', precision:'LINE',
  lines:{before:[5], after:[5]}};
const links=(facts:LinkedFact[], not_comparable:string[]=[]):DiffFacts=>
  ({path:diff.path, commit:diff.commit, parent:diff.parent, facts, not_comparable});
const render=(value:FileDiff, linked:DiffFacts|null=null)=>renderToStaticMarkup(<DiffView diff={value} links={linked}/>);

describe('DiffView', ()=>{
  it('met le parent à gauche et le commit à droite', ()=>{
    const html=render(diff);
    expect(html).toContain('AVANT — SecurityConfig.java @ aaaaaaa');
    expect(html).toContain('APRÈS — SecurityConfig.java @ bbbbbbb');
    expect(html).toContain('@@ ligne 4 → ligne 4');
    expect(html).not.toContain('Faits Taxo touchés');
  });
  it('signale une fin de ligne CRLF ou absente sur une ligne modifiée', ()=>{
    const html=render(diff);
    expect(html).toContain('␍␊');
    expect(html).toContain('sans fin de ligne');
  });
  it('montre le renommage et un côté vide', ()=>{
    const html=render({...diff, old_path:'Old.java', status:'RENAMED', before:null});
    expect(html).toContain('Old.java → SecurityConfig.java');
    expect(html).toContain('AVANT — (aucun fichier)');
  });
  it('donne seulement la raison quand le contenu n’est pas affichable', ()=>{
    expect(render({...diff, displayable:false, reason:'CONFIDENTIAL', hunks:[]})).toContain('Fichier confidentiel');
    expect(render({...diff, displayable:false, reason:'INCONNU', hunks:[]})).toContain('Contenu non disponible.');
  });
  it('dit quand seul le nom ou le mode a changé', ()=>{
    expect(render({...diff, hunks:[]})).toContain('Aucune ligne modifiée');
  });
});

describe('faits reliés au diff', ()=>{
  it('marque les lignes reliées et liste le fait avec avant → après', ()=>{
    const html=render(diff, links([fact]));
    expect(html.match(/class="number linked"/g)).toHaveLength(2);
    expect(html).toContain('route-pattern:/api/**');
    expect(html).toContain('symbol:permitAll');
    expect(html).toContain('ligne avant 5 · après 5');
    expect(html).toContain('class="precision line"');
  });
  it('présente un lien au fichier sans marquer de ligne', ()=>{
    const onFile:LinkedFact={...fact, precision:'FILE', before:null, after:null, lines:{before:[], after:[]}};
    const html=render(diff, links([onFile]));
    expect(html).not.toContain('number linked');
    expect(html).toContain('fichier : aucune ligne modifiée ne porte sa preuve');
    expect(html).not.toContain('→ <code>');
  });
  it('dit quand aucun fait n’est relié, et quand un évaluateur n’est pas comparable', ()=>{
    const html=render(diff, links([], ['taxo.inventory']));
    expect(html).toContain('Aucun fait changé par ce commit');
    expect(html).toContain('Comparaison impossible pour taxo.inventory');
  });
});
