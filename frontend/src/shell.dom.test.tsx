// @vitest-environment happy-dom
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ProjectPicker, TopMenu, type PickerProps} from './shell';

(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;

let host:HTMLElement, root:Root;
beforeEach(()=>{host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{act(()=>root.unmount());host.remove();});

const render=(element:React.ReactElement)=>act(()=>{root.render(element);});
const click=(node:Element|null)=>act(()=>{node?.dispatchEvent(new MouseEvent('click',{bubbles:true}));});
const button=(label:string)=>Array.from(host.querySelectorAll('button')).find(item=>item.textContent?.trim()===label)??null;
const item=(label:string)=>Array.from(host.querySelectorAll('[role="menuitem"]')).find(node=>node.textContent===label)??null;

describe('TopMenu', ()=>{
  const setup=(canAnalyze=true)=>{
    const analyze=vi.fn(), addProject=vi.fn();
    render(<TopMenu canAnalyze={canAnalyze} analyze={analyze} addProject={addProject}/>);
    return {analyze, addProject};
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
  it('lance l’action choisie puis referme le menu', ()=>{
    const {analyze, addProject}=setup();
    click(button('Fichier'));
    click(item('Ajouter un projet…'));
    expect(addProject).toHaveBeenCalledTimes(1);
    expect(host.querySelector('.menu-list')).toBeNull();
    click(button('Analyse'));
    click(item('Lancer l’analyse globale'));
    expect(analyze).toHaveBeenCalledTimes(1);
  });
  it('ne lance pas une analyse impossible', ()=>{
    const {analyze}=setup(false);
    click(button('Analyse'));
    expect((item('Lancer l’analyse globale') as HTMLButtonElement).disabled).toBe(true);
    click(item('Lancer l’analyse globale'));
    expect(analyze).not.toHaveBeenCalled();
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
    render(<TopMenu canAnalyze analyze={vi.fn()} addProject={vi.fn()} latest={latest}/>);
    click(button('Affichage'));
    click(item('Revenir à la dernière analyse'));
    expect(latest).toHaveBeenCalledOnce();
    click(button('Affichage'));
    click(item('Choisir l’analyse affichée…'));
    expect(host.querySelector('.menu-list')).toBeNull();
  });
});

describe('ProjectPicker', ()=>{
  const projects=[{id:'a', name:'Iam', path:'/iam'}, {id:'b', name:'Taxo', path:'/taxo'}];
  function setup(extra:Partial<PickerProps>={}){
    const calls={setOpen:vi.fn(), setAdding:vi.fn(), onSelect:vi.fn(), setName:vi.fn(), setPath:vi.fn(), onSubmit:vi.fn((event:{preventDefault():void})=>event.preventDefault())};
    const props:PickerProps={projects, selected:'a', busy:false, loading:false, open:true, adding:false, status:'il y a 2 min', name:'', path:'', ...calls, ...extra};
    render(<ProjectPicker {...props}/>);
    return calls;
  }
  it('ouvre et referme le panneau depuis la pastille', ()=>{
    const calls=setup({open:false});
    click(host.querySelector('.picker-current'));
    expect(calls.setOpen).toHaveBeenCalledWith(true);
    const openCalls=setup({open:true});
    click(host.querySelector('.picker-current'));
    expect(openCalls.setOpen).toHaveBeenCalledWith(false);
  });
  it('choisit un projet', ()=>{
    const calls=setup();
    click(host.querySelector('[role="option"][aria-selected="false"]'));
    expect(calls.onSelect).toHaveBeenCalledWith('b');
  });
  it('passe en mode ajout', ()=>{
    const calls=setup();
    click(host.querySelector('.picker-add'));
    expect(calls.setAdding).toHaveBeenCalledWith(true);
  });
  it('remonte la saisie et l’envoi du formulaire', ()=>{
    const calls=setup({adding:true});
    const [name,path]=Array.from(host.querySelectorAll('input'));
    const type=(input:HTMLInputElement, value:string)=>act(()=>{
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')?.set?.call(input, value);
      input.dispatchEvent(new Event('input',{bubbles:true}));
    });
    type(name,'Mon app');type(path,'D:\\Projet');
    expect(calls.setName).toHaveBeenCalledWith('Mon app');
    expect(calls.setPath).toHaveBeenCalledWith('D:\\Projet');
    act(()=>{host.querySelector('form')?.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));});
    expect(calls.onSubmit).toHaveBeenCalledTimes(1);
  });
  it('referme au clic ailleurs', ()=>{
    const calls=setup();
    act(()=>{host.querySelector('.picker-panel')?.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));});
    expect(calls.setOpen).not.toHaveBeenCalled();
    act(()=>{document.body.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));});
    expect(calls.setOpen).toHaveBeenCalledWith(false);
  });
});
