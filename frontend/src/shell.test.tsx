import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {ProjectPicker, ResultsNav, SECTIONS, TopMenu, closeOnOutside, commitOf, resultItemsOf, since, watchSections, type NavItem, type PickerProps} from './shell';
import type {RouteCounts, Scan} from './overview';

const NOW=Date.parse('2026-09-30T12:00:00Z');
const ago=(minutes:number)=>new Date(NOW-minutes*60000).toISOString();

describe('since', ()=>{
  it('dit l’âge d’une analyse en unités entières', ()=>{
    expect(since(ago(0), NOW)).toBe('à l’instant');
    expect(since(ago(12), NOW)).toBe('il y a 12 min');
    expect(since(ago(180), NOW)).toBe('il y a 3 h');
    expect(since(ago(3*24*60), NOW)).toBe('il y a 3 j');
    expect(since(new Date(NOW+5*60000).toISOString(), NOW)).toBe('à l’instant');
  });
  it('ne dit rien d’une date absente ou illisible', ()=>{
    expect(since(undefined, NOW)).toBe('');
    expect(since('pas une date', NOW)).toBe('');
    expect(since(new Date(Date.now()-2*60000).toISOString())).toBe('il y a 2 min');
  });
});

describe('commitOf', ()=>{
  const scan=(extra:Partial<Scan>):Scan=>({id:'s', created_at:'', ...extra});
  it('préfère le commit de l’instantané et le raccourcit', ()=>{
    expect(commitOf(scan({snapshot:{repository:'p', commit:'abcdef0123456789', mode:'COMMIT'}, commit:'ffffffffffff'}))).toBe('abcdef0');
    expect(commitOf(scan({commit:'1234567890'}))).toBe('1234567');
  });
  it('ne plante pas quand le commit manque ou n’est pas une chaîne', ()=>{
    expect(commitOf(scan({}))).toBe('');
    expect(commitOf(scan({commit:null}))).toBe('');
    expect(commitOf(scan({commit:42 as unknown as string}))).toBe('');
  });
});

describe('resultItemsOf', ()=>{
  const counts:RouteCounts={PROTECTED:4, PERMITS_ALL:1, NOT_INTERPRETED:7, NO_CONCLUSION:0, reserved:0, missing:0};
  const values:Record<string,string>={api:'210', architecture:'5', git:'2 280'};
  it('met un compte seulement quand Taxo en a un', ()=>{
    const items=resultItemsOf(11, id=>values[id], counts);
    expect(items.map(item=>[item.id, item.count])).toEqual([['technologies','11'], ['routes','210'], ['details','5'], ['securite','4'], ['donnees',undefined],
      ['historique','2 280'], ['limites',undefined], ['non-interpretees','7']]);
    expect(items.find(item=>item.id==='donnees')?.muted).toBe(true);
    expect(items.find(item=>item.id==='limites')?.apart).toBe(true);
    expect(items.filter(item=>item.to==='routes').map(item=>item.id)).toEqual(['securite','non-interpretees']);
  });
  it('n’invente aucun compte avant que les routes soient lues', ()=>{
    const items=resultItemsOf(0, ()=>undefined);
    expect(items.every(item=>item.count===undefined)).toBe(true);
  });
});

describe('closeOnOutside', ()=>{
  function fakeDocument(){
    const handlers=new Map<string,(event:Event)=>void>();
    return {handlers, addEventListener:vi.fn((type:string, handler:(event:Event)=>void)=>{handlers.set(type, handler);}),
      removeEventListener:vi.fn((type:string)=>{handlers.delete(type);})};
  }
  it('referme au clic ailleurs, pas au clic dedans', ()=>{
    const doc=fakeDocument(), close=vi.fn(), inside={}, outside={};
    const stop=closeOnOutside({contains:node=>node===inside}, close, doc as unknown as Document);
    doc.handlers.get('mousedown')?.({target:inside} as unknown as Event);
    expect(close).not.toHaveBeenCalled();
    doc.handlers.get('mousedown')?.({target:outside} as unknown as Event);
    expect(close).toHaveBeenCalledTimes(1);
    stop();
    expect(doc.handlers.size).toBe(0);
  });
  it('referme sur Échap seulement', ()=>{
    const doc=fakeDocument(), close=vi.fn();
    closeOnOutside({contains:()=>true}, close, doc as unknown as Document);
    doc.handlers.get('keydown')?.({key:'a'} as unknown as Event);
    expect(close).not.toHaveBeenCalled();
    doc.handlers.get('keydown')?.({key:'Escape'} as unknown as Event);
    expect(close).toHaveBeenCalledTimes(1);
  });
  it('referme aussi quand il n’y a pas de panneau', ()=>{
    const doc=fakeDocument(), close=vi.fn();
    closeOnOutside(null, close, doc as unknown as Document);
    doc.handlers.get('mousedown')?.({target:{}} as unknown as Event);
    expect(close).toHaveBeenCalledTimes(1);
  });
});

describe('watchSections', ()=>{
  const items:NavItem[]=[{id:'technologies', label:'T'}, {id:'securite', to:'routes', label:'S'}, {id:'historique', label:'H'}];
  function setup(present:string[]){
    const observed:string[]=[];
    let notify:(entries:{target:{id:string}; isIntersecting:boolean}[])=>void=()=>{};
    const disconnect=vi.fn();
    const setCurrent=vi.fn();
    const stop=watchSections(items, setCurrent, callback=>{notify=callback;return {observe:node=>{observed.push((node as unknown as {id:string}).id);}, disconnect};},
      id=>present.includes(id)?({id} as unknown as Element):null);
    return {observed, setCurrent, disconnect, stop, notify:(entries:{target:{id:string}; isIntersecting:boolean}[])=>notify(entries)};
  }
  it('n’observe que les sections présentes, sous l’identifiant visé', ()=>{
    const watch=setup(['technologies','routes']);
    expect(watch.observed).toEqual(['technologies','routes']);
  });
  it('désigne la première entrée visible, y compris pour une cible partagée', ()=>{
    const watch=setup(['technologies','routes','historique']);
    watch.notify([{target:{id:'routes'}, isIntersecting:true}]);
    expect(watch.setCurrent).toHaveBeenLastCalledWith('securite');
    watch.notify([{target:{id:'technologies'}, isIntersecting:true}]);
    expect(watch.setCurrent).toHaveBeenLastCalledWith('technologies');
  });
  it('ne change rien quand aucune section n’est visible, et se déconnecte', ()=>{
    const watch=setup(['technologies']);
    watch.notify([{target:{id:'technologies'}, isIntersecting:false}]);
    expect(watch.setCurrent).not.toHaveBeenCalled();
    watch.stop();
    expect(watch.disconnect).toHaveBeenCalled();
  });
});

describe('TopMenu', ()=>{
  const render=(initialOpen:string|null, canAnalyze=true)=>renderToStaticMarkup(<TopMenu canAnalyze={canAnalyze} analyze={()=>{}} addProject={()=>{}} initialOpen={initialOpen}/>);
  it('montre Overview en premier, avec son icône, puis les quatre menus fermés', ()=>{
    const html=render(null);
    expect(html.indexOf('Overview')).toBeLessThan(html.indexOf('Fichier'));
    expect(html).toContain('class="menu-link"');
    for(const name of ['Fichier','Analyse','Affichage','Aide'])expect(html).toContain(`>${name}</button>`);
    expect(html).not.toContain('menu-list');
  });
  it('ouvre un seul menu à la fois', ()=>{
    const html=render('Affichage');
    expect(html.match(/menu-list/g)).toHaveLength(1);
    for(const section of SECTIONS)expect(html).toContain(`href="${section.href}"`);
    expect(html).not.toContain('Ajouter un projet…');
  });
  it('désactive l’analyse tant qu’elle n’est pas possible', ()=>{
    expect(render('Analyse', false)).toContain('disabled=""');
    expect(render('Analyse', true)).not.toContain('disabled=""');
    expect(render('Fichier')).toContain('Ajouter un projet…');
    expect(render('Aide')).toContain('version 0.1');
  });
});

describe('ResultsNav', ()=>{
  it('rend les comptes, la pastille grisée et la séparation', ()=>{
    const html=renderToStaticMarkup(<ResultsNav items={resultItemsOf(11, id=>id==='api'?'210':undefined)}/>);
    expect(html).toContain('href="#technologies"');
    expect(html).toContain('<span class="results-count">11</span>');
    expect(html).toContain('<span class="results-count">210</span>');
    expect(html).toContain('results-item muted');
    expect(html).toContain('title="Pas encore analysé"');
    expect(html).toContain('class="apart"');
    expect(html.match(/href="#routes"/g)).toHaveLength(3);
    expect(html).not.toContain('aria-current');
  });
});

describe('ProjectPicker', ()=>{
  const projects=[{id:'a', name:'Iam', path:'/iam'}, {id:'b', name:'Taxo', path:'/taxo'}];
  const base:PickerProps={projects, selected:'a', busy:false, loading:false, open:false, setOpen:()=>{}, adding:false, setAdding:()=>{}, onSelect:()=>{}, status:'il y a 12 min',
    name:'', setName:()=>{}, path:'', setPath:()=>{}, onSubmit:()=>{}};
  const render=(extra:Partial<PickerProps>={})=>renderToStaticMarkup(<ProjectPicker {...base} {...extra}/>);
  it('montre le projet courant et l’âge de son analyse, panneau fermé', ()=>{
    const html=render();
    expect(html).toContain('<strong>Iam</strong>');
    expect(html).toContain('il y a 12 min');
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain('picker-panel');
  });
  it('invite à choisir un projet quand aucun n’est sélectionné, sans état d’analyse', ()=>{
    const html=render({selected:'', status:''});
    expect(html).toContain('Choisir un projet');
    expect(html).not.toContain('picker-status');
  });
  it('liste les projets, le courant marqué, et propose l’ajout', ()=>{
    const html=render({open:true});
    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain('Projets <span>2</span>');
    expect(html).toContain('aria-selected="true">Iam');
    expect(html).toContain('aria-selected="false">Taxo');
    expect(html).toContain('picker-add');
    expect(html).not.toContain('<form');
  });
  it('déplie le formulaire d’ajout et le bloque pendant un travail en cours', ()=>{
    const html=render({open:true, adding:true, name:'Mon app', path:'D:\\Projet'});
    expect(html).toContain('<form');
    expect(html).toContain('value="Mon app"');
    expect(html).not.toContain('picker-add');
    expect(html).not.toMatch(/picker-save"[^>]*disabled/);
    expect(render({open:true, adding:true, busy:true})).toMatch(/disabled=""[^>]*>Iam|disabled=""/);
    expect(render({open:true, adding:true, loading:true})).toMatch(/picker-save" disabled=""/);
  });
});
