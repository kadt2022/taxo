import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {BrandMark, MENU_ICONS, ResultsNav, TopMenu, closeOnOutside, commitOf, navItemsOf, since} from './shell';
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

describe('navItemsOf', ()=>{
  const counts:RouteCounts={PROTECTED:4, PERMITS_ALL:1, NOT_INTERPRETED:7, NO_CONCLUSION:0, reserved:0, missing:0};
  const values:Record<string,string>={api:'210', architecture:'5', git:'2 280'};
  it('une entrée par page, groupées, avec un compte seulement quand Taxo en a un', ()=>{
    const items=navItemsOf(11, id=>values[id], counts, 3);
    expect(items.map(item=>[item.id, item.count])).toEqual([['overview',undefined], ['analyses','3'], ['comparaisons',undefined],
      ['interroger',undefined], ['technologies','11'], ['routes','210'], ['architecture','5'], ['securite','4'], ['donnees',undefined],
      ['historique','2 280'], ['limites',undefined], ['non-interpretees','7']]);
    expect(items.filter(item=>item.apart).map(item=>item.id)).toEqual(['analyses', 'technologies', 'historique', 'limites']);
    expect(items.find(item=>item.id==='donnees')?.muted).toBe(true);
  });
  it('n’invente aucun compte avant que les routes soient lues', ()=>{
    const items=navItemsOf(0, ()=>undefined);
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

describe('TopMenu', ()=>{
  const render=(initialOpen:string|null, latest?:()=>void, running=false)=>renderToStaticMarkup(<TopMenu latest={latest} running={running}
    initialOpen={initialOpen} analysis={()=><p>Panneau</p>}/>);
  it('ne garde que les commandes globales : aucun lien de navigation', ()=>{
    const html=render(null);
    for(const name of ['Fichier','Analyse','Affichage','Aide'])expect(html).toContain(`<path d="${MENU_ICONS[name]}"></path></svg><span class="menu-label">${name}</span></button>`);
    expect(new Set(Object.values(MENU_ICONS)).size).toBe(4);
    expect(html).not.toContain('Overview');
    expect(html).not.toContain('<a ');
    expect(html).not.toContain('menu-list');
    expect(html).toContain('aria-haspopup="dialog"');
  });
  it('ouvre un seul menu à la fois, et Analyse en panneau', ()=>{
    const html=render('Affichage');
    expect(html.match(/menu-list/g)).toHaveLength(1);
    expect(html).toContain('href="#/analyses"');
    expect(html).not.toContain('Ajouter un projet…');
    expect(render('Analyse')).toContain('<div class="menu-panel" role="dialog" aria-label="Analyse"><p>Panneau</p></div>');
  });
  it('mène aux projets, désactive ce qui n’est pas possible, et signale une analyse en cours', ()=>{
    expect(render('Fichier')).toContain('href="#/projets?ajouter=1"');
    expect(render('Fichier')).toContain('href="#/projets"');
    expect(render('Affichage')).toMatch(/disabled="">Revenir à la dernière analyse/);
    expect(render('Affichage', ()=>{})).not.toContain('disabled=""');
    expect(render('Aide')).toContain('version 0.1');
    expect(render(null, undefined, true)).toContain('class="is-running"');
    expect(render(null)).not.toContain('is-running');
  });
});

describe('BrandMark', ()=>{
  it('le même logo partout, décoratif', ()=>{
    const html=renderToStaticMarkup(<BrandMark/>);
    expect(html).toContain('class="brand-mark"');
    expect(html).toContain('aria-hidden="true"');
    // Un réseau dessiné : six nœuds autour d'un centre, colorés par un dégradé propre à chaque logo.
    expect(html.match(/<circle /g)).toHaveLength(7);
    const id=/<linearGradient id="([^"]+)"/.exec(html)?.[1];
    expect(html).toContain(`fill="url(#${id})"`);
  });
});

describe('ResultsNav', ()=>{
  it('une adresse par page, les comptes, la page grisée, les groupes et la page affichée', ()=>{
    const html=renderToStaticMarkup(<ResultsNav items={navItemsOf(11, id=>id==='api'?'210':undefined)} current="routes"/>);
    expect(html).toContain('href="#/technologies"');
    expect(html).toContain('href="#/"');
    expect(html).toContain('<span class="results-count">11</span>');
    expect(html).toContain('<span class="results-count">210</span>');
    expect(html).toContain('class="muted"');
    expect(html).toContain('title="Pas encore analysé"');
    expect(html).toContain('class="apart"');
    expect(html.match(/aria-current="page"/g)).toHaveLength(1);
    expect(html).toMatch(/href="#\/routes"[^>]*aria-current="page"/);
  });
});

