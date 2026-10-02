// @vitest-environment happy-dom
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {TopMenu} from './shell';

(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;

let host:HTMLElement, root:Root;
beforeEach(()=>{host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{act(()=>root.unmount());host.remove();});

const render=(element:React.ReactElement)=>act(()=>{root.render(element);});
const click=(node:Element|null)=>act(()=>{node?.dispatchEvent(new MouseEvent('click',{bubbles:true}));});
const button=(label:string)=>Array.from(host.querySelectorAll('button')).find(item=>item.textContent?.trim()===label)??null;
const item=(label:string)=>Array.from(host.querySelectorAll('[role="menuitem"]')).find(node=>node.textContent===label)??null;

describe('TopMenu', ()=>{
  const setup=(latest?:()=>void)=>{
    const panel=vi.fn();
    render(<TopMenu latest={latest} analysis={close=><button type="button" onClick={()=>{panel();close();}}>Commande</button>}/>);
    return {panel};
  };
  it('ouvre et referme un menu au clic', ()=>{
    setup();
    click(button('Affichage'));
    expect(host.querySelectorAll('.menu-list')).toHaveLength(1);
    expect(button('Affichage')?.getAttribute('aria-expanded')).toBe('true');
    click(button('Affichage'));
    expect(host.querySelector('.menu-list')).toBeNull();
  });
  it('change de menu au survol quand un menu est déjà ouvert, pas avant', ()=>{
    setup();
    const hover=(label:string)=>act(()=>{button(label)?.dispatchEvent(new MouseEvent('mouseover',{bubbles:true}));});
    hover('Aide');
    expect(host.querySelector('.menu-list')).toBeNull();
    click(button('Fichier'));
    hover('Aide');
    expect(item('Taxo · version 0.1')).not.toBeNull();
    expect(item('Ajouter un projet…')).toBeNull();
  });
  it('ouvre Analyse en panneau de commande, que la commande peut refermer', ()=>{
    const {panel}=setup();
    click(button('Analyse'));
    expect(host.querySelector('.menu-panel[role="dialog"]')).not.toBeNull();
    expect(host.querySelector('.menu-list')).toBeNull();
    click(button('Commande'));
    expect(panel).toHaveBeenCalledOnce();
    expect(host.querySelector('.menu-panel')).toBeNull();
  });
  it('referme au clic ailleurs et sur Échap, pas au clic dans la barre', ()=>{
    setup();
    click(button('Affichage'));
    act(()=>{document.body.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));});
    expect(host.querySelector('.menu-list')).toBeNull();
    click(button('Affichage'));
    act(()=>{button('Affichage')?.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));});
    expect(host.querySelector('.menu-list')).not.toBeNull();
    act(()=>{document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}));});
    expect(host.querySelector('.menu-list')).toBeNull();
  });
  it('revient à la dernière analyse, et referme quand on choisit une page', ()=>{
    const latest=vi.fn();
    setup(latest);
    click(button('Affichage'));
    click(item('Revenir à la dernière analyse'));
    expect(latest).toHaveBeenCalledOnce();
    click(button('Fichier'));
    click(item('Ouvrir un projet…'));
    expect(host.querySelector('.menu-list')).toBeNull();
  });
});
